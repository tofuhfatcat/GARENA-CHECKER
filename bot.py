#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hesu Generator — Telegram bot
Force-join gate · button-driven UI · admin panel. by @dvlist
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

import names
import telebot
from faker import Faker
from telebot import types
from telebot.apihelper import ApiTelegramException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")

# ── Config — tune here ───────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9213601526:AAHEzniDdfd3qRYlyi4KnMFCkFVRpOKr9I8")  # FILL: @BotFather

ADMIN_IDS = [6654003878]  # FILL: His Telegram user id(s)

DATA_FILE = "bot_data.json"

BRAND = "HESU"                  # header title
TAGLINE = "COMBO / NAME GENERATOR"

# The bot MUST be admin (or a member) in each channel/group, or get_chat_member
# cannot read membership and the gate never opens. FILL: His channels.
CHANNELS = [
    {"title": "Main Channel", "username": "@HesuMainChannel", "url": "https://t.me/HesuMainChannel"},
    {"title": "Group Chat",   "username": "@HesuDiscussion",  "url": "https://t.me/HesuDiscussion"},
]

MAX_AMOUNT = 50_000
PREVIEW_COUNT = 8
DEFAULT_RANGE = (1, 999)
COOLDOWN_SECONDS = 30 * 60   # wait between generations (admins exempt)
FEEDBACK_KEEP = 50           # how many feedback entries to retain

AMOUNT_PRESETS = [100, 250, 500, 1000, 2500, 5000]
RANGE_PRESETS = [(1, 999), (1, 99), (100, 999), (1000, 9999)]

# (name, locale, flag)
COUNTRIES = {
    "1":  ("USA",         "en_US", "🇺🇸"),
    "2":  ("UK",          "en_GB", "🇬🇧"),
    "3":  ("Philippines", "en_PH", "🇵🇭"),
    "4":  ("Russia",      "ru_RU", "🇷🇺"),
    "5":  ("Germany",     "de_DE", "🇩🇪"),
    "6":  ("France",      "fr_FR", "🇫🇷"),
    "7":  ("Italy",       "it_IT", "🇮🇹"),
    "8":  ("Spain",       "es_ES", "🇪🇸"),
    "9":  ("India",       "en_IN", "🇮🇳"),
    "10": ("Japan",       "ja_JP", "🇯🇵"),
    "11": ("China",       "zh_CN", "🇨🇳"),
    "12": ("Brazil",      "pt_BR", "🇧🇷"),
    "13": ("Mexico",      "es_MX", "🇲🇽"),
    "14": ("South Korea", "ko_KR", "🇰🇷"),
    "15": ("Indonesia",   "id_ID", "🇮🇩"),
    "16": ("Poland",      "pl_PL", "🇵🇱"),
    "17": ("Netherlands", "nl_NL", "🇳🇱"),
    "18": ("Turkey",      "tr_TR", "🇹🇷"),
    "19": ("Ukraine",     "uk_UA", "🇺🇦"),
    "20": ("All Countries", None,  "🌍"),
}

_ALL_LOCALES = [
    "en_US", "en_GB", "en_PH", "ru_RU", "de_DE", "fr_FR",
    "it_IT", "es_ES", "en_IN", "pt_BR", "id_ID", "pl_PL",
]
# ─────────────────────────────────────────────────────────────────────────────

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN not set — put it in config or the BOT_TOKEN env var.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# step: country | amount | amount_custom | range | range_custom | confirm | feedback
_state: dict[int, dict] = {}
_awaiting_broadcast: set[int] = set()
_awaiting_reply: dict[int, int] = {}   # admin_uid -> target_uid for feedback replies


def _st(uid: int) -> dict:
    return _state.setdefault(uid, {"step": "country", "country": None, "amount": None, "range": None})


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ── Persistence ──────────────────────────────────────────────────────────────
_data = {"users": {}, "total_generated": 0, "total_runs": 0, "feedback": []}


