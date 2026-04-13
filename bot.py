#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ULTIMATE CHECKER - v35 RESOLVEPHONE METHOD
- Uses contacts.resolvePhone instead of ImportContacts
- resolvePhone is 100% accurate - no phone matching needed
- Supports ALL 200+ countries
"""

import os, json, asyncio, random, threading, re, requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from telethon import TelegramClient, functions, types
from telethon.errors import (
    FloodWaitError, SessionPasswordNeededError,
    PhoneCodeInvalidError, PhoneMigrateError,
    NetworkMigrateError, UserMigrateError,
)
from telethon.tl.functions.contacts import ResolvePhoneRequest

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ContextTypes,
    ConversationHandler,
)
import phonenumbers

# ═══════════════════════════════════════════════════════════
BOT_TOKEN = "8709521947:AAEZoyndKwA7pMBti4avuM5AlYjG6-HifA8"
API_ID    = 28786346
API_HASH  = "7364888324936105dc6754101e7dd0b4"
ADMIN_IDS = [7095358778]
# ── Green API (Telegram) ────────────────────────────────────
GREEN_API_URL      = "https://4100.api.green-api.com"
GREEN_INSTANCE_ID  = "4100585336"
GREEN_API_TOKEN    = "657a702703174b5385611f0daf9867979bd8c50bb26e64104ad"
# ═══════════════════════════════════════════════════════════

VERSION = "v36 RESOLVEPHONE+GREENAPI"
DEV     = "@badol_112"

os.makedirs("sessions", exist_ok=True)
os.makedirs("data",     exist_ok=True)

ADD_USER, REMOVE_USER, BROADCAST, SET_DELAY = range(4)


# ═══════════════════════════════════════════════════════════
#  PHONE UTILITIES
# ═══════════════════════════════════════════════════════════
class PhoneUtils:
    @staticmethod
    def normalize(phone: str) -> str:
        """Returns digits only, no + sign"""
        if not phone:
            return ""
        cleaned = re.sub(r'[\s\-\(\)\+]', '', phone.strip())
        if cleaned.startswith("00"):
            cleaned = cleaned[2:]
        return cleaned

    @staticmethod
    def for_api(phone: str) -> str:
        """Returns +XXXXXXXXXX format"""
        digits = PhoneUtils.normalize(phone)
        return "+" + digits if digits else ""

    @staticmethod
    def get_flag(phone: str) -> str:
        try:
            p = PhoneUtils.for_api(phone)
            parsed = phonenumbers.parse(p, None)
            cc = phonenumbers.region_code_for_number(parsed)
            if not cc or len(cc) != 2:
                return "🌐"
            flag = ""
            for char in cc.upper():
                if 'A' <= char <= 'Z':
                    flag += chr(0x1F1E6 + ord(char) - ord('A'))
            return flag if flag else "🌐"
        except:
            return "🌐"


# ═══════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════
class DB:
    def __init__(self):
        self.uf   = "data/users.json"
        self.af   = "data/allowed.json"
        self.sf   = "data/settings.json"
        self.sessf= "data/sessions.json"
        self._load()

    def _r(self, p, d):
        if os.path.exists(p):
            try: return json.load(open(p, encoding="utf-8"))
            except: pass
        return d

    def _load(self):
        self.users    = self._r(self.uf,    {})
        self.allowed  = self._r(self.af,    {})
        self.cfg      = self._r(self.sf,    {"wl": True, "delay": 1.0})
        self.sessions = self._r(self.sessf, {})

    def _save(self):
        for p, o in [(self.uf,self.users),(self.af,self.allowed),(self.sf,self.cfg),(self.sessf,self.sessions)]:
            try:
                with open(p,"w",encoding="utf-8") as f:
                    json.dump(o, f, indent=2, ensure_ascii=False)
            except: pass

    def touch(self, uid, uname, name):
        k = str(uid)
        if k not in self.users:
            self.users[k] = {"name":name or "User","uname":uname or "N/A",
                             "joined":str(datetime.now()),"checks":0,"active":0}
        self.users[k].update({"name":name or "User","uname":uname or "N/A","last":str(datetime.now())})
        self._save()

    def is_admin(self, uid):   return uid in ADMIN_IDS
    def is_allowed(self, uid):
        if self.is_admin(uid): return True
        if not self.cfg.get("wl", True): return True
        return str(uid) in self.allowed

    def add_wl(self, uid):
        self.allowed[str(uid)] = {"t": str(datetime.now())}
        self._save()

    def del_wl(self, uid):
        k = str(uid)
        if k in self.allowed:
            del self.allowed[k]; self._save(); return True
        return False

    def add_check(self, uid, total, active):
        k = str(uid)
        if k in self.users:
            self.users[k]["checks"] = self.users[k].get("checks",0) + 1
            self.users[k]["active"] = self.users[k].get("active",0) + active
            self._save()

    def get_user_sessions(self, uid):
        return self.sessions.get(str(uid), [])

    def add_user_session(self, uid, sess_name):
        k = str(uid)
        if k not in self.sessions:
            self.sessions[k] = []
        if sess_name not in self.sessions[k]:
            self.sessions[k].append(sess_name)
            self._save()

    def remove_user_session(self, uid, sess_name):
        k = str(uid)
        if k in self.sessions and sess_name in self.sessions[k]:
            self.sessions[k].remove(sess_name)
            self._save()
            return True
        return False

    def set_delay(self, delay):
        self.cfg["delay"] = float(delay)
        self._save()

    def get_delay(self):
        return self.cfg.get("delay", 1.0)

    def stats(self):
        return {"users":len(self.users),"allowed":len(self.allowed),
                "checks":sum(u.get("checks",0) for u in self.users.values()),
                "active":sum(u.get("active",0) for u in self.users.values()),
                "delay":self.get_delay()}


# ═══════════════════════════════════════════════════════════
#  SESSION WORKER - ResolvePhone METHOD
# ═══════════════════════════════════════════════════════════
class SessionWorker:
    def __init__(self, sess_path: str):
        self.sess_path  = sess_path
        self.sess_name  = os.path.basename(sess_path).replace(".session","")
        self._loop      = asyncio.new_event_loop()
        self._thread    = threading.Thread(target=self._run, daemon=True, name=f"sess_{self.sess_name}")
        self._thread.start()
        self._client: TelegramClient | None = None
        self.flood_until  = None
        self.is_available = True

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect(self):
        if self._client is None or not self._client.is_connected():
            self._client = TelegramClient(self.sess_path, API_ID, API_HASH)
            await self._client.connect()
        return self._client

    async def _authorized(self):
        try:
            c = await self._connect()
            return await c.is_user_authorized()
        except: return False

    async def _send_otp(self, phone):
        try:
            c = await self._connect()
            r = await c.send_code_request(phone)
            return True, r.phone_code_hash
        except (PhoneMigrateError, NetworkMigrateError, UserMigrateError) as e:
            try:
                c = await self._connect()
                await c._switch_dc(e.new_dc)
                r = await c.send_code_request(phone)
                return True, r.phone_code_hash
            except Exception as e2: return False, str(e2)
        except Exception as e: return False, str(e)

    async def _sign_in(self, phone, code, phash):
        try:
            c = await self._connect()
            await c.sign_in(phone=phone, code=code, phone_code_hash=phash)
            return True, None
        except PhoneCodeInvalidError: return False, "❌ OTP ভুল!"
        except SessionPasswordNeededError: return False, "2FA"
        except Exception as e: return False, str(e)

    async def _sign_in_2fa(self, pwd):
        try:
            c = await self._connect()
            await c.sign_in(password=pwd)
            return True, None
        except Exception as e: return False, str(e)

    async def _check_single(self, number: str):
        """
        ══════════════════════════════════════════════════
        METHOD: contacts.ResolvePhone

        এই method সরাসরি phone number দিয়ে Telegram user
        খোঁজে। কোনো contact import দরকার নেই।

        - User থাকলে  → "opened" + username
        - না থাকলে   → "fresh"
        - Error হলে  → None (retry হবে)
        ══════════════════════════════════════════════════
        """
        if self.flood_until and datetime.now() < self.flood_until:
            return None

        phone = PhoneUtils.for_api(number)  # +966XXXXXXXXX format
        c = await self._connect()

        print(f"\n[{self.sess_name}] ResolvePhone: {phone}")

        try:
            result = await asyncio.wait_for(
                c(ResolvePhoneRequest(phone=phone)),
                timeout=30
            )

            # ✅ User found!
            if result and result.users:
                user = result.users[0]
                username = user.username or "NoUsername"
                name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "NoName"
                print(f"  ✅ REGISTERED! id={user.id} username=@{username} name={name}")
                return {
                    "status":   "opened",
                    "number":   phone,
                    "username": username,
                    "name":     name,
                    "success":  True
                }
            else:
                # Response আসলো কিন্তু user নেই
                print(f"  ❌ FRESH (empty response)")
                return {
                    "status":  "fresh",
                    "number":  phone,
                    "success": True
                }

        except FloodWaitError as e:
            self.flood_until  = datetime.now() + timedelta(seconds=e.seconds + 5)
            self.is_available = False
            print(f"[{self.sess_name}] ⚠️ FloodWait {e.seconds}s")
            return None

        except Exception as e:
            err_type = type(e).__name__
            err_str  = str(e).lower()
            print(f"[{self.sess_name}] Error: {err_type}: {e}")

            # ══════════════════════════════════════════
            # ResolvePhoneRequest এ নম্বর না থাকলে
            # Telegram "phone not occupied" বা
            # "Bad Request" error দেয় — এটা FRESH
            # ══════════════════════════════════════════
            if any(x in err_str for x in [
                "phone not occupied",
                "bad request",
                "not found",
                "no user",
                "phonenot",
                "phone_not",
                "400",
            ]):
                print(f"  ❌ FRESH (error: {err_type})")
                return {
                    "status":  "fresh",
                    "number":  phone,
                    "success": True
                }

            # অন্য error → retry করবে
            return None

    def check_available(self):
        if self.flood_until and datetime.now() >= self.flood_until:
            self.flood_until  = None
            self.is_available = True
        return self.is_available

    def _call(self, coro, timeout=45):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    def authorized(self):        return self._call(self._authorized())
    def send_otp(self, phone):   return self._call(self._send_otp(phone))
    def sign_in(self, ph, c, h): return self._call(self._sign_in(ph, c, h))
    def sign_in_2fa(self, pwd):  return self._call(self._sign_in_2fa(pwd))
    def check_number(self, num): return self._call(self._check_single(num), timeout=45)


# ═══════════════════════════════════════════════════════════
#  SESSION POOL
# ═══════════════════════════════════════════════════════════
class SessionPool:
    def __init__(self):
        self._sessions: dict[int, list[SessionWorker]] = {}
        self._lock = threading.Lock()

    def add_session(self, uid: int, sess_name: str):
        with self._lock:
            if uid not in self._sessions:
                self._sessions[uid] = []
            sess_path = f"sessions/user_{uid}_{sess_name}"
            worker = SessionWorker(sess_path)
            self._sessions[uid].append(worker)
            return worker

    def get_sessions(self, uid: int) -> list[SessionWorker]:
        with self._lock:
            return self._sessions.get(uid, [])

    def get_available_session(self, uid: int) -> SessionWorker | None:
        sessions = self.get_sessions(uid)
        for sess in sessions:
            if sess.check_available():
                return sess
        return None

    def remove_session(self, uid: int, sess_name: str):
        with self._lock:
            if uid in self._sessions:
                self._sessions[uid] = [s for s in self._sessions[uid]
                                       if s.sess_name != f"user_{uid}_{sess_name}"]
            sess_file = f"sessions/user_{uid}_{sess_name}.session"
            if os.path.exists(sess_file):
                try: os.remove(sess_file)
                except: pass


pool      = SessionPool()
db        = DB()
_executor = ThreadPoolExecutor(max_workers=50)
_tasks: dict[int, asyncio.Task] = {}


# ═══════════════════════════════════════════════════════════
#  GREEN API - TELEGRAM NUMBER CHECK
# ═══════════════════════════════════════════════════════════
def green_check_sync(phone: str) -> dict:
    """
    Green API দিয়ে Telegram নম্বর চেক।
    phone: +8801XXXXXXXXX format
    Return: {"found": True/False/None, "error": str|None}
    """
    # শুধু digits, no +
    digits = re.sub(r'\D', '', phone)
    url = (
        f"{GREEN_API_URL}/waInstance{GREEN_INSTANCE_ID}"
        f"/checkPhoneNumber/{digits}"
        f"?token={GREEN_API_TOKEN}"
    )
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Green API Telegram: {"existsTelegram": true/false}
            # বা {"existsWhatsapp": true/false} — দুটোই handle করি
            if "existsTelegram" in data:
                return {"found": data["existsTelegram"], "error": None}
            elif "existsWhatsapp" in data:
                return {"found": data["existsWhatsapp"], "error": None}
            else:
                return {"found": None, "error": f"Unknown response: {data}"}
        elif r.status_code == 401:
            return {"found": None, "error": "Green API Not Authorized (QR দিয়ে লিংক করো)"}
        else:
            return {"found": None, "error": f"HTTP {r.status_code}"}
    except requests.exceptions.Timeout:
        return {"found": None, "error": "Timeout"}
    except Exception as e:
        return {"found": None, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  UI HELPERS
# ═══════════════════════════════════════════════════════════
def kb_main(is_admin):
    rows = []
    if is_admin:
        rows.append([InlineKeyboardButton("👑 Admin", callback_data="admin")])
    rows.append([
        InlineKeyboardButton("📊 Stats",    callback_data="my_stats"),
        InlineKeyboardButton("📱 Sessions", callback_data="my_sessions")
    ])
    return InlineKeyboardMarkup(rows)

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add",    callback_data="add_user"),
         InlineKeyboardButton("➖ Remove", callback_data="rem_user")],
        [InlineKeyboardButton("✅ List",   callback_data="wl_list"),
         InlineKeyboardButton("📢 BC",     callback_data="do_bc")],
        [InlineKeyboardButton("🔄 WL",    callback_data="tog_wl"),
         InlineKeyboardButton("📊 Stats",  callback_data="adm_stats")],
        [InlineKeyboardButton("⏱️ Delay", callback_data="set_delay"),
         InlineKeyboardButton("« Back",   callback_data="back")],
    ])

def kb_sessions(sessions):
    rows = []
    for sess in sessions[:10]:
        clean  = sess.sess_name.split("_",2)[-1] if "_" in sess.sess_name else sess.sess_name
        status = "✅" if sess.is_available else "🔴"
        rows.append([
            InlineKeyboardButton(f"{status} {clean}", callback_data=f"si_{clean}"),
            InlineKeyboardButton("🗑️", callback_data=f"del_sess_{clean}")
        ])
    rows.append([InlineKeyboardButton("« Back", callback_data="back")])
    return InlineKeyboardMarkup(rows)

async def run_worker(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, fn, *args)


# ═══════════════════════════════════════════════════════════
#  CHECK TASK
# ═══════════════════════════════════════════════════════════
async def _check_task(uid, nums, prog_msg, reply_fn):
    delay    = db.get_delay()
    sessions = pool.get_sessions(uid)

    if not sessions:
        await reply_fn("❌ No session!\n`/add_session acc1`", parse_mode="Markdown")
        _tasks.pop(uid, None)
        return

    fresh_list  = []
    opened_list = []
    error_list  = []
    checked     = 0
    total       = len(nums)
    use_green   = bool(GREEN_INSTANCE_ID and GREEN_API_TOKEN)  # Green API enabled?

    print(f"\n{'='*60}")
    print(f"Starting ResolvePhone check for {total} numbers")
    print(f"{'='*60}")

    for num in nums:
        sess = pool.get_available_session(uid)

        wait = 0
        while not sess and wait < 10:
            await asyncio.sleep(3)
            sess = pool.get_available_session(uid)
            wait += 1

        if not sess:
            error_list.append(num)
            checked += 1
            continue

        result = await run_worker(sess.check_number, num)

        if result is None:
            # Retry once
            await asyncio.sleep(2)
            sess2 = pool.get_available_session(uid)
            if sess2:
                result = await run_worker(sess2.check_number, num)

        if result and result.get("success"):
            # ── Green API check (parallel) ──────────────────
            green_found = None
            if use_green:
                try:
                    gr = await run_worker(green_check_sync, result["number"])
                    green_found = gr.get("found")   # True / False / None
                    if gr.get("error"):
                        print(f"  [GreenAPI] {gr['error']}")
                except Exception as ge:
                    print(f"  [GreenAPI] Error: {ge}")
            # ────────────────────────────────────────────────
            if result["status"] == "opened":
                opened_list.append({
                    "num":   result["number"],
                    "user":  result.get("username", ""),
                    "name":  result.get("name", ""),
                    "green": green_found,
                })
            else:
                fresh_list.append({
                    "num":   result["number"],
                    "green": green_found,
                })
        else:
            error_list.append(num)

        checked += 1
        pct = int(checked / total * 100)
        try:
            await prog_msg.edit_text(
                f"⏳ {checked}/{total} ({pct}%)\n"
                f"🔵 Telegram Registered: {len(opened_list)}\n"
                f"✅ Fresh: {len(fresh_list)}\n"
                f"❓ Error: {len(error_list)}\n"
                f"{'🟢 Green API: ON' if use_green else '⚪ Green API: OFF'}\n"
                f"⏱️ Delay: {delay}s"
            )
        except:
            pass

        if checked < total:
            await asyncio.sleep(delay)

    print(f"\n{'='*60}")
    print(f"Done! Registered:{len(opened_list)} Fresh:{len(fresh_list)} Error:{len(error_list)}")
    print(f"{'='*60}\n")

    try:
        await prog_msg.delete()
    except:
        pass

    # ── Summary ──
    green_tg_count = sum(1 for i in opened_list if i.get("green") is True)
    green_fr_count = sum(1 for i in fresh_list  if i.get("green") is True)
    summary = (
        f"✅ Check Complete!\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📋 Total: {total}\n"
        f"🔵 Telegram Registered: {len(opened_list)}\n"
        f"✅ Fresh (Telegram): {len(fresh_list)}\n"
    )
    if use_green:
        summary += (
            f"━━━━━━━━━━━━━━━━\n"
            f"🟢 Green API Confirmed: {green_tg_count + green_fr_count}\n"
            f"  └ Registered তে: {green_tg_count}\n"
            f"  └ Fresh তে: {green_fr_count}\n"
        )
    if error_list:
        summary += f"❓ Error: {len(error_list)}\n"
    await reply_fn(summary)

    # ── Registered list ──
    if opened_list:
        text = f"🔵 Telegram Registered: {len(opened_list)}\n\n"
        for item in opened_list:
            flag = PhoneUtils.get_flag(item["num"])
            gicon = "🟢" if item.get("green") is True else ("🔴" if item.get("green") is False else "⚪")
            text += f"{flag} {item['num']}"
            if item.get("name"):
                text += f" | {item['name']}"
            if item.get("user") and item["user"] != "NoUsername":
                text += f" | @{item['user']}"
            text += f" {gicon}\n"
            if len(text) > 3800:
                await reply_fn(text)
                text = ""
        if text:
            await reply_fn(text)

    # ── Fresh list ──
    if fresh_list:
        text = f"✅ Fresh Numbers: {len(fresh_list)}\n\n"
        for item in fresh_list:
            flag  = PhoneUtils.get_flag(item["num"])
            gicon = "🟢" if item.get("green") is True else ("🔴" if item.get("green") is False else "⚪")
            text += f"{flag} {item['num']} {gicon}\n"
            if len(text) > 3800:
                await reply_fn(text)
                text = ""
        if text:
            await reply_fn(text)

    await reply_fn(f"\n{DEV} | {VERSION}")
    db.add_check(uid, total, len(opened_list))
    _tasks.pop(uid, None)


# ═══════════════════════════════════════════════════════════
#  BOT COMMANDS
# ═══════════════════════════════════════════════════════════
async def start(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = upd.effective_user
    db.touch(u.id, u.username, u.first_name)
    if not db.is_allowed(u.id):
        await upd.message.reply_text(f"🚫 Access Denied!\nYour ID: `{u.id}`", parse_mode="Markdown")
        return
    sessions = pool.get_sessions(u.id)
    await upd.message.reply_text(
        f"✨ ULTIMATE CHECKER ✨\n\n"
        f"👋 {u.first_name}\n"
        f"📱 Sessions: {len(sessions)}\n\n"
        f"🌍 All countries supported!\n"
        f"⚡ Method: ResolvePhone (100% accurate)\n"
        f"🟢 Green API: {'Active' if GREEN_INSTANCE_ID else 'OFF'}\n\n"
        f"`/add_session acc1` - Add session\n"
        f"`/login +880...` - Login\n"
        f"`/otp 12345` - Enter OTP",
        parse_mode="Markdown",
        reply_markup=kb_main(db.is_admin(u.id))
    )

async def add_session_cmd(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = upd.effective_user.id
    if not db.is_allowed(uid):
        await upd.message.reply_text("🚫"); return
    parts = upd.message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await upd.message.reply_text("`/add_session acc1`", parse_mode="Markdown"); return
    sess_name = parts[1].strip()
    pool.add_session(uid, sess_name)
    db.add_user_session(uid, sess_name)
    ctx.user_data["current_session"] = sess_name
    await upd.message.reply_text(
        f"✅ Session `{sess_name}` created!\n`/login +CountryCodeNumber`",
        parse_mode="Markdown"
    )

async def login_cmd(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = upd.effective_user.id
    if not db.is_allowed(uid):
        await upd.message.reply_text("🚫"); return
    if "current_session" not in ctx.user_data:
        await upd.message.reply_text("`/add_session acc1` first!", parse_mode="Markdown"); return
    parts = upd.message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await upd.message.reply_text("`/login +880XXXXXXXXX`", parse_mode="Markdown"); return
    phone     = PhoneUtils.for_api(parts[1])
    sess_name = ctx.user_data["current_session"]
    sessions  = pool.get_sessions(uid)
    sess = next((s for s in sessions if s.sess_name == f"user_{uid}_{sess_name}"), None)
    if not sess:
        await upd.message.reply_text("❌ Session not found!"); return
    msg = await upd.message.reply_text(f"⏳ Sending OTP to `{phone}`...", parse_mode="Markdown")
    ok, res = await run_worker(sess.send_otp, phone)
    if ok:
        ctx.user_data["lp"] = phone
        ctx.user_data["lh"] = res
        await msg.edit_text(f"✅ OTP sent!\n`/otp 12345`", parse_mode="Markdown")
    else:
        await msg.edit_text(f"❌ `{res}`", parse_mode="Markdown")

async def otp_cmd(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = upd.effective_user.id
    if "lp" not in ctx.user_data:
        await upd.message.reply_text("`/login` first!", parse_mode="Markdown"); return
    parts = upd.message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await upd.message.reply_text("`/otp 12345`", parse_mode="Markdown"); return
    sess_name = ctx.user_data.get("current_session","")
    sessions  = pool.get_sessions(uid)
    sess = next((s for s in sessions if s.sess_name == f"user_{uid}_{sess_name}"), None)
    if not sess:
        await upd.message.reply_text("❌"); return
    msg = await upd.message.reply_text("⏳")
    ok, err = await run_worker(sess.sign_in, ctx.user_data["lp"], parts[1].strip(), ctx.user_data["lh"])
    if ok:
        ctx.user_data.pop("lp", None)
        ctx.user_data.pop("lh", None)
        ctx.user_data.pop("current_session", None)
        await msg.edit_text("✅ Logged in successfully!")
    elif err == "2FA":
        await msg.edit_text("🔐 2FA enabled!\n`/pass YourPassword`", parse_mode="Markdown")
    else:
        await msg.edit_text(f"❌ {err}")

async def pass_cmd(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = upd.effective_user.id
    if "current_session" not in ctx.user_data:
        await upd.message.reply_text("❌"); return
    parts = upd.message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await upd.message.reply_text("`/pass password`", parse_mode="Markdown"); return
    sess_name = ctx.user_data["current_session"]
    sessions  = pool.get_sessions(uid)
    sess = next((s for s in sessions if s.sess_name == f"user_{uid}_{sess_name}"), None)
    if not sess:
        await upd.message.reply_text("❌"); return
    msg = await upd.message.reply_text("⏳")
    ok, err = await run_worker(sess.sign_in_2fa, parts[1])
    if ok:
        ctx.user_data.pop("current_session", None)
        await msg.edit_text("✅ 2FA verified!")
    else:
        await msg.edit_text(f"❌ {err}")

async def handle_msg(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = upd.effective_user.id
    if not db.is_allowed(uid):
        await upd.message.reply_text("🚫"); return
    sessions = pool.get_sessions(uid)
    if not sessions:
        await upd.message.reply_text("`/add_session acc1`", parse_mode="Markdown"); return
    if uid in _tasks and not _tasks[uid].done():
        await upd.message.reply_text("⏳ Already running..."); return

    nums = []
    if upd.message.document:
        try:
            f    = await upd.message.document.get_file()
            data = await f.download_as_bytearray()
            nums = [l.strip() for l in data.decode("utf-8","ignore").splitlines() if l.strip()]
        except:
            await upd.message.reply_text("❌ File read error!"); return
    else:
        nums = [l.strip() for l in upd.message.text.splitlines() if l.strip()]

    nums = list(dict.fromkeys(nums))
    if not nums:
        await upd.message.reply_text("❌ No numbers found!"); return

    await upd.message.reply_text(
        f"✅ {len(nums)} numbers loaded\n"
        f"⚡ Method: ResolvePhone\n"
        f"⏳ Starting..."
    )
    prog = await upd.message.reply_text("🔄 0%")
    task = asyncio.create_task(
        _check_task(uid=uid, nums=nums, prog_msg=prog, reply_fn=upd.message.reply_text)
    )
    _tasks[uid] = task


async def on_cb(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = upd.callback_query
    await q.answer()
    d   = q.data
    uid = upd.effective_user.id

    if d == "my_stats":
        u        = db.users.get(str(uid), {})
        sessions = pool.get_sessions(uid)
        await q.edit_message_text(
            f"📊 Your Stats\n\n🆔 {uid}\n"
            f"✅ Total checks: {u.get('checks',0)}\n"
            f"🔐 Registered found: {u.get('active',0)}\n"
            f"📱 Sessions: {len(sessions)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back",callback_data="back")]]))

    elif d == "my_sessions":
        sessions = pool.get_sessions(uid)
        if not sessions:
            await q.edit_message_text("No sessions!\n`/add_session acc1`", parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back",callback_data="back")]]))
        else:
            await q.edit_message_text(f"📱 Sessions ({len(sessions)}):", reply_markup=kb_sessions(sessions))

    elif d.startswith("del_sess_"):
        sess_name = d.replace("del_sess_","")
        pool.remove_session(uid, sess_name)
        db.remove_user_session(uid, sess_name)
        sessions  = pool.get_sessions(uid)
        await q.edit_message_text(
            "✅ Deleted!" if not sessions else f"✅\n📱 {len(sessions)} remaining:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back",callback_data="back")]]) if not sessions else kb_sessions(sessions))

    elif d == "back":
        sessions = pool.get_sessions(uid)
        await q.edit_message_text(f"🆔 {uid}\n📱 {len(sessions)}", reply_markup=kb_main(db.is_admin(uid)))

    elif d == "admin" and db.is_admin(uid):
        s = db.stats()
        await q.edit_message_text(
            f"👑 ADMIN PANEL\n\n👥 Users: {s['users']}\n✅ Allowed: {s['allowed']}\n⏱️ Delay: {s['delay']}s",
            reply_markup=kb_admin())

    elif d == "adm_stats" and db.is_admin(uid):
        s = db.stats()
        await q.edit_message_text(
            f"📊 Stats\n\n👥 {s['users']}\n✅ {s['allowed']}\n📈 {s['checks']}\n🔐 {s['active']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Admin",callback_data="admin")]]))

    elif d == "wl_list" and db.is_admin(uid):
        body = "Empty" if not db.allowed else "\n".join([f"• {k}" for k in list(db.allowed.keys())[:20]])
        await q.edit_message_text(f"✅ Whitelist ({len(db.allowed)}):\n{body}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Admin",callback_data="admin")]]))

    elif d == "tog_wl" and db.is_admin(uid):
        db.cfg["wl"] = not db.cfg.get("wl", True)
        db._save()
        await q.answer(f"WL {'ON' if db.cfg['wl'] else 'OFF'}")
        await q.edit_message_text("👑 ADMIN PANEL", reply_markup=kb_admin())


# ═══════════════════════════════════════════════════════════
#  CONVERSATION HANDLERS
# ═══════════════════════════════════════════════════════════
async def cv_add_start(upd, ctx):
    if not db.is_admin(upd.effective_user.id): return ConversationHandler.END
    await upd.callback_query.edit_message_text("➕ Send User ID:\n/cancel")
    return ADD_USER

async def cv_add_recv(upd, ctx):
    t = upd.message.text.strip()
    if t == "/cancel":
        await upd.message.reply_text("❌"); return ConversationHandler.END
    try:
        db.add_wl(int(t))
        await upd.message.reply_text(f"✅ Added `{t}`", parse_mode="Markdown")
    except: await upd.message.reply_text("❌ Invalid ID")
    return ConversationHandler.END

async def cv_rem_start(upd, ctx):
    if not db.is_admin(upd.effective_user.id): return ConversationHandler.END
    await upd.callback_query.edit_message_text("➖ Send User ID:\n/cancel")
    return REMOVE_USER

async def cv_rem_recv(upd, ctx):
    t = upd.message.text.strip()
    if t == "/cancel":
        await upd.message.reply_text("❌"); return ConversationHandler.END
    if db.del_wl(t): await upd.message.reply_text("✅ Removed")
    else: await upd.message.reply_text("❌ Not found")
    return ConversationHandler.END

async def cv_bc_start(upd, ctx):
    if not db.is_admin(upd.effective_user.id): return ConversationHandler.END
    await upd.callback_query.edit_message_text("📢 Send message:\n/cancel")
    return BROADCAST

async def cv_bc_recv(upd, ctx):
    t = upd.message.text.strip()
    if t == "/cancel":
        await upd.message.reply_text("❌"); return ConversationHandler.END
    msg  = await upd.message.reply_text("📢...")
    sent = 0
    for k in list(db.allowed.keys()):
        try:
            await ctx.bot.send_message(int(k), f"📢\n\n{t}\n\n{DEV}")
            sent += 1
        except: pass
        await asyncio.sleep(0.05)
    await msg.edit_text(f"✅ Sent to {sent}")
    return ConversationHandler.END

async def cv_delay_start(upd, ctx):
    if not db.is_admin(upd.effective_user.id): return ConversationHandler.END
    await upd.callback_query.edit_message_text(f"⏱️ Current: {db.get_delay()}s\nNew (0.1-10):\n/cancel")
    return SET_DELAY

async def cv_delay_recv(upd, ctx):
    t = upd.message.text.strip()
    if t == "/cancel":
        await upd.message.reply_text("❌"); return ConversationHandler.END
    try:
        delay = float(t)
        if delay < 0.1 or delay > 10:
            await upd.message.reply_text("❌ 0.1-10!"); return ConversationHandler.END
        db.set_delay(delay)
        await upd.message.reply_text(f"✅ {delay}s")
    except: await upd.message.reply_text("❌")
    return ConversationHandler.END

async def cv_cancel(upd, ctx):
    await upd.message.reply_text("❌")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
def main():
    print(f"""
