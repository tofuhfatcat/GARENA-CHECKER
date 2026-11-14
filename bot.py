#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Name/Combo Generator — Telegram bot
Force-join gate + inline UI. by @dvlist
"""
from __future__ import annotations


# ── Auto-install missing packages ────────────────────────────────────────────
def _auto_install():
    import importlib, subprocess, sys

    _REQUIRED = [
        ("telebot", "pyTelegramBotAPI"),
        ("faker",   "Faker"),
        ("names",   "names"),
    ]

    missing = []
    for mod, pkg in _REQUIRED:
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError:
            missing.append(pkg)

    if not missing:
        return

    print(f"\n  Installing missing packages: {', '.join(missing)}\n")
    for pkg in missing:
        print(f"  -> pip install {pkg}")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pkg],
            capture_output=True, text=True,
        )
        print(f"  {'ok' if r.returncode == 0 else 'FAILED'}  {pkg}")
        if r.returncode != 0 and r.stderr.strip():
            for ln in r.stderr.strip().splitlines()[-3:]:
                print(f"       {ln}")
    print()


_auto_install()
# ─────────────────────────────────────────────────────────────────────────────

import io
import os
import random
import tempfile

import names
import telebot
from faker import Faker
from telebot import types

# ── Config — tune here ───────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # FILL: bot token from @BotFather

# Channels the user must join before the bot unlocks.
# The bot MUST be an admin (or at least a member) in each channel, or
# get_chat_member cannot read membership. username is used for the verify call,
# url is the public join link, title is the button label.
# FILL: replace with His channels
CHANNELS = [
    {"title": "Main Channel",   "username": "@your_channel_1", "url": "https://t.me/your_channel_1"},
    {"title": "Backup Channel", "username": "@your_channel_2", "url": "https://t.me/your_channel_2"},
]

MAX_AMOUNT = 50_000          # hard cap per request, keep the box honest
PREVIEW_COUNT = 8            # lines shown inline before the file
DEFAULT_RANGE = (100, 999)   # fallback suffix range

COUNTRIES = {
    "1":  ("USA",         "en_US"),
    "2":  ("UK",          "en_GB"),
    "3":  ("Philippines", "en_PH"),
    "4":  ("Russia",      "ru_RU"),
    "5":  ("Germany",     "de_DE"),
    "6":  ("France",      "fr_FR"),
    "7":  ("Italy",       "it_IT"),
    "8":  ("Spain",       "es_ES"),
    "9":  ("India",       "en_IN"),
    "10": ("Japan",       "ja_JP"),
    "11": ("China",       "zh_CN"),
    "12": ("Brazil",      "pt_BR"),
    "13": ("Mexico",      "es_MX"),
    "14": ("South Korea", "ko_KR"),
    "15": ("Indonesia",   "id_ID"),
    "16": ("Poland",      "pl_PL"),
    "17": ("Netherlands", "nl_NL"),
    "18": ("Turkey",      "tr_TR"),
    "19": ("Ukraine",     "uk_UA"),
    "20": ("All Countries", None),
}

_ALL_LOCALES = [
    "en_US", "en_GB", "en_PH", "ru_RU", "de_DE", "fr_FR",
    "it_IT", "es_ES", "en_IN", "pt_BR", "id_ID", "pl_PL",
]
# ─────────────────────────────────────────────────────────────────────────────

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN not set — put it in config or the BOT_TOKEN env var.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Per-user flow state. step: menu | amount | range | confirm
_state: dict[int, dict] = {}


def _st(uid: int) -> dict:
    return _state.setdefault(uid, {"step": "menu", "country": None, "amount": None, "range": None})


# ── Generation core ──────────────────────────────────────────────────────────
def get_generator(locale):
    if locale is None:
        locale = random.choice(_ALL_LOCALES)
    try:
        return Faker(locale)
    except Exception:
        return Faker("en_US")


def generate_first_name(generator):
    try:
        first = generator.first_name()
    except Exception:
        first = names.get_first_name()
    first = (first or "").strip()
    if not first or not first.isalpha():
        first = names.get_first_name()
    return first.capitalize()


def build_combos(country_key, amount, number_range):
    """Return (lines, per_country_counts). Format: NameNum:NameNum, deduped."""
    start, end = number_range
    selected = (
        list(COUNTRIES.values())[:-1]
        if country_key == "20"
        else [COUNTRIES[country_key]]
    )

    lines: list[str] = []
    seen: set[str] = set()
    counts: dict[str, int] = {}

    for country_name, locale in selected:
        generator = get_generator(locale)
        made = 0
        attempts = 0
        max_attempts = max(amount * 20, 1000)

        while made < amount and attempts < max_attempts:
            attempts += 1
            first = generate_first_name(generator)
            number = random.randint(start, end)
            line = f"{first}{number}:{first}{number}"
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
            made += 1

        counts[country_name] = made

    return lines, counts


# ── Force-join gate ──────────────────────────────────────────────────────────
def missing_channels(user_id):
    """Return channels the user has NOT joined. On API error, treat as not joined."""
    missing = []
    for ch in CHANNELS:
        try:
            m = bot.get_chat_member(ch["username"], user_id)
            status = getattr(m, "status", "left")
            if status in ("left", "kicked"):
                missing.append(ch)
            elif status == "restricted" and not getattr(m, "is_member", False):
                missing.append(ch)
        except Exception:
            # bot not admin in channel, or channel unreachable — fail closed
            missing.append(ch)
    return missing


def gate_keyboard(missing):
    kb = types.InlineKeyboardMarkup()
    for ch in missing:
        kb.add(types.InlineKeyboardButton(f"📢 {ch['title']}", url=ch["url"]))
    kb.add(types.InlineKeyboardButton("✅ I've Joined", callback_data="gate:check"))
    return kb


def send_gate(chat_id, missing, edit_msg=None):
    text = (
        "🔒 <b>Access locked</b>\n\n"
        "Join the channel(s) below, then tap <b>✅ I've Joined</b>.\n\n"
        f"Pending: <b>{len(missing)}</b>"
    )
    kb = gate_keyboard(missing)
    if edit_msg is not None:
        try:
            bot.edit_message_text(text, chat_id, edit_msg, reply_markup=kb)
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, reply_markup=kb)


# ── UI builders ──────────────────────────────────────────────────────────────
def country_keyboard():
    kb = types.InlineKeyboardMarkup()
    items = list(COUNTRIES.items())
    # 2 per row, "All Countries" (key 20) full width at the bottom
    pairs = items[:-1]
    for i in range(0, len(pairs), 2):
        row = []
        for key, (name, _) in pairs[i:i + 2]:
            row.append(types.InlineKeyboardButton(name, callback_data=f"c:{key}"))
        kb.row(*row)
    kb.add(types.InlineKeyboardButton("🌍 All Countries", callback_data="c:20"))
    return kb


def menu_text():
    return (
        "✨ <b>Name / Combo Generator</b>\n\n"
        "Pick a country to begin.\n"
        "Output format: <code>NameNumber:NameNumber</code>"
    )


def confirm_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🚀 Generate", callback_data="go"),
        types.InlineKeyboardButton("✖ Cancel", callback_data="cancel"),
    )
    return kb


def send_menu(chat_id, edit_msg=None):
    if edit_msg is not None:
        try:
            bot.edit_message_text(menu_text(), chat_id, edit_msg, reply_markup=country_keyboard())
            return
        except Exception:
            pass
    bot.send_message(chat_id, menu_text(), reply_markup=country_keyboard())


# ── Handlers ─────────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def on_start(message):
    uid = message.from_user.id
    _state.pop(uid, None)
    miss = missing_channels(uid)
    if miss:
        send_gate(message.chat.id, miss)
        return
    _st(uid)
    send_menu(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data == "gate:check")
def on_gate_check(call):
    uid = call.from_user.id
    miss = missing_channels(uid)
    if miss:
        bot.answer_callback_query(call.id, f"Still {len(miss)} channel(s) to join ❌", show_alert=True)
        send_gate(call.message.chat.id, miss, edit_msg=call.message.message_id)
        return
    bot.answer_callback_query(call.id, "Verified ✅")
    _st(uid)
    send_menu(call.message.chat.id, edit_msg=call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("c:"))
def on_country(call):
    uid = call.from_user.id
    # re-gate on every action — no sneaking past by leaving the channel
    miss = missing_channels(uid)
    if miss:
        bot.answer_callback_query(call.id, "Join the channels first ❌", show_alert=True)
        send_gate(call.message.chat.id, miss, edit_msg=call.message.message_id)
        return

    key = call.data.split(":", 1)[1]
    if key not in COUNTRIES:
        bot.answer_callback_query(call.id, "Unknown country")
        return

    st = _st(uid)
    st["country"] = key
    st["step"] = "amount"
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"🌐 <b>{COUNTRIES[key][0]}</b> selected.\n\n"
        f"How many names? Send a number <b>(1–{MAX_AMOUNT:,})</b>.",
        call.message.chat.id, call.message.message_id,
    )


@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def on_cancel(call):
    uid = call.from_user.id
    _state.pop(uid, None)
    bot.answer_callback_query(call.id, "Cancelled")
    _st(uid)
    send_menu(call.message.chat.id, edit_msg=call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == "go")
def on_go(call):
    uid = call.from_user.id
    miss = missing_channels(uid)
    if miss:
        bot.answer_callback_query(call.id, "Join the channels first ❌", show_alert=True)
        send_gate(call.message.chat.id, miss, edit_msg=call.message.message_id)
        return

    st = _st(uid)
    if st.get("step") != "confirm" or not st.get("country"):
        bot.answer_callback_query(call.id, "Start over with /start")
        return

    bot.answer_callback_query(call.id, "Generating…")
    bot.edit_message_text("⏳ Generating, hold on…", call.message.chat.id, call.message.message_id)

    country_key = st["country"]
    amount = st["amount"]
    number_range = st["range"]

    lines, counts = build_combos(country_key, amount, number_range)
    total = len(lines)

    if total == 0:
        bot.send_message(call.message.chat.id, "Nothing generated. Try again with /start.")
        _state.pop(uid, None)
        return

    preview = "\n".join(lines[:PREVIEW_COUNT])
    breakdown = "\n".join(f"  • {k}: <b>{v:,}</b>" for k, v in counts.items())
    start, end = number_range

    caption = (
        "✅ <b>Done</b>\n\n"
        f"Country: <b>{COUNTRIES[country_key][0]}</b>\n"
        f"Range: <b>{start}-{end}</b>\n"
        f"Total: <b>{total:,}</b>\n\n"
        f"{breakdown}\n\n"
        f"<b>Preview</b>\n<code>{preview}</code>"
    )

    buf = io.BytesIO(("\n".join(lines) + "\n").encode("utf-8"))
    buf.name = f"combos_{COUNTRIES[country_key][0].replace(' ', '_')}_{total}.txt"

    bot.send_document(call.message.chat.id, buf, caption=caption)
    bot.send_message(call.message.chat.id, "Run again? /start")
    _state.pop(uid, None)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    uid = message.from_user.id
    st = _state.get(uid)
    if not st:
        return  # no active flow; ignore (or nudge)

    text = message.text.strip()

    if st["step"] == "amount":
        if not text.isdigit():
            bot.reply_to(message, "Send a plain number, e.g. <code>500</code>.")
            return
        amount = int(text)
        if amount <= 0 or amount > MAX_AMOUNT:
            bot.reply_to(message, f"Out of range. Use 1–{MAX_AMOUNT:,}.")
            return
        st["amount"] = amount
        st["step"] = "range"
        bot.send_message(
            message.chat.id,
            "🔢 Number suffix range?\n"
            "Send like <code>100-999</code> (or <code>skip</code> for default).",
        )
        return

    if st["step"] == "range":
        if text.lower() == "skip":
            st["range"] = DEFAULT_RANGE
        else:
            try:
                start, end = (int(x) for x in text.split("-"))
                if start < 0 or end < start:
                    raise ValueError
                st["range"] = (start, end)
            except Exception:
                bot.reply_to(message, "Bad range. Example: <code>100-999</code>.")
                return
        st["step"] = "confirm"
        start, end = st["range"]
        bot.send_message(
            message.chat.id,
            "🧾 <b>Review</b>\n\n"
            f"Country: <b>{COUNTRIES[st['country']][0]}</b>\n"
            f"Amount: <b>{st['amount']:,}</b>\n"
            f"Range: <b>{start}-{end}</b>\n"
            f"Format: <code>NameNumber:NameNumber</code>",
            reply_markup=confirm_keyboard(),
        )
        return


def main():
    print("Bot running. Ctrl+C to stop.")
    bot.infinity_polling(skip_pending=True, timeout=30)


if __name__ == "__main__":
    main()