def load_data():
    global _data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            _data.update(json.load(f))
        _data.setdefault("users", {})
        _data.setdefault("feedback", [])
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
    rec.setdefault("generated", 0)
    rec.setdefault("runs", 0)
    rec["last_seen"] = int(time.time())
    _data["users"][uid] = rec
    save_data()


def bump_generated(uid, n):
    _data["total_generated"] += int(n)
    _data["total_runs"] += 1
    rec = _data["users"].setdefault(str(uid), {})
    rec["generated"] = rec.get("generated", 0) + int(n)
    rec["runs"] = rec.get("runs", 0) + 1
    save_data()


def cooldown_left(uid):
    """Seconds remaining before this user may generate again (0 = ready)."""
    if is_admin(uid):
        return 0
    last = _data["users"].get(str(uid), {}).get("last_gen", 0)
    left = COOLDOWN_SECONDS - (int(time.time()) - last)
    return max(0, left)


def mark_gen(uid):
    _data["users"].setdefault(str(uid), {})["last_gen"] = int(time.time())
    save_data()


def fmt_left(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def add_feedback(user, text):
    _data["feedback"].append({
        "uid": user.id,
        "name": getattr(user, "first_name", None),
        "username": getattr(user, "username", None),
        "text": text[:1000],
        "ts": int(time.time()),
    })
    _data["feedback"] = _data["feedback"][-FEEDBACK_KEEP:]
    save_data()


# ── Visual helpers ───────────────────────────────────────────────────────────
DIV = "━━━━━━━━━━━━━━━━━━━━"


def header(subtitle=""):
    top = f"<b>⚡ {BRAND}</b>  <i>{TAGLINE}</i>"
    if subtitle:
        return f"{top}\n<code>{DIV}</code>\n{subtitle}"
    return f"{top}\n<code>{DIV}</code>"


def card(rows):
    """Framed monospace key/value block for that 'dashboard' look."""
    width = max((len(k) for k, _ in rows), default=0)
    body = "\n".join(f"{k.ljust(width)} │ {v}" for k, v in rows)
    return f"<pre>{body}</pre>"


def _safe_edit(chat_id, msg_id, text, kb=None):
    try:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            return
        bot.send_message(chat_id, text, reply_markup=kb)
    except Exception:
        bot.send_message(chat_id, text, reply_markup=kb)


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
    start, end = number_range
    selected = (
        list(COUNTRIES.values())[:-1]
        if country_key == "20"
        else [COUNTRIES[country_key]]
    )

    lines: list[str] = []
    seen: set[str] = set()
    counts: dict[str, int] = {}

    for country_name, locale, _flag in selected:
        generator = get_generator(locale)
        made = attempts = 0
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
            log.warning("gate check failed for %s — is the bot admin there? (%s)",
                        ch["username"], e)
            missing.append(ch)
    return missing


def gate_keyboard(missing):
    kb = types.InlineKeyboardMarkup()
    for ch in missing:
        kb.add(types.InlineKeyboardButton(f"📢  {ch['title']}", url=ch["url"]))
    kb.add(types.InlineKeyboardButton("✅  I've Joined — Verify", callback_data="gate:check"))
    return kb


def send_gate(chat_id, missing, edit_msg=None):
    text = header(
        "🔒 <b>Access Locked</b>\n\n"
        "Join the channel(s) below to unlock the generator, "
        "then tap <b>Verify</b>.\n\n"
        f"{card([('Required', str(len(CHANNELS))), ('Pending', str(len(missing)))])}"
    )
    kb = gate_keyboard(missing)
    if edit_msg is not None:
        _safe_edit(chat_id, edit_msg, text, kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)


# ── Menus / UI ───────────────────────────────────────────────────────────────
def main_menu_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚀  Generate Combos", callback_data="nav:gen"))
    kb.row(
        types.InlineKeyboardButton("📊  My Stats", callback_data="nav:stats"),
        types.InlineKeyboardButton("💬  Feedback", callback_data="nav:feedback"),
    )
    kb.add(types.InlineKeyboardButton("❓  Help", callback_data="nav:help"))
    if is_admin(uid):
        kb.add(types.InlineKeyboardButton("🛠  Admin Panel", callback_data="adm:open"))
    return kb


def main_menu_text(uid):
    rec = _data["users"].get(str(uid), {})
    stats = card([
        ("Your runs", str(rec.get("runs", 0))),
        ("Your combos", f"{rec.get('generated', 0):,}"),
    ])
    return header("Welcome. Pick an action below 👇\n\n" + stats)


def country_kb():
    kb = types.InlineKeyboardMarkup()
    pairs = list(COUNTRIES.items())[:-1]
    for i in range(0, len(pairs), 2):
        row = []
        for key, (name, _loc, flag) in pairs[i:i + 2]:
            row.append(types.InlineKeyboardButton(f"{flag} {name}", callback_data=f"c:{key}"))
        kb.row(*row)
    kb.add(types.InlineKeyboardButton("🌍  All Countries", callback_data="c:20"))
    kb.add(types.InlineKeyboardButton("« Back", callback_data="nav:menu"))
    return kb


def amount_kb():
    kb = types.InlineKeyboardMarkup()
    btns = [types.InlineKeyboardButton(f"{n:,}", callback_data=f"amt:{n}") for n in AMOUNT_PRESETS]
    for i in range(0, len(btns), 3):
        kb.row(*btns[i:i + 3])
    kb.add(types.InlineKeyboardButton("✏️  Custom amount", callback_data="amt:custom"))
    kb.add(types.InlineKeyboardButton("« Back", callback_data="nav:gen"))
    return kb


def range_kb():
    kb = types.InlineKeyboardMarkup()
    btns = [types.InlineKeyboardButton(f"{a}-{b}", callback_data=f"rng:{a}-{b}") for a, b in RANGE_PRESETS]
    for i in range(0, len(btns), 2):
        kb.row(*btns[i:i + 2])
    kb.add(types.InlineKeyboardButton("✏️  Custom range", callback_data="rng:custom"))
    kb.add(types.InlineKeyboardButton("« Back", callback_data="step:amount"))
    return kb


def confirm_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🚀  Generate", callback_data="go"),
        types.InlineKeyboardButton("« Back", callback_data="step:range"),
    )
    kb.add(types.InlineKeyboardButton("✖  Cancel", callback_data="nav:menu"))
    return kb