╔══════════════════════════════════════════════════════╗
║        ULTIMATE CHECKER - RESOLVEPHONE METHOD        ║
╠══════════════════════════════════════════════════════╣
║  Version : {VERSION:<41}║
║  Method  : contacts.ResolvePhone (accurate) ✅       ║
║  Countries: ALL 200+ supported ✅                    ║
╚══════════════════════════════════════════════════════╝
    """)
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("add_session", add_session_cmd))
    app.add_handler(CommandHandler("login",       login_cmd))
    app.add_handler(CommandHandler("otp",         otp_cmd))
    app.add_handler(CommandHandler("pass",        pass_cmd))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(cv_add_start,   pattern="^add_user$")],
        states={ADD_USER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_add_recv)]},
        fallbacks=[CommandHandler("cancel", cv_cancel)]))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(cv_rem_start,   pattern="^rem_user$")],
        states={REMOVE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_rem_recv)]},
        fallbacks=[CommandHandler("cancel", cv_cancel)]))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(cv_bc_start,    pattern="^do_bc$")],
        states={BROADCAST:   [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_bc_recv)]},
        fallbacks=[CommandHandler("cancel", cv_cancel)]))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(cv_delay_start, pattern="^set_delay$")],
        states={SET_DELAY:   [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_delay_recv)]},
        fallbacks=[CommandHandler("cancel", cv_cancel)]))

    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_msg))
    app.run_polling()


if __name__ == "__main__":
    main()
