#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║              IchigoBot  — by @ichigopogi             ║
║         Telegram Account Tools & File Generator      ║
╚══════════════════════════════════════════════════════╝

Owner: @ichigopogi
Version: v1.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import secrets
import sys
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

from telegram import (
    InlineKeyboardMarkup,
    InputFile,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN      = os.getenv("BOT_TOKEN", "8963828575:AAG2RZOEg2oT_SsiDOeZR2-Vwm0ULQdBLiY").strip()
BOT_NAME       = "IchigoBot"
BOT_VERSION    = "v1.0"
OWNER_USERNAME = "@ichigopogi"
SUPPORT_URL    = os.getenv("SUPPORT_URL", "https://t.me/Ichigopogi")
ADMIN_IDS      = {int(x) for x in os.getenv("ADMIN_IDS", "5446268639").replace(" ", "").split(",") if x}

DB_PATH  = Path(os.getenv("DB_PATH",  "ichigo_db.json"))
DATA_DIR = Path(os.getenv("DATA_DIR", "data")).resolve()

RATE_LIMIT    = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
COOLDOWN_SEC  = int(os.getenv("COOLDOWN_SECONDS",   "1"))
SPAM_WINDOW   = float(os.getenv("SPAM_WINDOW",      "2.5"))
MAX_TS        = 32503680000  # year 2999 cap
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "50"))

DATA_DIR.mkdir(parents=True, exist_ok=True)

_START_TIME = time.time()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
)
for _lib in ("httpx", "telegram", "httpcore", "urllib3"):
    logging.getLogger(_lib).setLevel(logging.WARNING)
log = logging.getLogger("ichigo")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DURATION_MAP: dict[str, tuple[str, float]] = {
    "1h":   ("1 Hour",    1 / 24),
    "6h":   ("6 Hours",   6 / 24),
    "12h":  ("12 Hours",  12 / 24),
    "1d":   ("1 Day",     1),
    "3d":   ("3 Days",    3),
    "7d":   ("7 Days",    7),
    "14d":  ("14 Days",   14),
    "1m":   ("1 Month",   30),
    "3m":   ("3 Months",  90),
    "6m":   ("6 Months",  180),
    "1y":   ("1 Year",    365),
    "perm": ("Lifetime",  36500),
}
DURATION_ALIASES: dict[str, str] = {
    "permanent": "perm", "lifetime": "perm", "forever": "perm",
    "week": "7d", "1week": "7d", "month": "1m", "year": "1y",
    "day": "1d",  "1day": "1d", "hour": "1h",
}

# Sources available in IchigoBot
SOURCES = [
    "garena", "roblox", "tiktok", "mobilelegends", "codashop",
    "expressvpn", "facebook", "hotmail", "instagram", "netflix",
    "spotify", "crunchyroll",
]

LINE_OPTIONS    = [50, 100, 200, 300, 500, 750, 1000]
FORMAT_RAW      = "Raw"
FORMAT_USERPASS = "User:Pass"

EXECUTOR = ThreadPoolExecutor(max_workers=12, thread_name_prefix="ichigo")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SOURCE STOCK CACHE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_STOCK: dict[str, int] = {}

def _src_path(src: str) -> Optional[Path]:
    for ext in (".txt", ".csv"):
        p = DATA_DIR / f"{src}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None

def _count_lines(path: Path) -> int:
    try:
        count = 0
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                count += chunk.count(b"\n")
        return max(count, 1) if path.stat().st_size > 0 else 0
    except Exception:
        return 0

def _refresh_src(src: str) -> int:
    p = _src_path(src)
    n = _count_lines(p) if p else 0
    _STOCK[src] = n
    return n

def stock(src: str) -> int:
    return _STOCK.get(src, 0)

async def preload_sources() -> None:
    loop = asyncio.get_running_loop()
    results = await asyncio.gather(*[
        loop.run_in_executor(EXECUTOR, _refresh_src, s) for s in SOURCES
    ])
    have = sum(1 for r in results if r > 0)
    log.info("Sources loaded: %d/%d available", have, len(SOURCES))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  JSON DATABASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_DB_LOCK = asyncio.Lock()

def _load_db() -> dict:
    try:
        if DB_PATH.exists():
            return json.loads(DB_PATH.read_text("utf-8"))
    except Exception as e:
        log.warning("DB read error: %s", e)
    return {"users": {}, "keys": {}, "feedback": [], "meta": {}}

def _flush(db: dict) -> None:
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(DB_PATH)

_DB: dict = _load_db()

# ── User helpers ─────────────────────────────────────
async def user_get(uid: int) -> Optional[dict]:
    return _DB["users"].get(str(uid))

async def user_upsert(uid: int, username: str, first_name: str) -> dict:
    async with _DB_LOCK:
        k = str(uid)
        if k not in _DB["users"]:
            _DB["users"][k] = {
                "user_id":        uid,
                "username":       username or "",
                "first_name":     first_name or "",
                "joined":         int(time.time()),
                "premium_expiry": 0,
                "premium_tier":   None,
                "key_used":       None,
                "gen_count":      0,
                "last_gen":       0,
                "banned":         False,
            }
        else:
            _DB["users"][k]["username"]   = username or ""
            _DB["users"][k]["first_name"] = first_name or ""
        _flush(_DB)
        return _DB["users"][k]

async def user_all() -> list[dict]:
    return list(_DB["users"].values())

async def user_set_premium(uid: int, expiry: int, tier: str = "premium") -> None:
    async with _DB_LOCK:
        k = str(uid)
        if k in _DB["users"]:
            _DB["users"][k]["premium_expiry"] = expiry
            _DB["users"][k]["premium_tier"]   = tier
        _flush(_DB)

async def user_revoke(uid: int) -> None:
    async with _DB_LOCK:
        k = str(uid)
        if k in _DB["users"]:
            _DB["users"][k]["premium_expiry"] = 0
            _DB["users"][k]["premium_tier"]   = None
            _DB["users"][k]["key_used"]       = None
        _flush(_DB)

async def user_ban(uid: int, state: bool) -> None:
    async with _DB_LOCK:
        k = str(uid)
        if k in _DB["users"]:
            _DB["users"][k]["banned"] = state
        _flush(_DB)

async def user_inc_gen(uid: int) -> None:
    async with _DB_LOCK:
        k = str(uid)
        if k in _DB["users"]:
            _DB["users"][k]["gen_count"] = _DB["users"][k].get("gen_count", 0) + 1
            _DB["users"][k]["last_gen"]  = int(time.time())
        _flush(_DB)

# ── Key helpers ──────────────────────────────────────
async def key_create(code: str, dur_key: str, tier: str = "premium", by: int = 0) -> dict:
    label, days = DURATION_MAP[dur_key]
    rec = {
        "code":           code,
        "duration_key":   dur_key,
        "duration_label": label,
        "tier":           tier,
        "days":           days,
        "claim_expiry":   int(time.time() + 7 * 86400),
        "used":           False,
        "used_by":        None,
        "used_at":        None,
        "created_by":     by,
        "created_at":     int(time.time()),
    }
    async with _DB_LOCK:
        _DB["keys"][code] = rec
        _flush(_DB)
    return rec

async def key_get(code: str) -> Optional[dict]:
    return _DB["keys"].get(code)

async def key_redeem(code: str, uid: int) -> tuple[bool, str]:
    async with _DB_LOCK:
        rec = _DB["keys"].get(code)
        if not rec:
            return False, "Key not found."
        if rec["used"]:
            return False, "This key has already been used."
        if int(time.time()) > rec["claim_expiry"]:
            return False, "Key has expired — claim window closed."
        days  = rec["days"]
        tier  = rec.get("tier", "premium")
        now   = int(time.time())
        u     = _DB["users"].get(str(uid))
        if u:
            base    = max(now, _clamp_ts(u.get("premium_expiry", 0) or 0))
            new_exp = min(int(base + days * 86400), MAX_TS)
            _DB["users"][str(uid)]["premium_expiry"] = new_exp
            _DB["users"][str(uid)]["premium_tier"]   = tier
            _DB["users"][str(uid)]["key_used"]       = code
        rec["used"]    = True
        rec["used_by"] = uid
        rec["used_at"] = now
        _flush(_DB)
        return True, rec["duration_label"]

async def key_delete(code: str) -> bool:
    async with _DB_LOCK:
        if code in _DB["keys"]:
            del _DB["keys"][code]
            _flush(_DB)
            return True
        return False

async def key_all() -> list[dict]:
    return list(_DB["keys"].values())

# ── Feedback ─────────────────────────────────────────
async def feedback_add(uid: int, username: str, text: str) -> None:
    async with _DB_LOCK:
        _DB.setdefault("feedback", []).append({
            "uid": uid, "username": username,
            "text": text, "ts": int(time.time()),
        })
        _flush(_DB)