def show_menu(chat_id, uid, edit=None):
    if edit:
        _safe_edit(chat_id, edit, main_menu_text(uid), main_menu_kb(uid))
    else:
        bot.send_message(chat_id, main_menu_text(uid), reply_markup=main_menu_kb(uid))


def show_country(chat_id, edit=None):
    text = header("🚀 <b>Step 1/3 — Country</b>\n\nChoose a source locale:")
    _safe_edit(chat_id, edit, text, country_kb()) if edit else \
        bot.send_message(chat_id, text, reply_markup=country_kb())


def show_amount(chat_id, uid, edit=None):
    name, _loc, flag = COUNTRIES[_st(uid)["country"]]
    text = header(f"🔢 <b>Step 2/3 — Amount</b>\n\n{flag} <b>{name}</b>\nHow many combos?")
    _safe_edit(chat_id, edit, text, amount_kb()) if edit else \
        bot.send_message(chat_id, text, reply_markup=amount_kb())


def show_range(chat_id, uid, edit=None):
    st = _st(uid)
    name, _loc, flag = COUNTRIES[st["country"]]
    text = header(
        f"🎲 <b>Step 3/3 — Number Range</b>\n\n{flag} <b>{name}</b> · "
        f"<b>{st['amount']:,}</b> combos\nPick the suffix range:"
    )
    _safe_edit(chat_id, edit, text, range_kb()) if edit else \
        bot.send_message(chat_id, text, reply_markup=range_kb())


