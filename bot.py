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
import json
import logging
import os
import random
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")

import names
import telebot
from faker import Faker
from telebot import types

# ── Config — tune here ───────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # FILL: bot token from @BotFather

# Admin user ids — only these can open /admin. FILL: add His Telegram user id.
ADMIN_IDS = [
    # 123456789,
]

DATA_FILE = "bot_data.json"  # tiny json store: known users + counters

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
# Admins waiting to send a broadcast message.
_awaiting_broadcast: set[int] = set()


def _st(uid: int) -> dict:
    return _state.setdefault(uid, {"step": "menu", "country": None, "amount": None, "range": None})


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ── Persistence (users + counters) ───────────────────────────────────────────
_data = {"users": {}, "total_generated": 0, "total_runs": 0}


def load_data():
    global _data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        _data.update(loaded)
        _data.setdefault("users", {})
    except Exception:
        pass


def save_data():
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_data, f)
        os.replace(tmp, DATA_FILE)
    except Exception:
        pass


def track_user(user):
    uid = str(user.id)
    rec = _data["users"].get(uid, {})
    rec["username"] = getattr(user, "username", None)
    rec["name"] = getattr(user, "first_name", None)
    rec.setdefault("first_seen", int(time.time()))
    rec["last_seen"] = int(time.time())
    _data["users"][uid] = rec
    save_data()


def bump_generated(n):
    _data["total_generated"] += int(n)
    _data["total_runs"] += 1
    save_data()


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
    """Return channels the user has NOT joined. On API error, fail closed + log why."""
    missing = []
    for ch in CHANNELS:
        try:
            m = bot.get_chat_member(ch["username"], user_id)
            status = getattr(m, "status", "left")
            if status in ("left", "kicked"):
                missing.append(ch)
            elif status == "restricted" and not getattr(m, "is_member", False):
                missing.append(ch)
        except Exception as e:
            # Most common: bot is not an admin/member of this channel, so it
            # literally cannot read membership. Shows up as the gate never
            # opening. Log it loud so it's obvious, then fail closed.
            log.warning("gate check failed for %s — is the bot admin there? (%s)",
                        ch["username"], e)
            missing.append(ch)
    return missing


def preflight():
    """Verify token + each channel is reachable by the bot. Prints a clear report."""
    try:
        me = bot.get_me()
        log.info("connected as @%s (id %s)", me.username, me.id)
    except Exception as e:
        log.error("getMe failed — bad token or no network: %s", e)
        raise SystemExit(1)

    print("\n  Channel preflight:")
    ok = True
    for ch in CHANNELS:
        try:
            chat = bot.get_chat(ch["username"])
            # Can the bot read members here? Checking its own membership proves it.
            bot.get_chat_member(ch["username"], me.id)
            print(f"    OK        {ch['username']}  ({chat.type})")
        except Exception as e:
            ok = False
            print(f"    NOT-OK    {ch['username']}  -> {e}")
    if not ok:
        print("\n  Fix: add the bot to each channel/group above AND make it an admin,\n"
              "       then check the @username is spelled exactly right.\n")
    else:
        print("  All channels reachable.\n")


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
    track_user(message.from_user)
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
    bump_generated(total)
    _state.pop(uid, None)


# ── Admin panel ──────────────────────────────────────────────────────────────
def admin_panel_text():
    users = len(_data["users"])
    return (
        "🛠 <b>Admin Panel</b>\n\n"
        f"👥 Users: <b>{users:,}</b>\n"
        f"🧮 Combos generated: <b>{_data['total_generated']:,}</b>\n"
        f"🏃 Runs: <b>{_data['total_runs']:,}</b>\n"
        f"📢 Channels: <b>{len(CHANNELS)}</b>"
    )


def admin_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("📊 Refresh", callback_data="adm:stats"),
        types.InlineKeyboardButton("📣 Broadcast", callback_data="adm:bc"),
    )
    kb.row(
        types.InlineKeyboardButton("📢 Channels", callback_data="adm:ch"),
        types.InlineKeyboardButton("✖ Close", callback_data="adm:close"),
    )
    return kb


@bot.message_handler(commands=["admin"])
def on_admin(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return  # silent — non-admins never learn it exists
    bot.send_message(message.chat.id, admin_panel_text(), reply_markup=admin_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm:"))
def on_admin_cb(call):
    uid = call.from_user.id
    if not is_admin(uid):
        bot.answer_callback_query(call.id, "Not authorized")
        return

    action = call.data.split(":", 1)[1]
    cid, mid = call.message.chat.id, call.message.message_id

    if action == "stats":
        bot.answer_callback_query(call.id, "Refreshed")
        try:
            bot.edit_message_text(admin_panel_text(), cid, mid, reply_markup=admin_keyboard())
        except Exception:
            pass

    elif action == "ch":
        bot.answer_callback_query(call.id)
        lines = "\n".join(f"  • {c['title']} — {c['username']}" for c in CHANNELS) or "  (none)"
        bot.edit_message_text(
            f"📢 <b>Gate Channels</b>\n\n{lines}",
            cid, mid, reply_markup=admin_keyboard(),
        )

    elif action == "bc":
        _awaiting_broadcast.add(uid)
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "📣 <b>Broadcast</b>\n\nSend the message now. It goes to every known user.\n"
            "Send /cancel_bc to abort.",
            cid, mid,
        )

    elif action == "close":
        _awaiting_broadcast.discard(uid)
        bot.answer_callback_query(call.id, "Closed")
        try:
            bot.delete_message(cid, mid)
        except Exception:
            pass


@bot.message_handler(commands=["cancel_bc"])
def on_cancel_bc(message):
    if is_admin(message.from_user.id):
        _awaiting_broadcast.discard(message.from_user.id)
        bot.reply_to(message, "Broadcast cancelled.")


def do_broadcast(admin_chat_id, message):
    ids = list(_data["users"].keys())
    sent = failed = 0
    for uid_str in ids:
        try:
            bot.copy_message(int(uid_str), message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 25 == 0:
            time.sleep(1)  # stay under Telegram's ~30 msg/s
    bot.send_message(
        admin_chat_id,
        f"📣 <b>Broadcast done</b>\n✅ Sent: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>",
    )


@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    uid = message.from_user.id

    # Admin broadcast capture takes priority over any user flow.
    if uid in _awaiting_broadcast and is_admin(uid):
        _awaiting_broadcast.discard(uid)
        bot.reply_to(message, "Sending…")
        do_broadcast(message.chat.id, message)
        return

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
    load_data()
    preflight()
    log.info("polling started — send /start to the bot")
    bot.infinity_polling(skip_pending=True, timeout=30)


if __name__ == "__main__":
    main()