async def feedback_recent(n: int = 20) -> list[dict]:
    return list(reversed(_DB.get("feedback", [])))[:n]

# ── Meta ─────────────────────────────────────────────
def meta_get(k: str, default=None):
    return _DB.get("meta", {}).get(k, default)

async def meta_set(k: str, v) -> None:
    async with _DB_LOCK:
        _DB.setdefault("meta", {})[k] = v
        _flush(_DB)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  UTILITY HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _clamp_ts(ts) -> int:
    try:
        return min(max(0, int(ts)), MAX_TS)
    except Exception:
        return 0

def is_premium(u: Optional[dict]) -> bool:
    if not u:
        return False
    return _clamp_ts(u.get("premium_expiry", 0) or 0) > int(time.time())

def is_banned(u: Optional[dict]) -> bool:
    return bool(u and u.get("banned"))

def is_maintenance() -> bool:
    return bool(meta_get("maintenance", False))

def uptime() -> str:
    s = int(time.time() - _START_TIME)
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d}d {h}h {m}m"

def fmt_ts(ts) -> str:
    ts = _clamp_ts(ts)
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "—"

def expiry_str(u: dict) -> str:
    exp = _clamp_ts(u.get("premium_expiry", 0) or 0)
    now = int(time.time())
    if not exp or exp <= now:
        return "Expired"
    try:
        dt  = datetime.fromtimestamp(exp, tz=timezone.utc)
        rem = exp - now
        d, r = divmod(rem, 86400)
        h = r // 3600
        return f"{dt.strftime('%Y-%m-%d %H:%M')} UTC  (+{d}d {h}h)"
    except Exception:
        return "Active"

def make_key() -> str:
    return "ICHI-" + "-".join(secrets.token_hex(4).upper() for _ in range(3))

def src_label(s: str) -> str:
    labels = {
        "garena": "Garena", "roblox": "Roblox", "tiktok": "TikTok",
        "mobilelegends": "Mobile Legends", "codashop": "Codashop",
        "expressvpn": "ExpressVPN", "facebook": "Facebook", "hotmail": "Hotmail",
        "instagram": "Instagram", "netflix": "Netflix", "spotify": "Spotify",
        "crunchyroll": "Crunchyroll",
    }
    return labels.get(s, s.title())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RATE LIMITING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_rate_log: dict[int, list[float]] = {}
_last_msg: dict[int, float] = {}
_spam_log: dict[int, tuple[str, float]] = {}

def rate_ok(uid: int) -> bool:
    now   = time.time()
    times = [t for t in _rate_log.get(uid, []) if now - t < 60]
    if len(times) >= RATE_LIMIT or now - _last_msg.get(uid, 0) < COOLDOWN_SEC:
        return False
    times.append(now)
    _rate_log[uid] = times
    _last_msg[uid] = now
    return True

def spam_ok(uid: int, text: str) -> bool:
    now = time.time()
    last_text, last_ts = _spam_log.get(uid, ("", 0.0))
    _spam_log[uid] = (text, now)
    return not (text == last_text and now - last_ts < SPAM_WINDOW)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FSM STATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_STATE: dict[int, dict] = {}

def state_get(uid: int) -> dict:
    return _STATE.get(uid, {})

def state_set(uid: int, **kw) -> None:
    _STATE[uid] = kw

def state_clear(uid: int) -> None:
    _STATE.pop(uid, None)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  UI BUTTON LABELS  (no emojis — clean & simple)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B = {
    # Guest
    "REDEEM":  "Redeem Key",
    "BUY":     "Buy Key",
    "INFO":    "Info",
    # Premium
    "GENFILES": "Generate Files",
    "TOOLS":    "Tools",
    "FEEDBACK": "Send Feedback",
    "ACCOUNT":  "My Account",
    "SUPPORT":  "Contact Support",
    # Navigation
    "BACK":   "< Back",
    "CANCEL": "Cancel",
    "DONE":   "Done",
    "CLOSE":  "Close",
    # Tools
    "T_SPLIT":   "Split",
    "T_MERGE":   "Merge",
    "T_EXTRACT": "Userpass Extractor",
    "T_DEDUP":   "Remove Duplicate",
    "T_ASCII":   "ASCII Maker",
    # Admin
    "ADMIN":       "Admin Panel",
    "BACK2MENU":   "Main Menu",
    "BACK2PANEL":  "Back to Panel",
    "GENKEY":      "Generate Key",
    "KEY_LIST":    "Key List",
    "DEL_KEY":     "Delete Key",
    "EXT_PREM":    "Extend Premium",
    "USER_LIST":   "User List",
    "SEARCH_USER": "Search User",
    "BAN_USER":    "Ban User",
    "UNBAN_USER":  "Unban User",
    "REVOKE_USER": "Revoke Premium",
    "DB_STOCK":    "DB Stock",
    "ADD_STOCK":   "Add Stock",
    "BROADCAST":   "Broadcast",
    "DB_STATS":    "DB Stats",
    "MAINT_ON":    "Maintenance ON",
    "MAINT_OFF":   "Maintenance OFF",
}

BUILTIN_TOOLS = [B["T_SPLIT"], B["T_MERGE"], B["T_EXTRACT"], B["T_DEDUP"], B["T_ASCII"]]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  KEYBOARD BUILDERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _kb(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)

def kb_guest() -> ReplyKeyboardMarkup:
    return _kb([
        [B["REDEEM"], B["BUY"]],
        [B["INFO"]],
    ])

def kb_premium() -> ReplyKeyboardMarkup:
    return _kb([
        [B["GENFILES"], B["TOOLS"]],
        [B["FEEDBACK"], B["ACCOUNT"]],
        [B["SUPPORT"]],
    ])

def kb_admin() -> ReplyKeyboardMarkup:
    return _kb([
        [B["GENFILES"], B["TOOLS"]],
        [B["FEEDBACK"], B["ACCOUNT"]],
        [B["SUPPORT"]],
        [B["ADMIN"]],
    ])

def kb_for(u: Optional[dict]) -> ReplyKeyboardMarkup:
    if not u:
        return kb_guest()
    uid = u.get("user_id", 0)
    if uid in ADMIN_IDS:
        return kb_admin()
    return kb_premium() if is_premium(u) else kb_guest()

def kb_admin_panel() -> ReplyKeyboardMarkup:
    return _kb([
        [B["GENKEY"],      B["KEY_LIST"]],
        [B["DEL_KEY"],     B["EXT_PREM"]],
        [B["USER_LIST"],   B["SEARCH_USER"]],
        [B["BAN_USER"],    B["UNBAN_USER"]],
        [B["REVOKE_USER"]],
        [B["DB_STOCK"],    B["ADD_STOCK"]],
        [B["BROADCAST"],   B["DB_STATS"]],
        [B["MAINT_ON"],    B["MAINT_OFF"]],
        [B["BACK2MENU"]],
    ])

def kb_panel_cancel() -> ReplyKeyboardMarkup:
    return _kb([[B["BACK2PANEL"], B["CANCEL"]]])

def kb_sources() -> ReplyKeyboardMarkup:
    rows, row = [], []
    for i, s in enumerate(SOURCES, 1):
        row.append(src_label(s))
        if i % 2 == 0:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([B["BACK"]])
    return _kb(rows)

def kb_sources_stock() -> ReplyKeyboardMarkup:
    """Source picker for Add Stock — shows name and current count."""
    rows, row = [], []
    for i, s in enumerate(SOURCES, 1):
        label = f"{src_label(s)} [{stock(s):,}]"
        row.append(label)
        if i % 2 == 0:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([B["BACK2PANEL"]])
    return _kb(rows)

def kb_lines() -> ReplyKeyboardMarkup:
    return _kb([[str(n)] for n in LINE_OPTIONS] + [[B["BACK"]]])

def kb_format() -> ReplyKeyboardMarkup:
    return _kb([[FORMAT_RAW, FORMAT_USERPASS], [B["BACK"]]])

def kb_dur() -> ReplyKeyboardMarkup:
    items = list(DURATION_MAP.items())
    rows  = []
    for i in range(0, len(items), 2):
        rows.append([v[0] for _, v in items[i:i+2]])
    rows.append([B["CANCEL"]])
    return _kb(rows)

def kb_tools() -> ReplyKeyboardMarkup:
    rows = []
    for i in range(0, len(BUILTIN_TOOLS), 2):
        rows.append(BUILTIN_TOOLS[i:i+2])
    rows.append([B["BACK"]])
    return _kb(rows)

def kb_cancel() -> ReplyKeyboardMarkup:
    return _kb([[B["CANCEL"]]])

def kb_back() -> ReplyKeyboardMarkup:
    return _kb([[B["BACK"]]])