def show_confirm(chat_id, uid, edit=None):
    st = _st(uid)
    name, _loc, flag = COUNTRIES[st["country"]]
    s, e = st["range"]
    text = header(
        "🧾 <b>Review & Confirm</b>\n\n"
        + card([
            ("Country", f"{flag} {name}"),
            ("Amount", f"{st['amount']:,}"),
            ("Range", f"{s}-{e}"),
            ("Format", "Name##:Name##"),
        ])
    )
    _safe_edit(chat_id, edit, text, confirm_kb()) if edit else \
        bot.send_message(chat_id, text, reply_markup=confirm_kb())


# ── Gate guard ───────────────────────────────────────────────────────────────
def guard(call):
    """True if blocked (and gate was shown)."""
    miss = missing_channels(call.from_user.id)
    if miss:
        bot.answer_callback_query(call.id, "Join the channels first ❌", show_alert=True)
        send_gate(call.message.chat.id, miss, edit_msg=call.message.message_id)
        return True
    return False


# ── Handlers ─────────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start", "menu"])
def on_start(message):
    uid = message.from_user.id
    track_user(message.from_user)
    _state.pop(uid, None)
    miss = missing_channels(uid)
    if miss:
        send_gate(message.chat.id, miss)
        return
    show_menu(message.chat.id, uid)


@bot.callback_query_handler(func=lambda c: c.data == "gate:check")
def on_gate_check(call):
    uid = call.from_user.id
    miss = missing_channels(uid)
    if miss:
        bot.answer_callback_query(call.id, f"Still {len(miss)} channel(s) left ❌", show_alert=True)
        send_gate(call.message.chat.id, miss, edit_msg=call.message.message_id)
        return
    bot.answer_callback_query(call.id, "Unlocked ✅")
    show_menu(call.message.chat.id, uid, edit=call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("nav:"))
def on_nav(call):
    if guard(call):
        return
    uid = call.from_user.id
    what = call.data.split(":", 1)[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if what == "menu":
        _state.pop(uid, None)
        show_menu(cid, uid, edit=mid)
    elif what == "gen":
        left = cooldown_left(uid)
        if left:
            bot.answer_callback_query(
                call.id, f"⏳ Cooldown — wait {fmt_left(left)}", show_alert=True)
            return
        _st(uid)["step"] = "country"
        show_country(cid, edit=mid)
    elif what == "feedback":
        _st(uid)["step"] = "feedback"
        text = header(
            "💬 <b>Feedback</b>\n\nSend your message, suggestion or bug report.\n"
            "It goes straight to the admins."
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("« Back", callback_data="nav:menu"))
        _safe_edit(cid, mid, text, kb)
    elif what == "stats":
        rec = _data["users"].get(str(uid), {})
        since = rec.get("first_seen")
        since_s = time.strftime("%Y-%m-%d", time.localtime(since)) if since else "—"
        text = header("📊 <b>Your Stats</b>\n\n" + card([
            ("Runs", str(rec.get("runs", 0))),
            ("Combos", f"{rec.get('generated', 0):,}"),
            ("Member since", since_s),
        ]))
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("« Back", callback_data="nav:menu"))
        _safe_edit(cid, mid, text, kb)
    elif what == "help":
        text = header(
            "❓ <b>Help</b>\n\n"
            "1️⃣ Pick a country\n"
            "2️⃣ Pick how many combos\n"
            "3️⃣ Pick a number range\n"
            "4️⃣ Confirm → get a <code>.txt</code> file\n\n"
            "Format: <code>Name123:Name123</code>\n"
            f"Max per run: <b>{MAX_AMOUNT:,}</b>"
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("« Back", callback_data="nav:menu"))
        _safe_edit(cid, mid, text, kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("step:"))
def on_step(call):
    if guard(call):
        return
    uid = call.from_user.id
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)
    which = call.data.split(":", 1)[1]
    if which == "amount":
        _st(uid)["step"] = "amount"
        show_amount(cid, uid, edit=mid)
    elif which == "range":
        _st(uid)["step"] = "range"
        show_range(cid, uid, edit=mid)


@bot.callback_query_handler(func=lambda c: c.data.startswith("c:"))
def on_country(call):
    if guard(call):
        return
    uid = call.from_user.id
    key = call.data.split(":", 1)[1]
    if key not in COUNTRIES:
        bot.answer_callback_query(call.id, "Unknown")
        return
    st = _st(uid)
    st["country"] = key
    st["step"] = "amount"
    bot.answer_callback_query(call.id)
    show_amount(call.message.chat.id, uid, edit=call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("amt:"))
def on_amount(call):
    if guard(call):
        return
    uid = call.from_user.id
    cid, mid = call.message.chat.id, call.message.message_id
    val = call.data.split(":", 1)[1]
    if val == "custom":
        _st(uid)["step"] = "amount_custom"
        bot.answer_callback_query(call.id)
        _safe_edit(cid, mid, header(
            f"✏️ <b>Custom Amount</b>\n\nSend a number <b>1–{MAX_AMOUNT:,}</b>."
        ))
        return
    st = _st(uid)
    st["amount"] = int(val)
    st["step"] = "range"
    bot.answer_callback_query(call.id, f"{int(val):,} ✓")
    show_range(cid, uid, edit=mid)


@bot.callback_query_handler(func=lambda c: c.data.startswith("rng:"))
def on_range(call):
    if guard(call):
        return
    uid = call.from_user.id
    cid, mid = call.message.chat.id, call.message.message_id
    val = call.data.split(":", 1)[1]
    if val == "custom":
        _st(uid)["step"] = "range_custom"
        bot.answer_callback_query(call.id)
        _safe_edit(cid, mid, header(
            "✏️ <b>Custom Range</b>\n\nSend like <code>100-999</code>."
        ))
        return
    a, b = (int(x) for x in val.split("-"))
    st = _st(uid)
    st["range"] = (a, b)
    st["step"] = "confirm"
    bot.answer_callback_query(call.id, f"{a}-{b} ✓")
    show_confirm(cid, uid, edit=mid)


@bot.callback_query_handler(func=lambda c: c.data == "go")
def on_go(call):
    if guard(call):
        return
    uid = call.from_user.id
    cid, mid = call.message.chat.id, call.message.message_id
    st = _st(uid)
    if st.get("step") != "confirm" or not st.get("country"):
        bot.answer_callback_query(call.id, "Start over with /start")
        return

    left = cooldown_left(uid)
    if left:
        bot.answer_callback_query(
            call.id, f"⏳ Cooldown — wait {fmt_left(left)}", show_alert=True)
        return

    bot.answer_callback_query(call.id, "Working…")
    mark_gen(uid)   # stamp now so the cooldown starts immediately
    for frame in ("⏳ Spinning up the generator…",
                  "🧬 Building combos…",
                  "📦 Packing your file…"):
        _safe_edit(cid, mid, header(frame))
        time.sleep(0.4)

    lines, counts = build_combos(st["country"], st["amount"], st["range"])
    total = len(lines)
    if total == 0:
        _safe_edit(cid, mid, header("⚠️ Nothing generated. Try /start again."))
        _state.pop(uid, None)
        return

    name, _loc, flag = COUNTRIES[st["country"]]
    s, e = st["range"]
    preview = "\n".join(lines[:PREVIEW_COUNT])
    breakdown = card([(k, f"{v:,}") for k, v in counts.items()]) if st["country"] == "20" else ""

    caption = header(
        "✅ <b>Done!</b>\n\n"
        + card([("Country", f"{flag} {name}"), ("Range", f"{s}-{e}"), ("Total", f"{total:,}")])
        + (f"\n{breakdown}" if breakdown else "")
        + f"\n<b>Preview</b>\n<code>{preview}</code>"
    )

    buf = io.BytesIO(("\n".join(lines) + "\n").encode("utf-8"))
    buf.name = f"{BRAND.lower()}_{name.replace(' ', '_')}_{total}.txt"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔁  Generate Again", callback_data="nav:gen"))
    kb.add(types.InlineKeyboardButton("🏠  Main Menu", callback_data="nav:menu"))

    bot.send_document(cid, buf, caption=caption, reply_markup=kb)
    try:
        bot.delete_message(cid, mid)
    except Exception:
        pass
    bump_generated(uid, total)
    _state.pop(uid, None)