def kb_done_cancel() -> ReplyKeyboardMarkup:
    return _kb([[B["DONE"], B["CANCEL"]]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SCREEN RENDERING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LINE = "━" * 30
THIN = "┄" * 30

def panel(title: str, body: list[str]) -> str:
    return f"<b>{title}</b>\n{LINE}\n" + "\n".join(body)

def section(label: str, value: str) -> str:
    return f"<code>{label:<14}</code>  {value}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REPLY HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def reply(update: Update, text: str, kb=None, **kw) -> None:
    kw.setdefault("parse_mode", ParseMode.HTML)
    kw.setdefault("disable_web_page_preview", True)
    if kb is not None:
        kw["reply_markup"] = kb
    await update.message.reply_text(text, **kw)

async def send_file(update: Update, buf: BytesIO, caption: str = "", kb=None) -> None:
    kw: dict = {"parse_mode": ParseMode.HTML}
    if kb:
        kw["reply_markup"] = kb
    await update.message.reply_document(
        document=InputFile(buf, filename=buf.name),
        caption=caption, **kw,
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOW STOCK NOTIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _notify_low_stock(bot, src: str, remaining: int) -> None:
    if not ADMIN_IDS:
        return
    msg = panel("Low Stock Alert", [
        section("Source",    f"<b>{src_label(src)}</b>"),
        section("Remaining", f"<b>{remaining:,} lines</b>"),
        "",
        f"Stock has dropped below {LOW_STOCK_THRESHOLD}.",
        "Use Add Stock in the Admin Panel to replenish.",
    ])
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, msg, parse_mode=ParseMode.HTML,
                                   disable_web_page_preview=True)
        except Exception:
            pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATA GENERATION ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_USERPASS_RE = re.compile(r'([^:/\s@]+[@]?[^:/\s]+):([^:/\s]+)$')

def _sample_lines(src: str, n: int) -> Optional[list[str]]:
    p = _src_path(src)
    if not p:
        return None
    try:
        size = p.stat().st_size
        if size == 0:
            return None
        collected: list[str] = []
        seen: set[str]       = set()
        budget = max(n * 25, 500)
        with open(p, "rb") as f:
            if size < 51_200:
                lines = [ln.decode("utf-8", errors="replace").strip() for ln in f if ln.strip()]
                if not lines:
                    return None
                return random.sample(lines, min(n, len(lines)))
            for _ in range(budget):
                if len(collected) >= n:
                    break
                f.seek(random.randint(0, size - 2))
                f.readline()
                raw  = f.readline()
                if not raw:
                    f.seek(0); raw = f.readline()
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line in seen:
                    continue
                seen.add(line)
                collected.append(line)
        return collected or None
    except Exception:
        return None

def _remove_sent(path: Path, sent: list[str]) -> int:
    if not path or not path.exists():
        return -1
    try:
        quota = Counter(sent)
        kept: list[bytes] = []
        count = 0
        with open(path, "rb") as f:
            for raw in f:
                stripped = raw.decode("utf-8", errors="replace").strip()
                if not stripped:
                    kept.append(raw); continue
                if quota.get(stripped, 0) > 0:
                    quota[stripped] -= 1
                else:
                    kept.append(raw); count += 1
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            for ln in kept:
                f.write(ln)
        tmp.replace(path)
        return count
    except Exception as e:
        log.warning("remove_sent failed: %s", e)
        return -1

def _append_to_src(src: str, new_lines: list[str]) -> int:
    """Append new lines to a source file, skipping blank lines. Returns count added."""
    p = DATA_DIR / f"{src}.txt"
    added = 0
    try:
        with open(p, "a", encoding="utf-8") as f:
            for ln in new_lines:
                ln = ln.strip()
                if ln:
                    f.write(ln + "\n")
                    added += 1
    except Exception as e:
        log.warning("append_to_src failed: %s", e)
    return added

def _extract_userpass(lines: list[str]) -> tuple[list[str], bool]:
    out = []
    for ln in lines:
        m = _USERPASS_RE.search(ln.strip())
        if m:
            out.append(f"{m.group(1)}:{m.group(2)}")
    return out, True

def _apply_fmt(lines: list[str], fmt: str) -> tuple[list[str], bool]:
    if fmt == FORMAT_USERPASS:
        return _extract_userpass(lines)
    return lines, False

def _make_gen_file(src: str, lines: list[str], fmt: str) -> BytesIO:
    now       = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fmt_label = "User:Pass" if fmt == FORMAT_USERPASS else "Raw"
    header = "\n".join([
        "╔══════════════════════════════════════════╗",
        "║          IchigoBot  File Generator       ║",
        f"║  Source  : {src_label(src):<30}║",
        f"║  Format  : {fmt_label:<30}║",
        f"║  Lines   : {len(lines):<30}║",
        f"║  Date    : {now:<30}║",
        "║  Owner   : @ichigopogi                   ║",
        "╚══════════════════════════════════════════╝",
        "",
    ])
    content = header + "\n".join(lines) + "\n"
    buf = BytesIO(content.encode("utf-8"))
    buf.name = f"ichigo_{src}_{fmt_label.lower()}_{len(lines)}.txt"
    return buf

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BUILT-IN TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def tool_extract(text: str) -> tuple[str, int]:
    hits = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ":" in ln and not ln.startswith("http"):
            hits.append(ln)
    return "\n".join(hits), len(hits)

def tool_dedup(text: str) -> tuple[str, int, int]:
    lines  = [ln.strip() for ln in text.splitlines() if ln.strip()]
    unique = list(dict.fromkeys(lines))
    return "\n".join(unique), len(lines), len(unique)

def tool_split(text: str, chunk_size: int) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return ["\n".join(lines[i:i+chunk_size]) for i in range(0, len(lines), chunk_size)]

def tool_count(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.strip())

# ── ASCII Maker ───────────────────────────────────────
_ASCII_CHARS: dict[str, list[str]] = {
    "A": ["  XX  ", " X  X ", "XXXXXX", "X    X", "X    X"],
    "B": ["XXXXX ", "X    X", "XXXXXX", "X    X", "XXXXX "],
    "C": [" XXXXX", "X     ", "X     ", "X     ", " XXXXX"],
    "D": ["XXXX  ", "X   X ", "X    X", "X   X ", "XXXX  "],
    "E": ["XXXXXX", "X     ", "XXXX  ", "X     ", "XXXXXX"],
    "F": ["XXXXXX", "X     ", "XXXX  ", "X     ", "X     "],
    "G": [" XXXXX", "X     ", "X  XXX", "X    X", " XXXXX"],
    "H": ["X    X", "X    X", "XXXXXX", "X    X", "X    X"],
    "I": ["XXXXXX", "  X   ", "  X   ", "  X   ", "XXXXXX"],
    "J": ["XXXXXX", "    X ", "    X ", "X   X ", " XXX  "],
    "K": ["X   X ", "X  X  ", "XXX   ", "X  X  ", "X   X "],
    "L": ["X     ", "X     ", "X     ", "X     ", "XXXXXX"],
    "M": ["X    X", "XX  XX", "X XX X", "X    X", "X    X"],
    "N": ["X    X", "XX   X", "X X  X", "X  X X", "X   XX"],
    "O": [" XXXX ", "X    X", "X    X", "X    X", " XXXX "],
    "P": ["XXXXX ", "X    X", "XXXXX ", "X     ", "X     "],
    "Q": [" XXXX ", "X    X", "X  X X", "X   XX", " XXXXX"],
    "R": ["XXXXX ", "X    X", "XXXXX ", "X  X  ", "X   X "],
    "S": [" XXXXX", "X     ", " XXXX ", "     X", "XXXXX "],
    "T": ["XXXXXX", "  X   ", "  X   ", "  X   ", "  X   "],
    "U": ["X    X", "X    X", "X    X", "X    X", " XXXX "],
    "V": ["X    X", "X    X", "X    X", " X  X ", "  XX  "],
    "W": ["X    X", "X    X", "X XX X", "XX  XX", "X    X"],
    "X": ["X    X", " X  X ", "  XX  ", " X  X ", "X    X"],
    "Y": ["X    X", " X  X ", "  XX  ", "  X   ", "  X   "],
    "Z": ["XXXXXX", "    X ", "  XX  ", " X    ", "XXXXXX"],
    "0": [" XXXX ", "X   XX", "X  X X", "XX   X", " XXXX "],
    "1": ["  X   ", " XX   ", "  X   ", "  X   ", " XXX  "],
    "2": [" XXXX ", "X    X", "   XX ", "  X   ", "XXXXXX"],
    "3": [" XXXX ", "     X", "  XXX ", "     X", " XXXX "],
    "4": ["X   X ", "X   X ", "XXXXXX", "    X ", "    X "],
    "5": ["XXXXXX", "X     ", "XXXXX ", "     X", "XXXXX "],
    "6": [" XXXX ", "X     ", "XXXXX ", "X    X", " XXXX "],
    "7": ["XXXXXX", "    X ", "   X  ", "  X   ", " X    "],
    "8": [" XXXX ", "X    X", " XXXX ", "X    X", " XXXX "],
    "9": [" XXXX ", "X    X", " XXXXX", "     X", " XXXX "],
    " ": ["      ", "      ", "      ", "      ", "      "],
    "!": ["  X   ", "  X   ", "  X   ", "      ", "  X   "],
    "?": [" XXXX ", "     X", "   XX ", "      ", "  X   "],
    ".": ["      ", "      ", "      ", "      ", "  XX  "],
    "-": ["      ", "      ", "XXXX  ", "      ", "      "],
    "_": ["      ", "      ", "      ", "      ", "XXXXXX"],
    "@": [" XXXX ", "X  XXX", "X X X ", "X  XX ", " XXXXX"],
    "#": [" X X  ", "XXXXXX", " X X  ", "XXXXXX", " X X  "],
}

def tool_ascii(text: str) -> str:
    text = text.upper().strip()
    if len(text) > 20:
        return "Max 20 characters for ASCII art."
    rows = ["", "", "", "", ""]
    for ch in text:
        glyph = _ASCII_CHARS.get(ch, _ASCII_CHARS.get(" "))
        if glyph:
            for i, line in enumerate(glyph):
                rows[i] += line + " "
    result = "\n".join(r.rstrip() for r in rows)
    return f"<pre>{result}</pre>"

async def _send_tool_result(update: Update, title: str, summary: str, result: str, kb=None) -> None:
    if kb is None:
        kb = kb_tools()
    header = f"<b>{title}</b>\n{summary}"
    if len(result) < 3200:
        await reply(update, f"{header}\n\n<code>{result}</code>", kb=kb)
    else:
        buf = BytesIO(result.encode("utf-8"))
        buf.name = f"ichigo_{title.lower().replace(' ', '_')}.txt"
        await send_file(update, buf, header, kb=kb)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GUIDE TEXTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def GUIDE_GEN() -> str:
    src_list = " | ".join(src_label(s) for s in SOURCES)
    return panel("Generate Files", [
        "Pull fresh account data from the available sources.",
        "",
        "<b>Sources:</b>",
        f"<code>{src_list}</code>",
        "",
        "<b>Steps:</b>",
        "1. Pick a source",
        "2. Choose how many lines (50 – 1,000)",
        "3. Choose output format:",
        "   Raw — full original data as-is",
        "   User:Pass — clean credential pairs only",
        "4. File is generated and sent with the Ichigo header.",
        "",
        "Select a source to begin:",
    ])

GUIDE_TOOLS = panel("Tools", [
    "File processing tools for premium users.",
    "",
    "<b>Split</b>           — divide a large list into equal-sized parts",
    "<b>Merge</b>           — combine up to 5 .txt files into one",
    "<b>Userpass Extractor</b>  — pull user:pass pairs from any text",
    "<b>Remove Duplicate</b>    — strip duplicate lines, keep unique",
    "<b>ASCII Maker</b>         — convert text to block ASCII art",
    "",
    "Paste text or send a .txt file for most tools.",
    "Results over 3,200 characters are sent as a file.",
])

GUIDE_SPLIT = panel("Split", [
    "Divide a large list into smaller, equal-sized chunks.",
    "",
    "<b>How to use:</b>",
    "1. Send your text or .txt file",
    "2. Enter the chunk size (lines per part)",
    "3. Multiple parts are zipped; single part is a .txt",
    "",
    "Send your text or file now:",
])

GUIDE_MERGE = panel("Merge", [
    "Combine up to 5 .txt files into one merged file.",
    "",
    "<b>How to use:</b>",
    "1. Send your .txt files one by one (up to 5)",
    "2. Tap Done when finished",
    "3. Receive one merged .txt with a line count summary",
    "",
    "Send your first .txt file now:",
])

GUIDE_EXTRACT = panel("Userpass Extractor", [
    "Extracts every user:pass pair from text or a file.",
    "",
    "<b>How to use:</b>",
    "1. Paste text directly or send a .txt file",
    "2. Bot scans every line for colon-separated pairs",
    "3. Returns only the matching lines",
    "",
    "Matches any line with a colon — email:pass, user:token, etc.",
    "Lines starting with http:// or https:// are skipped.",
    "",
    "Send your text or file now:",
])

GUIDE_DEDUP = panel("Remove Duplicate", [
    "Removes every duplicate line, keeps only the first occurrence.",
    "",
    "<b>How to use:</b>",
    "1. Paste text or send a .txt file",
    "2. Bot compares all lines and removes repeats",
    "3. You get a clean unique list with a removal count",
    "",
    "Matching is case-sensitive. Empty lines are excluded.",
    "",
    "Send your text or file now:",
])

GUIDE_ASCII = panel("ASCII Maker", [
    "Convert any text into block-style ASCII art.",
    "",
    "<b>How to use:</b>",
    "Type or send the text you want converted.",
    "Maximum 20 characters.",
    "",
    "Supported: A-Z, 0-9, and basic symbols: ! ? . - _ @ #",
    "",
    "Example input:  ICHIGO",
    "",
    "Send your text now:",
])

TOOL_GUIDES = {
    B["T_SPLIT"]:   GUIDE_SPLIT,
    B["T_MERGE"]:   GUIDE_MERGE,
    B["T_EXTRACT"]: GUIDE_EXTRACT,
    B["T_DEDUP"]:   GUIDE_DEDUP,
    B["T_ASCII"]:   GUIDE_ASCII,
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    u    = await user_upsert(user.id, user.username or "", user.first_name or "")
    u    = await user_get(user.id)
    name = user.first_name or "there"

    if is_banned(u):
        await reply(update, "You are banned from using this bot.", kb=ReplyKeyboardRemove())
        return

    if is_premium(u) or user.id in ADMIN_IDS:
        tier = (u.get("premium_tier") or "Premium").upper()
        exp  = expiry_str(u) if user.id not in ADMIN_IDS else "Lifetime (Admin)"
        text = panel(f"Welcome back, {name}", [
            section("Status",     f"<b>{tier}</b>"),
            section("Expires",    f"<code>{exp}</code>"),
            section("Total Gens", f"<b>{u.get('gen_count', 0):,}</b>"),
            "",
            "You have full access. Use the menu below.",
        ])
    else:
        src_active = sum(1 for s in SOURCES if stock(s) > 0)
        text = panel(f"Welcome to {BOT_NAME}", [
            f"<i>Account tools and file generator — by {OWNER_USERNAME}</i>",
            "",
            "<b>What this bot does:</b>",
            "Generate account data files from 12 popular platforms.",
            "Use built-in tools to split, merge, extract, and clean lists.",
            "",
            "<b>Sources available:</b>",
            "Garena, Roblox, TikTok, Mobile Legends, Codashop,",
            "ExpressVPN, Facebook, Hotmail, Instagram, Netflix,",
            "Spotify, Crunchyroll",
            f"  Active right now: {src_active}/{len(SOURCES)}",
            "",
            "<b>How to get started:</b>",
            "1. Tap <b>Buy Key</b> to purchase a premium key",
            "2. Tap <b>Redeem Key</b> and enter your key code",
            "3. Once active, Generate Files and Tools unlock",
            "",
            "<b>Key plans:</b>  1H, 6H, 12H, 1D, 3D, 7D, 14D, 1M, 3M, 6M, 1Y, Lifetime",
            "",
            section("Owner",   OWNER_USERNAME),
            section("Contact", SUPPORT_URL),
        ])
    await reply(update, text, kb=kb_for(u))

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u    = await user_get(update.effective_user.id)
    text = panel("Help and Commands", [
        "<b>User commands:</b>",
        "/start   — Return to main menu",
        "/redeem  — Redeem a premium key",
        "/account — View your account details",
        "/info    — Bot info and stats",
        "",
        "<b>Premium features:</b>",
        "Generate Files — Pull account data from 12+ sources",
        "Split          — Split large lists into parts",
        "Merge          — Combine multiple .txt files",
        "Extractor      — Extract user:pass pairs",
        "Remove Dup.    — Remove duplicate lines",
        "ASCII Maker    — Convert text to ASCII art",
        "",
        "<b>Admin commands:</b>",
        "/genkey [dur] [count] — Generate keys",
        "/broadcast [msg]      — Message all users",
        "/stats                — Bot statistics",
        "",
        f"Owner / Support: {OWNER_USERNAME}",
        f"Contact: {SUPPORT_URL}",
    ])
    await reply(update, text, kb=kb_for(u))

async def cmd_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    u    = await user_get(user.id)
    if not u:
        await reply(update, "Run /start first."); return
    tier = u.get("premium_tier") or "Guest"
    exp  = expiry_str(u) if is_premium(u) or user.id in ADMIN_IDS else "Not active"
    text = panel("My Account", [
        section("Name",       u.get("first_name", "")),
        section("Username",   f"@{u.get('username', '—')}"),
        section("User ID",    f"<code>{u.get('user_id')}</code>"),
        section("Tier",       f"<b>{tier.upper()}</b>"),
        section("Expires",    f"<code>{exp}</code>"),
        THIN,
        section("Total Gens", f"<b>{u.get('gen_count', 0):,}</b>"),
        section("Last Gen",   fmt_ts(u.get("last_gen", 0))),
        section("Joined",     fmt_ts(u.get("joined", 0))),
    ])
    await reply(update, text, kb=kb_for(u))

async def cmd_redeem(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await user_upsert(user.id, user.username or "", user.first_name or "")
    if ctx.args:
        code    = ctx.args[0].strip().upper()
        ok, msg = await key_redeem(code, user.id)
        u = await user_get(user.id)
        if ok:
            await reply(update, panel("Key Redeemed", [
                section("Duration", f"<b>{msg}</b>"),
                section("Expires",  f"<code>{expiry_str(u)}</code>"),
                "",
                "Premium access is now active.",
            ]), kb=kb_for(u))
        else:
            await reply(update, panel("Redeem Failed", [msg]), kb=kb_for(u))
        return
    state_set(user.id, step="await_key")
    await reply(update, panel("Redeem Key", [
        "Send your key code below.",
        "",
        "Format: <code>ICHI-XXXXXXXX-XXXXXXXX-XXXXXXXX</code>",
        "Keys are not case-sensitive.",
    ]), kb=kb_cancel())

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = await user_get(update.effective_user.id)
    await _show_info(update, u)

async def _show_info(update: Update, u: Optional[dict]) -> None:
    users       = await user_all()
    total_users = len(users)
    prem_users  = sum(1 for x in users if is_premium(x))
    src_active  = sum(1 for s in SOURCES if stock(s) > 0)
    db_kb       = DB_PATH.stat().st_size // 1024 if DB_PATH.exists() else 0

    text = panel(f"{BOT_NAME}  {BOT_VERSION}", [
        f"<i>Account tools and file generator by {OWNER_USERNAME}</i>",
        "",
        "<b>Stats:</b>",
        section("Users",    f"{total_users:,}"),
        section("Premium",  f"{prem_users:,}"),
        section("Sources",  f"{src_active}/{len(SOURCES)} active"),
        section("DB size",  f"{db_kb} KB"),
        section("Uptime",   uptime()),
        "",
        "<b>Sources:</b>",
        ", ".join(src_label(s) for s in SOURCES),
        "",
        "<b>Tools:</b>",
        "Split  |  Merge  |  Userpass Extractor",
        "Remove Duplicate  |  ASCII Maker",
        "",
        "<b>Key plans:</b>",
        "1H, 6H, 12H, 1D, 3D, 7D, 14D, 1M, 3M, 6M, 1Y, Lifetime",
        "",
        THIN,
        section("Owner",   OWNER_USERNAME),
        section("Contact", SUPPORT_URL),
        "",
        "<b>Commands:</b>  /start  /redeem  /account  /info  /help",
    ])
    await reply(update, text, kb=kb_for(u))

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    users  = await user_all()
    keys   = await key_all()
    prem   = sum(1 for u in users if is_premium(u))
    banned = sum(1 for u in users if u.get("banned"))
    text = panel("Admin — DB Stats", [
        section("Uptime",      uptime()),
        THIN,
        section("Total users", f"{len(users):,}"),
        section("Premium",     f"{prem:,}"),
        section("Banned",      f"{banned:,}"),
        THIN,
        section("Total keys",  f"{len(keys):,}"),
        section("Used",        f"{sum(1 for k in keys if k['used']):,}"),
        section("Unused",      f"{sum(1 for k in keys if not k['used']):,}"),
        THIN,
        section("Sources",     f"{sum(1 for s in SOURCES if stock(s) > 0)}/{len(SOURCES)}"),
        section("Maintenance", "ON" if is_maintenance() else "OFF"),
    ])
    await reply(update, text, kb=kb_admin_panel())

async def cmd_genkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    if not ctx.args:
        durs = "\n".join(f"  <code>{k}</code> — {v[0]}" for k, v in DURATION_MAP.items())
        await reply(update, f"<b>Usage:</b> /genkey [duration] [count=1]\n\n{durs}")
        return
    raw = ctx.args[0].lower()
    dur = DURATION_ALIASES.get(raw, raw)
    if dur not in DURATION_MAP:
        await reply(update, f"Unknown duration: <code>{raw}</code>"); return
    count = 1
    if len(ctx.args) > 1:
        try:
            count = max(1, min(int(ctx.args[1]), 20))
        except ValueError:
            pass
    codes = []
    for _ in range(count):
        code = make_key()
        rec  = await key_create(code, dur, by=user.id)
        codes.append(f"<code>{code}</code>  — {rec['duration_label']}")
    await reply(update, panel(f"{count} Key(s) Generated", codes + ["", "Claim window: 7 days."]))

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    if ctx.args:
        await _do_broadcast(update, ctx, " ".join(ctx.args)); return
    state_set(user.id, step="await_broadcast")
    await reply(update, panel("Broadcast", ["Type your message and send it."]), kb=kb_panel_cancel())

async def _do_broadcast(update: Update, ctx, msg: str) -> None:
    users = await user_all()
    sent = failed = 0
    for u in users:
        try:
            await ctx.bot.send_message(
                u["user_id"],
                panel(f"{BOT_NAME} Announcement", [msg]),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            failed += 1
    await reply(update, panel("Broadcast Complete", [
        section("Sent",   f"{sent:,}"),
        section("Failed", f"{failed:,}"),
    ]), kb=kb_admin_panel())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DB STOCK VIEW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _show_db_stock(update: Update) -> None:
    loop = asyncio.get_running_loop()
    await asyncio.gather(*[loop.run_in_executor(EXECUTOR, _refresh_src, s) for s in SOURCES])

    total = 0
    lines = []
    for s in SOURCES:
        n = stock(s)
        total += n
        if n == 0:
            tag = "  [EMPTY]"
        elif n < LOW_STOCK_THRESHOLD:
            tag = "  [LOW]"
        else:
            tag = ""
        lines.append(f"<code>{src_label(s):<18}</code> {n:>6,}{tag}")

    lines += [
        THIN,
        section("Total lines", f"{total:,}"),
        section("Threshold",   f"{LOW_STOCK_THRESHOLD} (low stock alert)"),
    ]
    await reply(update, panel("DB Stock", lines), kb=kb_admin_panel())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN MESSAGE ROUTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text.strip()
    u    = await user_upsert(user.id, user.username or "", user.first_name or "")

    if is_banned(u) and user.id not in ADMIN_IDS:
        await reply(update, "You are banned.", kb=ReplyKeyboardRemove()); return

    if is_maintenance() and user.id not in ADMIN_IDS:
        await reply(update, panel("Under Maintenance", [
            meta_get("maintenance_reason", "Bot is temporarily unavailable."),
            "", "Please check back soon.",
        ]), kb=ReplyKeyboardRemove()); return

    if not spam_ok(user.id, text) and user.id not in ADMIN_IDS:
        return
    if not rate_ok(user.id) and user.id not in ADMIN_IDS:
        await reply(update, f"Slow down. Limit: {RATE_LIMIT} msg/min."); return

    u    = await user_get(user.id)
    st   = state_get(user.id)
    step = st.get("step", "")

    # ── Navigation ────────────────────────────────────
    if text == B["BACK2PANEL"] and user.id in ADMIN_IDS:
        state_clear(user.id)
        await reply(update, panel("Admin Panel", ["Select an action:"]), kb=kb_admin_panel()); return

    if text in (B["CANCEL"], B["BACK"], B["BACK2MENU"], B["CLOSE"]):
        state_clear(user.id)
        await reply(update, "Back to main menu.", kb=kb_for(u)); return

    # ════════════════════════════════════════════════
    #  FSM STEPS
    # ════════════════════════════════════════════════

    if step == "await_key":
        state_clear(user.id)
        code = text.upper().replace(" ", "")
        ok, msg = await key_redeem(code, user.id)
        u = await user_get(user.id)
        if ok:
            await reply(update, panel("Key Redeemed", [
                section("Duration", f"<b>{msg}</b>"),
                section("Expires",  f"<code>{expiry_str(u)}</code>"),
                "", "Premium access is now active.",
            ]), kb=kb_for(u))
        else:
            await reply(update, panel("Redeem Failed", [msg]), kb=kb_for(u))
        return

    if step == "await_feedback":
        state_clear(user.id)
        uname = user.username or str(user.id)
        await feedback_add(user.id, uname, text)
        for aid in ADMIN_IDS:
            try:
                await ctx.bot.send_message(aid, panel("New Feedback", [
                    section("From", f"@{uname} (<code>{user.id}</code>)"),
                    f"<i>{text[:500]}</i>",
                ]), parse_mode=ParseMode.HTML)
            except Exception:
                pass
        await reply(update, panel("Feedback Sent", [
            "Thank you. Your feedback has been received.",
            "The owner will review it shortly.",
        ]), kb=kb_for(u)); return

    # Admin FSM steps
    if step == "await_broadcast" and user.id in ADMIN_IDS:
        state_clear(user.id)
        await _do_broadcast(update, ctx, text); return

    if step == "await_genkey_count" and user.id in ADMIN_IDS:
        try:
            n = max(1, min(int(text), 20))
        except ValueError:
            await reply(update, "Enter a number between 1 and 20:", kb=kb_panel_cancel()); return
        state_set(user.id, step="await_genkey_dur", gen_count=n)
        await reply(update, panel(f"Generate {n} Key(s)", ["Choose duration:"]), kb=kb_dur()); return

    if step == "await_genkey_dur" and user.id in ADMIN_IDS:
        raw = text.lower()
        dur = DURATION_ALIASES.get(raw, raw)
        if dur not in DURATION_MAP:
            for k, (lbl, _) in DURATION_MAP.items():
                if lbl.lower() == raw:
                    dur = k; break
        if dur not in DURATION_MAP:
            await reply(update, "Not recognized. Choose from the menu:", kb=kb_dur()); return
        n = st.get("gen_count", 1)
        codes = []
        for _ in range(n):
            code = make_key()
            rec  = await key_create(code, dur, by=user.id)
            codes.append(f"<code>{code}</code>  — {rec['duration_label']}")
        state_clear(user.id)
        await reply(update, panel(f"{n} Key(s) Generated", codes + ["", "Claim window: 7 days."]), kb=kb_admin_panel()); return

    if step == "await_del_key" and user.id in ADMIN_IDS:
        state_clear(user.id)
        code = text.upper().strip()
        ok   = await key_delete(code)
        await reply(update, panel("Delete Key", [
            f"{'Deleted' if ok else 'Not found'}: <code>{code}</code>"
        ]), kb=kb_admin_panel()); return

    if step == "await_search_user" and user.id in ADMIN_IDS:
        state_clear(user.id)
        q    = text.lstrip("@").lower()
        all_ = await user_all()
        found = [x for x in all_ if
                 q in str(x.get("user_id", "")) or
                 q in (x.get("username") or "").lower() or
                 q in (x.get("first_name") or "").lower()]
        if not found:
            await reply(update, "No user found.", kb=kb_admin_panel()); return
        lines = []
        for x in found[:8]:
            un  = f"@{x['username']}" if x.get("username") else f"ID:{x['user_id']}"
            exp = expiry_str(x) if is_premium(x) else "Guest"
            lines += [
                f"<b>{un}</b>  ({x.get('first_name', '')})",
                f"  ID     : <code>{x['user_id']}</code>",
                f"  Status : {exp}",
                f"  Gens   : {x.get('gen_count', 0):,}",
                f"  Banned : {'Yes' if x.get('banned') else 'No'}",
                "",
            ]
        await reply(update, panel(f"Search — {len(found)} result(s)", lines), kb=kb_admin_panel()); return

    if step == "await_ext_uid" and user.id in ADMIN_IDS:
        try:
            target = int(text.strip())
        except ValueError:
            await reply(update, "Invalid user ID.", kb=kb_panel_cancel()); return
        state_set(user.id, step="await_ext_dur", target_uid=target)
        await reply(update, panel("Extend Premium", [
            f"User ID: <code>{target}</code>", "", "Choose duration to add:",
        ]), kb=kb_dur()); return

    if step == "await_ext_dur" and user.id in ADMIN_IDS:
        raw = text.lower()
        dur = DURATION_ALIASES.get(raw, raw)
        if dur not in DURATION_MAP:
            for k, (lbl, _) in DURATION_MAP.items():
                if lbl.lower() == raw:
                    dur = k; break
        if dur not in DURATION_MAP:
            await reply(update, "Not recognized. Choose from the menu:", kb=kb_dur()); return
        target = st.get("target_uid")
        state_clear(user.id)
        label, days = DURATION_MAP[dur]
        now  = int(time.time())
        tu   = await user_get(target)
        if not tu:
            await reply(update, f"User <code>{target}</code> not found.", kb=kb_admin_panel()); return
        base    = max(now, _clamp_ts(tu.get("premium_expiry", 0) or 0))
        new_exp = min(int(base + days * 86400), MAX_TS)
        await user_set_premium(target, new_exp)
        tu = await user_get(target)
        try:
            await ctx.bot.send_message(target, panel("Premium Extended", [
                section("Added",   f"<b>{label}</b>"),
                section("Expires", f"<code>{expiry_str(tu)}</code>"),
            ]), parse_mode=ParseMode.HTML)
        except Exception:
            pass
        await reply(update, panel("Premium Extended", [
            section("User",    f"<code>{target}</code>"),
            section("Added",   label),
            section("Expires", expiry_str(tu)),
        ]), kb=kb_admin_panel()); return

    if step == "await_revoke_uid" and user.id in ADMIN_IDS:
        state_clear(user.id)
        try:
            target = int(text.strip())
        except ValueError:
            await reply(update, "Invalid user ID.", kb=kb_panel_cancel()); return
        await user_revoke(target)
        await reply(update, panel("Revoke Premium", [
            f"Premium revoked for <code>{target}</code>."
        ]), kb=kb_admin_panel()); return

    if step == "await_ban_uid" and user.id in ADMIN_IDS:
        state_clear(user.id)
        try:
            target = int(text.strip())
        except ValueError:
            await reply(update, "Invalid user ID.", kb=kb_panel_cancel()); return
        banning = st.get("banning", True)
        await user_ban(target, banning)
        action = "Banned" if banning else "Unbanned"
        await reply(update, panel(action, [
            f"User <code>{target}</code> has been {action.lower()}."
        ]), kb=kb_admin_panel()); return

    # Add Stock: source picker
    if step == "await_add_stock_src" and user.id in ADMIN_IDS:
        # Match against "Source Name [count]" format or plain source name
        chosen = None
        clean = text.split("[")[0].strip().lower()
        for s in SOURCES:
            if src_label(s).lower() == clean:
                chosen = s; break
        if not chosen:
            await reply(update, "Pick a source from the buttons:", kb=kb_sources_stock()); return
        state_set(user.id, step="await_add_stock_file", add_src=chosen)
        await reply(update, panel(f"Add Stock — {src_label(chosen)}", [
            f"Current stock: <b>{stock(chosen):,} lines</b>",
            "",
            "Send a .txt file with accounts to add.",
            "One account per line. Duplicates are not filtered here.",
            "",
            "Tap Cancel to abort.",
        ]), kb=kb_panel_cancel()); return

    # ── Data gen FSM ──────────────────────────────────
    if step == "await_src":
        src_map = {src_label(s).lower(): s for s in SOURCES}
        chosen  = src_map.get(text.lower())
        if not chosen:
            await reply(update, "Choose a source from the menu:", kb=kb_sources()); return
        avail = stock(chosen)
        if avail == 0:
            await reply(update, f"No data available for <b>{text}</b> right now. Pick another:", kb=kb_sources()); return
        state_set(user.id, step="await_lines", src=chosen, avail=avail)
        await reply(update, panel(f"{src_label(chosen)}", [
            section("Lines available", f"<b>{avail:,}</b>"),
            "",
            "How many lines do you want?",
        ]), kb=kb_lines()); return

    if step == "await_lines":
        try:
            n = int(text.replace(",", "").strip())
        except ValueError:
            await reply(update, "Choose from the menu:", kb=kb_lines()); return
        src   = st.get("src", "")
        avail = st.get("avail", 0)
        n     = min(n, avail)
        state_set(user.id, step="await_fmt", src=src, avail=avail, lines_n=n)
        await reply(update, panel("Choose Output Format", [
            section("Source", f"<b>{src_label(src)}</b>"),
            section("Lines",  f"<b>{n:,}</b>"),
            "",
            "<b>Raw</b>",
            "  Every line exactly as stored in the source.",
            "",
            "<b>User:Pass</b>",
            "  Only lines matching a user:pass pattern.",
            "",
            "Pick a format:",
        ]), kb=kb_format()); return

    if step == "await_fmt":
        fmt = None
        if text == FORMAT_RAW:
            fmt = FORMAT_RAW
        elif text == FORMAT_USERPASS:
            fmt = FORMAT_USERPASS
        if fmt is None:
            await reply(update, "Choose a format using the buttons:", kb=kb_format()); return
        src   = st.get("src", "")
        n     = st.get("lines_n", 100)
        avail = st.get("avail", 0)
        state_clear(user.id)
        n = min(n, avail)
        try:
            await update.effective_chat.send_chat_action(ChatAction.UPLOAD_DOCUMENT)
        except Exception:
            pass
        loop      = asyncio.get_running_loop()
        raw_lines = await loop.run_in_executor(EXECUTOR, _sample_lines, src, n)
        if not raw_lines:
            await reply(update, "Generation failed. Source may be empty.", kb=kb_for(u)); return
        lines, was_filtered = _apply_fmt(raw_lines, fmt)
        if was_filtered and not lines:
            await reply(update, panel("No Matches Found", [
                section("Source",  f"<b>{src_label(src)}</b>"),
                section("Sampled", f"<b>{len(raw_lines):,}</b> lines"),
                "",
                "None matched User:Pass format.",
                "Try Raw format or a different source.",
            ]), kb=kb_for(u)); return
        buf = _make_gen_file(src, lines, fmt)
        await user_inc_gen(user.id)
        u   = await user_get(user.id)
        fmt_label = "User:Pass" if fmt == FORMAT_USERPASS else "Raw"
        caption = panel(f"{src_label(src)} — {fmt_label}", [
            section("Delivered",   f"<b>{len(lines):,} lines</b>"),
            section("Format",      f"<b>{fmt_label}</b>"),
            section("Total gens",  f"<b>{u.get('gen_count', 0):,}</b>"),
            "",
            "Lines have been removed from the source after delivery.",
            f"Owner: {OWNER_USERNAME}",
        ])
        await send_file(update, buf, caption, kb=kb_for(u))
        # Remove delivered lines from source (background)
        src_p = _src_path(src)
        if src_p:
            new_count = await loop.run_in_executor(EXECUTOR, _remove_sent, src_p, raw_lines)
            if new_count >= 0:
                _STOCK[src] = new_count
                # Low stock notification
                if new_count < LOW_STOCK_THRESHOLD:
                    asyncio.create_task(_notify_low_stock(ctx.bot, src, new_count))
        return

    # ── Tool FSM ──────────────────────────────────────
    if step and step.startswith("tool_"):
        await _handle_tool(update, ctx, u, st, text); return

    # ════════════════════════════════════════════════
    #  MENU BUTTONS
    # ════════════════════════════════════════════════

    if text == B["REDEEM"]:
        state_set(user.id, step="await_key")
        await reply(update, panel("Redeem Key", [
            "Send your key code below.",
            "",
            "Format: <code>ICHI-XXXXXXXX-XXXXXXXX-XXXXXXXX</code>",
        ]), kb=kb_cancel()); return

    if text == B["BUY"]:
        await reply(update, panel("Buy a Key", [
            "Contact the owner to purchase premium access.",
            "",
            "<b>Plans available:</b>",
            "1 Hour, 6H, 12H, 1 Day, 3 Day, 7 Day,",
            "14 Day, 1 Month, 3 Month, 6 Month, 1 Year, Lifetime",
            "",
            section("Owner",   OWNER_USERNAME),
            section("Contact", SUPPORT_URL),
        ]), kb=kb_for(u)); return

    if text == B["INFO"]:
        await _show_info(update, u); return

    if text == B["SUPPORT"]:
        await reply(update, panel("Contact Support", [
            "Need help or have a question?",
            "",
            section("Owner",   OWNER_USERNAME),
            section("Contact", SUPPORT_URL),
            "",
            "You can also use Send Feedback to message the owner directly.",
        ]), kb=kb_for(u)); return

    if text == B["FEEDBACK"]:
        if not is_premium(u) and user.id not in ADMIN_IDS:
            await reply(update, "Premium access required.", kb=kb_guest()); return
        state_set(user.id, step="await_feedback")
        await reply(update, panel("Send Feedback", [
            "Share a suggestion, bug report, or anything on your mind.",
            "The owner reads everything — be as detailed as you like.",
        ]), kb=kb_cancel()); return

    if text == B["ACCOUNT"]:
        await cmd_account(update, ctx); return

    if text == B["GENFILES"]:
        if not is_premium(u) and user.id not in ADMIN_IDS:
            await reply(update, "Premium access required.\n\nRedeem or buy a key to unlock.", kb=kb_guest()); return
        state_set(user.id, step="await_src")
        await reply(update, GUIDE_GEN(), kb=kb_sources()); return

    if text == B["TOOLS"]:
        if not is_premium(u) and user.id not in ADMIN_IDS:
            await reply(update, "Premium access required.\n\nRedeem or buy a key to unlock.", kb=kb_guest()); return
        await reply(update, GUIDE_TOOLS, kb=kb_tools()); return

    if text in BUILTIN_TOOLS:
        if not is_premium(u) and user.id not in ADMIN_IDS:
            await reply(update, "Premium access required.", kb=kb_guest()); return
        await _start_tool(update, u, text); return

    # ── Admin Panel ───────────────────────────────────
    if text == B["ADMIN"]:
        if user.id not in ADMIN_IDS:
            return
        await reply(update, panel("Admin Panel", [
            "Manage keys, users, database, and system settings.",
            "",
            "Keys     — generate, list, delete, extend",
            "Users    — list, search, ban, revoke",
            "Stock    — view and add account data",
            "System   — broadcast, stats, maintenance",
        ]), kb=kb_admin_panel()); return

    if text == B["GENKEY"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_genkey_count")
        await reply(update, panel("Generate Key", ["How many keys? (1–20):"]), kb=kb_panel_cancel()); return

    if text == B["KEY_LIST"] and user.id in ADMIN_IDS:
        keys   = await key_all()
        unused = [k for k in keys if not k["used"]]
        lines  = [
            section("Total",  str(len(keys))),
            section("Unused", str(len(unused))),
            section("Used",   str(len(keys) - len(unused))),
            "",
        ]
        for k in sorted(unused, key=lambda x: x.get("created_at", 0), reverse=True)[:15]:
            lines.append(f"<code>{k['code']}</code>  — {k['duration_label']}")
        if len(unused) > 15:
            lines.append(f"... and {len(unused)-15} more")
        await reply(update, panel("Unused Keys", lines), kb=kb_admin_panel()); return

    if text == B["DEL_KEY"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_del_key")
        await reply(update, panel("Delete Key", ["Send the key code to delete:"]), kb=kb_panel_cancel()); return

    if text == B["EXT_PREM"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_ext_uid")
        await reply(update, panel("Extend Premium", ["Send the user ID:"]), kb=kb_panel_cancel()); return

    if text == B["REVOKE_USER"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_revoke_uid")
        await reply(update, panel("Revoke Premium", ["Send the user ID:"]), kb=kb_panel_cancel()); return

    if text == B["BAN_USER"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_ban_uid", banning=True)
        await reply(update, panel("Ban User", ["Send the user ID:"]), kb=kb_panel_cancel()); return

    if text == B["UNBAN_USER"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_ban_uid", banning=False)
        await reply(update, panel("Unban User", ["Send the user ID:"]), kb=kb_panel_cancel()); return

    if text == B["SEARCH_USER"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_search_user")
        await reply(update, panel("Search User", ["Enter username or user ID:"]), kb=kb_panel_cancel()); return

    if text == B["DB_STATS"] and user.id in ADMIN_IDS:
        await cmd_stats(update, ctx); return

    if text == B["DB_STOCK"] and user.id in ADMIN_IDS:
        await _show_db_stock(update); return

    if text == B["ADD_STOCK"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_add_stock_src")
        await reply(update, panel("Add Stock", [
            "Pick the source you want to add lines to.",
            "Numbers in brackets show current stock.",
        ]), kb=kb_sources_stock()); return

    if text == B["USER_LIST"] and user.id in ADMIN_IDS:
        users = await user_all()
        prem  = sum(1 for x in users if is_premium(x))
        lines = [
            section("Total",   f"{len(users):,}"),
            section("Premium", f"{prem:,}"),
            section("Guest",   f"{len(users) - prem:,}"),
            "",
        ]
        for x in sorted(users, key=lambda y: y.get("joined", 0), reverse=True)[:20]:
            un  = f"@{x['username']}" if x.get("username") else f"ID:{x['user_id']}"
            tag = "[P]" if is_premium(x) else "[G]"
            ban = " [BAN]" if x.get("banned") else ""
            lines.append(f"{tag}{ban} {un}  {x.get('first_name', '')}")
        if len(users) > 20:
            lines.append(f"... and {len(users)-20} more")
        await reply(update, panel("User List", lines), kb=kb_admin_panel()); return

    if text == B["BROADCAST"] and user.id in ADMIN_IDS:
        state_set(user.id, step="await_broadcast")
        await reply(update, panel("Broadcast", ["Type your message:"]), kb=kb_panel_cancel()); return

    if text == B["MAINT_ON"] and user.id in ADMIN_IDS:
        await meta_set("maintenance", True)
        await meta_set("maintenance_reason", "Bot is temporarily under maintenance. Please check back soon.")
        await reply(update, panel("Maintenance ON", ["All non-admin users are now blocked."]), kb=kb_admin_panel()); return

    if text == B["MAINT_OFF"] and user.id in ADMIN_IDS:
        await meta_set("maintenance", False)
        await reply(update, panel("Maintenance OFF", ["Bot is open to all users."]), kb=kb_admin_panel()); return

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOOL HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _start_tool(update: Update, u: dict, tool_name: str) -> None:
    uid  = update.effective_user.id
    slug = "tool_" + re.sub(r"[^a-z0-9]", "_", tool_name.lower())
    state_set(uid, step=slug, tool=tool_name, substep="text")
    guide = TOOL_GUIDES.get(tool_name)
    await reply(update, guide or panel(tool_name, ["Send your input:"]), kb=kb_cancel())

async def _handle_tool(update: Update, ctx, u: dict, st: dict, text: str) -> None:
    tool    = st.get("tool", "")
    uid     = update.effective_user.id
    substep = st.get("substep", "text")

    # ASCII Maker — single step
    if tool == B["T_ASCII"]:
        state_clear(uid)
        result = tool_ascii(text)
        await reply(update, f"<b>ASCII Art</b>\nInput: <code>{text[:20]}</code>\n\n{result}", kb=kb_tools())
        return

    # Split — two steps
    if tool == B["T_SPLIT"]:
        if substep == "text":
            state_set(uid, step=st["step"], tool=tool, substep="count", saved=text)
            await reply(update, "Received. Enter chunk size — how many lines per part?", kb=kb_cancel()); return
        saved = st.get("saved", "")
        try:
            chunk = max(1, int(text))
        except ValueError:
            await reply(update, "Enter a number.", kb=kb_cancel()); return
        state_clear(uid)
        parts = tool_split(saved, chunk)
        if not parts:
            await reply(update, "No data to split.", kb=kb_tools()); return
        if len(parts) == 1:
            buf = BytesIO(parts[0].encode("utf-8")); buf.name = "split_1.txt"
            await send_file(update, buf, f"Split complete — 1 part, {chunk} lines per chunk.", kb=kb_tools())
        else:
            zb = BytesIO()
            with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, c in enumerate(parts, 1):
                    zf.writestr(f"part_{i:03d}.txt", c)
            zb.seek(0); zb.name = f"split_{len(parts)}_parts.zip"
            await send_file(update, zb, f"Split complete — {len(parts)} parts, {chunk} lines each.", kb=kb_tools())
        return

    # Single-step tools
    state_clear(uid)
    if tool == B["T_EXTRACT"]:
        result, count = tool_extract(text)
        if not result:
            await reply(update, "No user:pass pairs found.", kb=kb_tools()); return
        await _send_tool_result(update, "Userpass Extractor", f"Found {count:,} pairs.", result)

    elif tool == B["T_DEDUP"]:
        result, before, after = tool_dedup(text)
        removed = before - after
        await _send_tool_result(update, "Remove Duplicate",
            f"Before: {before:,}  After: {after:,}  Removed: {removed:,}", result)

    else:
        await reply(update, "Unknown tool.", kb=kb_tools())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DOCUMENT HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    u    = await user_get(user.id)
    doc  = update.message.document
    if not doc:
        return

    st   = state_get(user.id)
    step = st.get("step", "")
    tool = st.get("tool", "")

    # Admin: add stock — receive .txt file for a source
    if step == "await_add_stock_file" and user.id in ADMIN_IDS:
        src = st.get("add_src", "")
        if not src:
            await reply(update, "Something went wrong. Start over.", kb=kb_admin_panel()); return
        if not doc.file_name or not doc.file_name.lower().endswith(".txt"):
            await reply(update, "Please send a .txt file.", kb=kb_panel_cancel()); return
        state_clear(user.id)
        try:
            file = await doc.get_file()
            raw  = await file.download_as_bytearray()
            text = raw.decode("utf-8", errors="ignore")
            new_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        except Exception as e:
            await reply(update, f"Error reading file: {e}", kb=kb_admin_panel()); return

        loop  = asyncio.get_running_loop()
        added = await loop.run_in_executor(EXECUTOR, _append_to_src, src, new_lines)
        new_total = await loop.run_in_executor(EXECUTOR, _refresh_src, src)

        await reply(update, panel(f"Stock Added — {src_label(src)}", [
            section("Lines in file",  f"{len(new_lines):,}"),
            section("Lines added",    f"<b>{added:,}</b>"),
            section("New total",      f"<b>{new_total:,}</b>"),
        ]), kb=kb_admin_panel())
        return

    # Merge: collect files
    if tool == B["T_MERGE"] and doc.file_name and doc.file_name.lower().endswith(".txt"):
        files = st.get("merge_files", [])
        try:
            file = await doc.get_file()
            raw  = await file.download_as_bytearray()
            files.append(raw.decode("utf-8", errors="ignore"))
        except Exception as e:
            await reply(update, f"Error reading file: {e}"); return
        if len(files) >= 5:
            await _do_merge(update, user.id, files)
        else:
            state_set(user.id, step=step, tool=tool, substep="collect", merge_files=files)
            await reply(update, f"File {len(files)} received. Send another or tap Done.", kb=kb_done_cancel())
        return

    # Other tools: single .txt input
    if step and step.startswith("tool_") and doc.file_name and doc.file_name.lower().endswith(".txt"):
        substep = st.get("substep", "text")
        if substep == "text" and tool in BUILTIN_TOOLS and tool != B["T_MERGE"]:
            try:
                file = await doc.get_file()
                raw  = await file.download_as_bytearray()
                text = raw.decode("utf-8", errors="ignore")
            except Exception as e:
                await reply(update, f"Error: {e}"); return
            if tool == B["T_SPLIT"]:
                state_set(user.id, step=step, tool=tool, substep="count", saved=text)
                await reply(update, "File received. Enter chunk size (lines per part):", kb=kb_cancel())
            elif tool == B["T_ASCII"]:
                state_clear(user.id)
                result = tool_ascii(text[:20])
                await reply(update, f"<b>ASCII Art</b>\n\n{result}", kb=kb_tools())
            else:
                await _handle_tool(update, ctx, u, {**st}, text)

async def _do_merge(update: Update, uid: int, files: list[str]) -> None:
    state_clear(uid)
    merged = "\n".join(files)
    count  = tool_count(merged)
    buf    = BytesIO(merged.encode("utf-8"))
    buf.name = "ichigo_merged.txt"
    await send_file(update, buf,
        f"<b>Merge complete</b> — {len(files)} file(s), {count:,} total lines.",
        kb=kb_tools())

async def _intercept_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user  = update.effective_user
    st    = state_get(user.id)
    if st.get("tool") == B["T_MERGE"] and update.message.text == B["DONE"]:
        files = st.get("merge_files", [])
        if files:
            await _do_merge(update, user.id, files)
        else:
            await reply(update, "No files received yet.", kb=kb_cancel())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CALLBACK QUERY (inline button fallback)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main() -> None:
    if not BOT_TOKEN:
        log.error("BOT_TOKEN is not set. Set it as an environment variable.")
        sys.exit(1)

    log.info("Starting %s %s", BOT_NAME, BOT_VERSION)
    log.info("Admin IDs : %s", ADMIN_IDS)
    log.info("DB path   : %s", DB_PATH)
    log.info("Data dir  : %s", DATA_DIR)

    async def _post_init(app) -> None:
        await preload_sources()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(_post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("account",   cmd_account))
    app.add_handler(CommandHandler("redeem",    cmd_redeem))
    app.add_handler(CommandHandler("info",      cmd_info))
    app.add_handler(CommandHandler("genkey",    cmd_genkey))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("support",
        lambda u, c: u.message.reply_text(f"Owner: {OWNER_USERNAME}\nContact: {SUPPORT_URL}")))

    app.add_handler(CallbackQueryHandler(on_callback))

    # "Done" intercept must come before the generic text handler
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(rf"^{re.escape(B['DONE'])}$"),
        _intercept_done,
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))

    log.info("IchigoBot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