# ── Feedback relay ───────────────────────────────────────────────────────────
def _uname(fb_or_user):
    u = fb_or_user.get("username") if isinstance(fb_or_user, dict) else getattr(fb_or_user, "username", None)
    return f"@{u}" if u else "—"


def relay_feedback(user, text):
    """Push a user's feedback to every admin live, with a Reply button."""
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩️ Reply", callback_data=f"fbreply:{user.id}"))
    body = header(
        "💬 <b>New Feedback</b>\n\n"
        + card([
            ("From", getattr(user, "first_name", "") or "—"),
            ("User", _uname(user)),
            ("ID", str(user.id)),
        ])
        + f"\n{text}"
    )
    for admin in ADMIN_IDS:
        try:
            bot.send_message(admin, body, reply_markup=kb)
        except Exception:
            pass


# ── Admin panel ──────────────────────────────────────────────────────────────
def admin_text():
    return header("🛠 <b>Admin Panel</b>\n\n" + card([
        ("Users", f"{len(_data['users']):,}"),
        ("Combos", f"{_data['total_generated']:,}"),
        ("Runs", f"{_data['total_runs']:,}"),
        ("Feedback", str(len(_data["feedback"]))),
        ("Channels", str(len(CHANNELS))),
    ]))


def admin_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🔄 Refresh", callback_data="adm:open"),
        types.InlineKeyboardButton("📣 Broadcast", callback_data="adm:bc"),
    )
    kb.row(
        types.InlineKeyboardButton("📥 Feedback", callback_data="adm:fb"),
        types.InlineKeyboardButton("📢 Channels", callback_data="adm:ch"),
    )
    kb.add(types.InlineKeyboardButton("🏠 Menu", callback_data="nav:menu"))
    return kb


@bot.message_handler(commands=["admin"])
def on_admin(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, admin_text(), reply_markup=admin_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm:"))
def on_admin_cb(call):
    uid = call.from_user.id
    if not is_admin(uid):
        bot.answer_callback_query(call.id, "Not authorized")
        return
    action = call.data.split(":", 1)[1]
    cid, mid = call.message.chat.id, call.message.message_id

    if action == "open":
        bot.answer_callback_query(call.id)
        _safe_edit(cid, mid, admin_text(), admin_kb())
    elif action == "ch":
        bot.answer_callback_query(call.id)
        rows = [(c["title"], c["username"]) for c in CHANNELS] or [("—", "none")]
        _safe_edit(cid, mid, header("📢 <b>Gate Channels</b>\n\n" + card(rows)), admin_kb())
    elif action == "fb":
        bot.answer_callback_query(call.id)
        recent = list(reversed(_data["feedback"][-8:]))
        if not recent:
            body = "📥 <b>Feedback Inbox</b>\n\n<i>Nothing yet.</i>"
            kb = admin_kb()
        else:
            chunks = []
            kb = types.InlineKeyboardMarkup()
            for fb in recent:
                when = time.strftime("%m-%d %H:%M", time.localtime(fb["ts"]))
                who = fb.get("name") or _uname(fb)
                snippet = fb["text"] if len(fb["text"]) <= 220 else fb["text"][:220] + "…"
                chunks.append(f"<b>{who}</b> <i>{when}</i>\n{snippet}")
                kb.add(types.InlineKeyboardButton(
                    f"↩️ Reply to {who}", callback_data=f"fbreply:{fb['uid']}"))
            body = "📥 <b>Feedback Inbox</b>\n\n" + "\n\n".join(chunks)
            kb.add(types.InlineKeyboardButton("« Back", callback_data="adm:open"))
        _safe_edit(cid, mid, header(body), kb)
    elif action == "bc":
        _awaiting_broadcast.add(uid)
        bot.answer_callback_query(call.id)
        _safe_edit(cid, mid, header(
            "📣 <b>Broadcast</b>\n\nSend the message now (any type).\n"
            "It goes to every user. /cancel_bc to abort."
        ))


@bot.callback_query_handler(func=lambda c: c.data.startswith("fbreply:"))
def on_fb_reply(call):
    uid = call.from_user.id
    if not is_admin(uid):
        bot.answer_callback_query(call.id, "Not authorized")
        return
    target = int(call.data.split(":", 1)[1])
    _awaiting_reply[uid] = target
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, header(
        f"↩️ <b>Reply mode</b>\n\nSend your reply — it goes to user <code>{target}</code>.\n"
        "/cancel_bc to abort."))


@bot.message_handler(commands=["cancel_bc"])
def on_cancel_bc(message):
    if is_admin(message.from_user.id):
        _awaiting_broadcast.discard(message.from_user.id)
        _awaiting_reply.pop(message.from_user.id, None)
        bot.reply_to(message, "Cancelled.")


def do_broadcast(admin_chat_id, message):
    sent = failed = 0
    for uid_str in list(_data["users"].keys()):
        try:
            bot.copy_message(int(uid_str), message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 25 == 0:
            time.sleep(1)
    bot.send_message(admin_chat_id, header(
        "📣 <b>Broadcast Done</b>\n\n" + card([("Sent", str(sent)), ("Failed", str(failed))])
    ))


# ── Free-text (custom inputs + broadcast capture) ────────────────────────────
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    uid = message.from_user.id

    if uid in _awaiting_broadcast and is_admin(uid):
        _awaiting_broadcast.discard(uid)
        bot.reply_to(message, "Sending…")
        do_broadcast(message.chat.id, message)
        return

    # Admin replying to a user's feedback
    if uid in _awaiting_reply and is_admin(uid):
        target = _awaiting_reply.pop(uid)
        try:
            bot.send_message(target, header(
                "💬 <b>Reply from admin</b>\n\n" + message.text.strip()))
            bot.reply_to(message, "✅ Reply delivered.")
        except Exception as e:
            bot.reply_to(message, f"❌ Could not deliver: {e}")
        return

    st = _state.get(uid)
    if not st:
        return
    text = message.text.strip()

    if st["step"] == "feedback":
        _state.pop(uid, None)
        add_feedback(message.from_user, text)
        relay_feedback(message.from_user, text)
        bot.send_message(message.chat.id, header(
            "✅ <b>Feedback sent</b>\n\nThanks — the admins got it."),
            reply_markup=main_menu_kb(uid))
        return

    if st["step"] == "amount_custom":
        if not text.isdigit():
            bot.reply_to(message, "Send a plain number, e.g. <code>500</code>.")
            return
        amount = int(text)
        if not (0 < amount <= MAX_AMOUNT):
            bot.reply_to(message, f"Out of range. Use 1–{MAX_AMOUNT:,}.")
            return
        st["amount"] = amount
        st["step"] = "range"
        show_range(message.chat.id, uid)
        return

    if st["step"] == "range_custom":
        try:
            a, b = (int(x) for x in text.split("-"))
            if a < 0 or b < a:
                raise ValueError
        except Exception:
            bot.reply_to(message, "Bad range. Example: <code>100-999</code>.")
            return
        st["range"] = (a, b)
        st["step"] = "confirm"
        show_confirm(message.chat.id, uid)
        return


# ── Boot ─────────────────────────────────────────────────────────────────────
def preflight():
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
            bot.get_chat_member(ch["username"], me.id)
            print(f"    OK        {ch['username']}  ({chat.type})")
        except Exception as e:
            ok = False
            print(f"    NOT-OK    {ch['username']}  -> {e}")
    print("  All channels reachable.\n" if ok else
          "\n  Fix: add the bot to each channel/group AND make it admin,\n"
          "       and check the @username spelling.\n")


def main():
    load_data()
    preflight()
    log.info("polling started — send /start")
    bot.infinity_polling(skip_pending=True, timeout=30)


if __name__ == "__main__":
    main()
