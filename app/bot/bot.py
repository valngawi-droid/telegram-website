"""Bot Telegram multi-tombol — PallBot.

Fitur:
  🔍 Cek ID (diri sendiri, via username, channel/grup, forward pesan)
  🤖 AI Chat (API key dari konfigurasi)
  ➕ Buat Channel / Grup + pilih owner (MTProto)
  📢 Tambah bot ke channel/grup (invite link)
  ℹ️ Info bot
  ⚙️ Admin (owner): statistik, kelola owner, broadcast, tes AI
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import services
from ..ai import AIError, ai_chat, ai_test
from ..db import db
from ..services import state as appstate

log = logging.getLogger("pallbot.bot")

router = Router()

# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------
class CekUsername(StatesGroup):
    wait = State()


class CekChatId(StatesGroup):
    wait = State()


class Create(StatesGroup):
    wait_name = State()
    wait_about = State()
    wait_owner = State()
    wait_custom_id = State()


class JoinInvite(StatesGroup):
    wait = State()


class Broadcast(StatesGroup):
    wait = State()


class AddOwner(StatesGroup):
    wait_id = State()
    wait_label = State()


class AIMode(StatesGroup):
    on = State()


class EditChannel(StatesGroup):
    wait_name = State()
    wait_about = State()


AI_RATE = 30          # pesan per jendela
AI_WINDOW = 600       # detik
_rate: dict[int, list[float]] = {}


def _ai_ok(tg_id: int) -> bool:
    now = time.time()
    ts = [t for t in _rate.get(tg_id, []) if now - t < AI_WINDOW]
    if len(ts) >= AI_RATE:
        return False
    ts.append(now)
    _rate[tg_id] = ts
    return True


def _chunk(text: str, n: int = 4000) -> list[str]:
    out = []
    while len(text) > n:
        cut = text.rfind("\n", 0, n)
        if cut < n // 2:
            cut = n
        out.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        out.append(text)
    return out or ["…"]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
async def is_admin(tg_id: int) -> bool:
    row = await db.query_one(
        "SELECT 1 AS x FROM owners WHERE tg_id=? AND is_admin=1", (int(tg_id),)
    )
    return row is not None


def B(text: str, cb: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb)


def main_kb(admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [B("🔍 Cek ID", "menu_cekid"), B("🤖 AI Chat", "menu_ai")],
        [B("➕ Buat Channel", "create_channel"), B("➕ Buat Grup", "create_group")],
        [B("📢 Tambah Bot", "menu_join"), B("ℹ️ Info", "menu_info")],
    ]
    if admin:
        rows.append([B("⚙️ Admin", "menu_admin")])
    rows.append([B("🏠 Menu Utama", "main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cekid_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B("🪪 ID Saya", "id_saya")],
        [B("📇 Cek ID via Username", "cek_username")],
        [B("📺 Cek ID Channel/Grup", "cek_chatid")],
        [B("↩️ Menu Utama", "main")],
    ])


def ai_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B("⏹️ Stop AI Chat", "ai_stop")],
        [B("🧹 Hapus Riwayat AI", "ai_clear")],
        [B("↩️ Menu Utama", "main")],
    ])


def create_owner_kb(owners: list[dict], cb_prefix: str) -> InlineKeyboardMarkup:
    rows = [[B(f"👤 {o['label']} ({o['tg_id']})", f"{cb_prefix}{o['tg_id']}")]
            for o in owners]
    rows.append([B("✏️ Input ID Manual", f"{cb_prefix}_custom")])
    rows.append([B("❌ Batal", "main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_main(message_or_cb, user_id: int, editing: bool = False):
    admin = await is_admin(user_id)
    text = (
        " <b>Halo, saya PallBot</b> — bot Telegram multi fungsi "
        "milik <b>Pall</b>.\n\n"
        "Pilih fitur di bawah:\n"
        "🔍 Cek ID • 🤖 AI Chat • ➕ Buat Channel/Grup • 📢 Tambah Bot"
    )
    kb = main_kb(admin)
    if editing and isinstance(message_or_cb, CallbackQuery):
        try:
            await message_or_cb.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except TelegramBadRequest:
            await message_or_cb.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        message_or_cb.answer()
    else:
        await message_or_cb.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def touch(user):
    try:
        await db.touch_user(user.id, user.username or "", user.first_name or "")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Komando & start
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await touch(message.from_user)
    await send_main(message, message.from_user.id)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await send_main(message, message.from_user.id)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Panduan singkat</b>\n\n"
        "🔍 <b>Cek ID</b> — cek ID diri sendiri, ID dari username, "
        "atau ID channel/grup.\n"
        "🤖 <b>AI Chat</b> — ngobrol dengan AI TELEGRAM.\n"
        "➕ <b>Buat Channel/Grup</b> — bot membuatkan channel/grup baru "
        "dan memindahkan ownership ke owner pilihan.\n"
        "📢 <b>Tambah Bot</b> — kirim invite link, bot langsung join.\n\n"
        "Ketik /start untuk kembali ke menu.",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message):
    t0 = time.time()
    await message.answer(" Pong!")
    ms = int((time.time() - t0) * 1000)
    await message.answer(f"⚡ Bot online, respons: <b>{ms} ms</b>", parse_mode=ParseMode.HTML)


@router.message(Command("ai"))
async def cmd_ai(message: Message, state: FSMContext):
    """/ai <teks> — tanya AI langsung tanpa masuk mode AI."""
    text = (message.text or "").split(maxsplit=1)
    if len(text) < 2 or not text[1].strip():
        await message.answer(
            "🤖 Pakai: <code>/ai pertanyaan kamu</code>\n"
            "atau tekan tombol 🤖 AI Chat di menu /start untuk ngobrol santai.",
            parse_mode=ParseMode.HTML,
        )
        return
    q = text[1].strip()
    u = message.from_user
    user_key = f"tg:{u.id}"
    if not _ai_ok(u.id):
        await message.answer("🚦 Terlalu banyak pesan. Tunggu beberapa menit.")
        return
    history = await db.get_ai_history(user_key, limit=10)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": q})
    await message.answer("⏳ AI sedang berpikir...")
    await db.add_ai_message(user_key, "user", q)
    try:
        reply = await ai_chat(await services.get_cfg(), messages)
        is_error = False
    except AIError as e:
        reply = f"❌ <b>AI error</b>: {e}"
        is_error = True
    except Exception as e:
        reply = f"❌ <b>Gagal terhubung ke AI</b>: {e}"
        is_error = True
    if not is_error:
        await db.add_ai_message(user_key, "assistant", reply)
    for part in _chunk(reply):
        await message.answer(part)


@router.message(Command("id"))
async def cmd_id(message: Message):
    u = message.from_user
    txt = (
        f"🪪 <b>ID Anda</b>\n\n"
        f"ID: <code>{u.id}</code>\n"
        f"Nama: {u.full_name or '-'}\n"
        f"Username: {'@' + u.username if u.username else '-'}"
    )
    if message.chat.type != "private":
        txt += f"\n\n👥 Grup/Channel ini: <code>{message.chat.id}</code>"
    await message.answer(txt, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Utilitas cepat
# ---------------------------------------------------------------------------
@router.message(Command("waktu"))
async def cmd_waktu(message: Message):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    await message.answer(
        f"🕐 <b>{now.strftime('%A, %d %B %Y')}</b>\n"
        f"⏰ {now.strftime('%H:%M:%S')} WIB"
    )


@router.message(Command("random"))
async def cmd_random(message: Message):
    import random as _r
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Pakai: <code>/random 1 100</code> (angka) "
                             "atau <code>/random a,b,c</code> (pilih acak).",
                             parse_mode=ParseMode.HTML)
        return
    arg = parts[1].strip()
    nums = arg.split()
    if len(nums) == 2 and all(n.lstrip("-").isdigit() for n in nums):
        lo, hi = int(nums[0]), int(nums[1])
        if lo > hi:
            lo, hi = hi, lo
        res = _r.randint(lo, hi)
    elif "," in arg:
        opts = [x.strip() for x in arg.split(",") if x.strip()]
        res = _r.choice(opts)
    else:
        await message.answer("Format salah. Contoh: <code>/random 1 10</code> "
                             "atau <code>/random batu,kertas,gunting</code>",
                             parse_mode=ParseMode.HTML)
        return
    await message.answer(f"🎲 <b>{res}</b>")


@router.message(Command("ceklink"))
async def cmd_ceklink(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Pakai: <code>/ceklink https://t.me/+xxxx</code>",
                             parse_mode=ParseMode.HTML)
        return
    d = await services.check_invite(parts[1].strip())
    if not d.get("ok"):
        await message.answer(d.get("message", "Gagal"))
        return
    t = "Channel" if d.get("type") == "channel" else "Grup"
    await message.answer(
        "✅ <b>Invite link VALID</b>\n\n"
        f"Nama: {d['title']}\n"
        f"Tipe: {t}\n"
        f"Member: {d.get('participants_count', 0):,}\n"
        f"Username: {'@' + d['username'] if d.get('username') else '-'}\n\n"
        "Kirim tombol 📢 Tambah Bot + link ini kalau mau bot join.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Moderasi grup (butuh bot jadi admin grup)
# ---------------------------------------------------------------------------
async def _resolve_target(message: Message):
    """Target dari reply, @username, atau ID."""
    rt = message.reply_to_message
    if rt and rt.from_user:
        return rt.from_user, None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        arg = parts[1].strip()
        if arg.lstrip("-").isdigit():
            return int(arg), None
        if arg.startswith("@"):
            try:
                chat = await message.bot.get_chat(arg)
                if chat.type == "user":
                    return chat, None
            except Exception:
                pass
    return None, (parts[1].strip() if len(parts) > 1 else None)


async def _mod_common(message: Message, action):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Fitur moderasi hanya di grup.")
        return
    target, _ = await _resolve_target(message)
    if target is None:
        await message.answer(
            "❌ Target tidak ditemukan. <b>Reply</b> pesan member, "
            "atau pakai: <code>/ban @username</code> / <code>/ban 123456789</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    name = getattr(target, "full_name", None) or str(target)
    tg_id = getattr(target, "id", target)
    try:
        if action == "kick":
            import time as _t
            await message.bot.ban_chat_member(
                message.chat.id, tg_id, until_date=int(_t.time()) + 120)
            await message.answer(f"👢 {name} dikeluarkan (bisa join lagi nanti).")
        elif action == "ban":
            await message.bot.ban_chat_member(message.chat.id, tg_id)
            await message.answer(f"🔨 {name} di-BAN permanen.")
        elif action == "unban":
            await message.bot.unban_chat_member(message.chat.id, tg_id)
            await message.answer(f"🕊️ {name} di-unban.")
        elif action == "mute":
            from aiogram.types import ChatPermissions
            import time as _t
            await message.bot.restrict_chat_member(
                message.chat.id, tg_id, ChatPermissions(),
                until_date=int(_t.time()) + 3600)
            await message.answer(f"🔇 {name} di-mute 1 jam.")
        elif action == "unmute":
            from aiogram.types import ChatPermissions
            await message.bot.restrict_chat_member(
                message.chat.id, tg_id,
                ChatPermissions(can_send_messages=True, can_send_audios=True,
                                can_send_documents=True, can_send_photos=True,
                                can_send_videos=True, can_send_video_notes=True,
                                can_send_voice_notes=True, can_send_polls=True))
            await message.answer(f"🔊 {name} bisa bicara lagi.")
    except Exception as e:
        msg = str(e)
        if "not enough rights" in msg or "Forbidden" in msg or "RIGHTS" in msg.upper():
            await message.answer(
                f"❌ Bot tidak punya izin untuk {action}. "
                "Jadikan bot <b>admin</b> grup dulu (izin: ban/restrict members).")
        else:
            await message.answer(f"❌ Gagal: {msg}")


@router.message(Command("kick"))
async def cmd_kick(message: Message):
    await _mod_common(message, "kick")


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    await _mod_common(message, "ban")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    await _mod_common(message, "unban")


@router.message(Command("mute"))
async def cmd_mute(message: Message):
    await _mod_common(message, "mute")


@router.message(Command("unmute"))
async def cmd_unmute(message: Message):
    await _mod_common(message, "unmute")


# ---------------------------------------------------------------------------
# Welcome message grup
# ---------------------------------------------------------------------------
async def _is_group_admin(message: Message) -> bool:
    me = await message.bot.get_me()
    try:
        mem = await message.bot.get_chat_member(message.chat.id, me.id)
        return mem.status in ("administrator", "creator")
    except Exception:
        return False


@router.message(Command("setwelcome"))
async def cmd_setwelcome(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Fitur welcome hanya di grup.")
        return
    if not await _is_group_admin(message):
        await message.answer("❌ Hanya admin grup yang bisa set welcome.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            'Pakai: <code>/setwelcome Selamat datang, {nama}! 🎉</code>\n'
            "({nama} akan diganti nama member baru)")
        return
    await db.set_welcome(message.chat.id, parts[1].strip()[:500])
    await message.answer("✅ Welcome message di-set. Member baru akan "
                         "disambut otomatis oleh bot.")


@router.message(Command("hapuswelcome"))
async def cmd_hapuswelcome(message: Message):
    if not await _is_group_admin(message):
        await message.answer("❌ Hanya admin grup.")
        return
    await db.del_welcome(message.chat.id)
    await message.answer("✅ Welcome message dihapus.")


from aiogram.types import ChatMemberUpdated  # noqa: E402


@router.chat_member()
async def on_chat_member(update: ChatMemberUpdated):
    old = update.old_chat_member.status
    new = update.new_chat_member.status
    if new in ("member", "administrator") and old in (None, "left", "kicked"):
        text = await db.get_welcome(update.chat.id)
        if text:
            user = update.new_chat_member.user
            nama = (user.first_name or user.full_name or "Member") if user else "Member"
            try:
                await update.bot.send_message(
                    update.chat.id, text.replace("{nama}", nama))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Pengingat pribadi
# ---------------------------------------------------------------------------
def _parse_duration(arg: str) -> tuple[float, str] | None:
    """'5m', '5 menit', '1h', '2 jam', '1d' -> (detik, label)"""
    import re as _re
    m = _re.match(r"^\s*(\d+)\s*(m|menit|min|menit|h|jam|d|hari|hour)\b",
                  arg.strip().lower())
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit in ("m", "menit", "min"):
        secs, label = n * 60, f"{n} menit"
    elif unit in ("h", "jam", "hour"):
        secs, label = n * 3600, f"{n} jam"
    else:
        secs, label = n * 86400, f"{n} hari"
    return secs, label


@router.message(Command("ingat"))
async def cmd_ingat(message: Message, state: FSMContext):
    if state.get_state() is not None:
        await state.clear()
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "⏰ Pakai: <code>/ingat 5m beli makanan</code>\n"
            "Durasi: <b>m</b>enit, <b>j</b>am (h), <b>h</b>ari (d) — "
            "contoh: <code>/ingat 30m</code>, <code>/ingat 2j</code>, <code>/ingat 1d</code>")
        return
    dur = _parse_duration(parts[1])
    if not dur:
        await message.answer("Durasi tidak valid. Contoh: <code>/ingat 5m pesan</code>")
        return
    secs, label = dur
    text = parts[2].strip()
    import time as _t
    rid = await db.add_reminder(message.chat.id, message.from_user.id,
                                _t.time() + secs, text)
    await message.answer(f"⏰ Oke! Aku akan ingatkanmu <b>{label}</b> lagi:\n\n{text}\n\n"
                         f"(ID pengingat: {rid})")


@router.message(Command("daftaringat"))
async def cmd_daftaringat(message: Message):
    rows = await db.get_reminders(message.chat.id)
    if not rows:
        await message.answer("Belum ada pengingat aktif.")
        return
    import time as _t
    from datetime import datetime
    from zoneinfo import ZoneInfo
    lines = []
    for r in rows[:20]:
        left = int(r["due_ts"] - _t.time())
        dt = datetime.fromtimestamp(r["due_ts"], ZoneInfo("Asia/Jakarta"))
        lines.append(f"• <code>#{r['id']}</code> {dt.strftime('%H:%M %d/%m')} "
                     f"({left//60}m lagi) — {r['text'][:80]}")
    await message.answer("📋 <b>Pengingat aktif</b>\n\n" + "\n".join(lines))


@router.message(Command("hapusingat"))
async def cmd_hapusingat(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("#").isdigit():
        await message.answer("Pakai: <code>/hapusingat 1</code> "
                             "(lihat /daftaringat)")
        return
    rid = int(parts[1].strip().lstrip("#"))
    await db.remove_reminder(rid)
    await message.answer(f"✅ Pengingat #{rid} dihapus.")


# ---------------------------------------------------------------------------
# Broadcast ke semua channel (admin)
# ---------------------------------------------------------------------------
@router.message(Command("bcchannel"))
async def cmd_bcchannel(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Khusus owner bot.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Pakai: <code>/bcchannel pesan kamu</code> — "
                             "dikirim ke SEMUA channel/grup yang dibuat bot.")
        return
    text = parts[1].strip()
    channels = await db.get_channels()
    ok, fail = 0, 0
    for c in channels:
        if not c.get("tg_id"):
            continue
        try:
            await message.bot.send_message(c["tg_id"], text)
            ok += 1
        except Exception:
            fail += 1
    await message.answer(
        f"📢 Broadcast channel selesai: ✅ {ok} sukses, ❌ {fail} gagal "
        "(bot harus masih admin/creator di sana).")


# ---------------------------------------------------------------------------
# Menu callbacks
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "main")
async def cb_main(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await send_main(cq, cq.from_user.id, editing=True)


@router.callback_query(F.data == "menu_cekid")
async def cb_cekid(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.message.edit_text(
        "🔍 <b>Cek ID</b> — pilih cara cek:", reply_markup=cekid_kb(),
        parse_mode=ParseMode.HTML,
    )
    cq.answer()


@router.callback_query(F.data == "id_saya")
async def cb_id_saya(cq: CallbackQuery):
    u = cq.from_user
    txt = (
        f"🪪 <b>ID Anda</b>\n\n"
        f"ID: <code>{u.id}</code>\n"
        f"Nama: {u.full_name or '-'}\n"
        f"Username: {'@' + u.username if u.username else '-'}"
    )
    if cq.message.chat.type != "private":
        txt += f"\n\n👥 ID Grup/Channel ini: <code>{cq.message.chat.id}</code>"
    await cq.message.edit_text(txt, parse_mode=ParseMode.HTML, reply_markup=cekid_kb())
    cq.answer()


@router.callback_query(F.data == "cek_username")
async def cb_cek_username(cq: CallbackQuery, state: FSMContext):
    await state.set_state(CekUsername.wait)
    await cq.message.edit_text(
        "📇 Kirim username yang mau dicek (contoh: <code>@pall</code> atau <code>pall</code>).\n"
        "Bisa username user, channel, atau grup publik.",
        parse_mode=ParseMode.HTML, reply_markup=cekid_kb(),
    )
    cq.answer()


@router.callback_query(F.data == "cek_chatid")
async def cb_cek_chatid(cq: CallbackQuery, state: FSMContext):
    await state.set_state(CekChatId.wait)
    await cq.message.edit_text(
        "📺 Kirim ID channel/grup (contoh: <code>-1001234567890</code>).\n\n"
        "💡 <b>Tidak tahu ID-nya?</b> Forward 1 pesan dari channel/grup "
        "tersebut ke bot ini — bot akan menjawab ID-nya.",
        parse_mode=ParseMode.HTML, reply_markup=cekid_kb(),
    )
    cq.answer()


@router.callback_query(F.data == "menu_join")
async def cb_join(cq: CallbackQuery, state: FSMContext):
    await state.set_state(JoinInvite.wait)
    await cq.message.edit_text(
        "📢 <b>Tambah bot ke channel/grup</b>\n\n"
        "Kirim <b>invite link</b> channel/grup (contoh:\n"
        "<code>https://t.me/+AbCd123...</code> atau <code>https://t.me/namagrup</code>)\n"
        "lalu bot akan bergabung otomatis.\n\n"
        "Atau cara manual: buka channel/grup → <i>Add Admin / Add Member</i> → "
        f"cari <b>@{appstate.bot_username or 'namabot'}</b>.",
        parse_mode=ParseMode.HTML, reply_markup=cekid_kb(),
    )
    cq.answer()


@router.callback_query(F.data == "menu_info")
async def cb_info(cq: CallbackQuery):
    owners = await db.get_owners()
    txt = (
        "ℹ️ <b>Tentang PallBot</b>\n\n"
        "Bot Telegram multi fungsi + website, dibuat oleh <b>Pall</b>.\n\n"
        "✨ Fitur:\n"
        "• Cek ID diri / username / channel / grup\n"
        "• Buat channel & grup + pilih owner\n"
        "• AI Chat (AI TELEGRAM)\n"
        "• Tambah bot ke channel/grup\n"
        "• Panel admin & broadcast\n\n"
        f"👤 Owner: {', '.join(o['label'] for o in owners)}"
    )
    await cq.message.edit_text(txt, reply_markup=main_kb(True), parse_mode=ParseMode.HTML)
    cq.answer()


@router.callback_query(F.data == "menu_ai")
async def cb_ai(cq: CallbackQuery, state: FSMContext):
    await state.set_state(AIMode.on)
    await cq.message.edit_text(
        "🤖 <b>AI TELEGRAM aktif</b>\n\n"
        "Kirim pesan Anda, AI akan menjawab.\n"
        "Tekan ⏹️ untuk keluar.",
        parse_mode=ParseMode.HTML, reply_markup=ai_kb(),
    )
    cq.answer()


@router.callback_query(F.data == "ai_stop")
async def cb_ai_stop(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.message.edit_text(
        "⏹️ AI Chat dimatikan.\nPilih fitur lain:",
        reply_markup=main_kb(await is_admin(cq.from_user.id)),
    )
    cq.answer()


@router.callback_query(F.data == "ai_clear")
async def cb_ai_clear(cq: CallbackQuery, state: FSMContext):
    await db.clear_ai_history(f"tg:{cq.from_user.id}")
    cq.answer("Riwayat AI dihapus", show_alert=True)


# ---------------------------------------------------------------------------
# Buat channel / grup
# ---------------------------------------------------------------------------
async def _start_create(cq: CallbackQuery, state: FSMContext, etype: str):
    await state.set_state(Create.wait_name)
    await state.update_data(etype=etype)
    label = "channel" if etype == "channel" else "grup"
    await cq.message.edit_text(
        f"➕ <b>Buat {label}</b>\n\nKirim <b>nama {label}</b> baru Anda:",
        parse_mode=ParseMode.HTML,
    )
    cq.answer()


@router.callback_query(F.data == "create_channel")
async def cb_create_channel(cq: CallbackQuery, state: FSMContext):
    await _start_create(cq, state, "channel")


@router.callback_query(F.data == "create_group")
async def cb_create_group(cq: CallbackQuery, state: FSMContext):
    await _start_create(cq, state, "group")


async def _choose_owner(message: Message, state: FSMContext, data: dict):
    owners = await db.get_owners()
    prefix = "create_owner_"
    kb = create_owner_kb(owners, prefix)
    await message.answer(
        f"👑 Pilih <b>owner</b> {data['etype']}:", parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    await state.set_state(Create.wait_owner)


@router.callback_query(F.data.startswith("create_owner_"))
async def cb_choose_owner(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cb = cq.data
    prefix = "create_owner_"
    if cb == prefix + "_custom":
        await state.set_state(Create.wait_custom_id)
        await cq.message.answer(
            "✏️ Kirim ID Telegram owner (angka, contoh: 8861238621)"
        )
        cq.answer()
        return
    rest = cb[len(prefix):]
    if not rest.lstrip("-").isdigit():
        cq.answer("Pilihan tidak valid", show_alert=True)
        return
    owner_id = int(rest)

    label = {o["tg_id"]: o["label"] for o in await db.get_owners()}.get(owner_id, str(owner_id))
    await state.clear()
    status = await cq.message.answer(f"⏳ Membuat {data.get('etype', 'channel')}...")
    result = await services.create_entity(
        name=data.get("name", "Tanpa Nama"),
        etype=data.get("etype", "channel"),
        owner_tg_id=owner_id,
        about=data.get("about", ""),
        source="bot",
    )
    await status.edit_text(_format_result(result, label), parse_mode=ParseMode.HTML)
    await db.add_channel(
        name=result.get("name") or data.get("name", ""),
        ctype=data.get("etype", ""),
        tg_id=result.get("tg_id"),
        username=result.get("username", ""),
        invite=result.get("invite", ""),
        owner_tg_id=owner_id,
        owner_label=label,
        source="bot",
    )
    cq.answer()


def _format_result(r: dict, owner_label: str = "") -> str:
    if not r.get("ok"):
        return f"{r.get('message', 'Gagal')}\n\nTekan /menu untuk mencoba lagi."
    lines = [
        "🎉 <b>Berhasil dibuat!</b>",
        f"📛 Nama: {r.get('name', '-')}",
        f"🆔 ID: <code>{r.get('tg_id', '-')}</code>",
    ]
    if r.get("username"):
        lines.append(f"🔗 Link: https://t.me/{r['username']}")
    elif r.get("invite"):
        lines.append(f"🔗 Invite: <code>{r['invite']}</code>")
    if owner_label or r.get("owner_tg_id"):
        lines.append(f"👑 Owner: {owner_label or r.get('owner_tg_id')}")
    if r.get("message"):
        lines.append(r["message"])
    lines.append("\nTekan /menu untuk kembali.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B("📊 Statistik", "admin_stats"), B("🤖 Tes AI", "admin_aitest")],
        [B("✏️ Edit Channel", "admin_editch"), B("👁️ Detail Channel", "admin_chdetail")],
        [B("➕ Tambah Owner", "admin_addowner"), B("📋 Daftar Owner", "admin_ownerlist")],
        [B("📋 Daftar Channel", "admin_channellist")],
        [B("📢 Broadcast", "admin_broadcast")],
        [B("↩️ Menu Utama", "main")],
    ])


@router.callback_query(F.data == "menu_admin")
async def cb_admin(cq: CallbackQuery, state: FSMContext):
    if not await is_admin(cq.from_user.id):
        cq.answer("❌ Khusus owner bot", show_alert=True)
        return
    await state.clear()
    await cq.message.edit_text(
        "⚙️ <b>Panel Admin</b> — hanya untuk owner bot.",
        reply_markup=admin_kb(), parse_mode=ParseMode.HTML,
    )
    cq.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(cq: CallbackQuery):
    users = await db.get_users()
    channels = await db.get_channels()
    owners = await db.get_owners()
    cfg = await services.get_cfg()
    txt = (
        "📊 <b>Statistik PallBot</b>\n\n"
        f"👤 User terdaftar: <b>{len(users)}</b>\n"
        f"📺 Channel/Grup dibuat: <b>{len(channels)}</b>\n"
        f"👑 Owner terdaftar: <b>{len(owners)}</b>\n\n"
        f"🤖 Bot: {'🟢 online' if appstate.bot_online else '🔴 offline'} "
        f"({'@' + appstate.bot_username if appstate.bot_username else '-'})\n"
        f"🛰️ MTProto: {'🟢 online' if appstate.mtproto_online else ('🟡 siap (perlu start)' if appstate.mtproto_ready else '🔴 belum di-set')}\n"
        f"🤖 AI: {cfg.get('AI_PROVIDER')}/{cfg.get('AI_MODEL') or cfg.get('AI_OPENAI_MODEL')}\n"
        f"🔑 AI key: {'terisi' if cfg.get('AI_KEY') else 'KOSONG'}"
    )
    await cq.message.edit_text(txt, reply_markup=admin_kb(), parse_mode=ParseMode.HTML)
    cq.answer()


@router.callback_query(F.data == "admin_aitest")
async def cb_admin_aitest(cq: CallbackQuery):
    await cq.message.answer("⏳ Menguji koneksi AI...")
    cfg = await services.get_cfg()
    try:
        msg = await ai_test(cfg)
    except AIError as e:
        msg = f"❌ {e}\n\nCek menu Pengaturan di website untuk mengubah provider/model/key."
    except Exception as e:
        msg = f"❌ Error koneksi: {e}\n\nPeriksa network VPS & konfigurasi AI."
    await cq.message.answer(msg)
    cq.answer()


@router.callback_query(F.data == "admin_addowner")
async def cb_admin_addowner(cq: CallbackQuery, state: FSMContext):
    await state.set_state(AddOwner.wait_id)
    await cq.message.answer("➕ Kirim <b>ID</b> Telegram owner baru (angka):")
    cq.answer()


@router.callback_query(F.data == "admin_ownerlist")
async def cb_admin_ownerlist(cq: CallbackQuery):
    owners = await db.get_owners()
    lines = [f"{'⭐' if o['is_admin'] else '•'} <b>{o['label']}</b> — <code>{o['tg_id']}</code>"
             for o in owners]
    await cq.message.edit_text(
        "📋 <b>Daftar Owner</b>\n\n" + "\n".join(lines),
        reply_markup=admin_kb(), parse_mode=ParseMode.HTML,
    )
    cq.answer()


@router.callback_query(F.data == "admin_channellist")
async def cb_admin_channellist(cq: CallbackQuery):
    channels = await db.get_channels()[:15]
    if not channels:
        txt = "📋 Belum ada channel/grup yang dibuat."
    else:
        lines = []
        for c in channels:
            link = f" | https://t.me/{c['username']}" if c.get("username") else ""
            lines.append(
                f"📛 <b>{c['name']}</b> ({c['type']})\n"
                f"   ID: <code>{c['tg_id']}</code>{link}\n"
                f"   Owner: {c.get('owner_label') or c.get('owner_tg_id')}"
            )
        txt = "📋 <b>Channel/Grup terakhir</b>\n\n" + "\n".join(lines)
    await cq.message.edit_text(txt, reply_markup=admin_kb(), parse_mode=ParseMode.HTML)
    cq.answer()


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(cq: CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.wait)
    await cq.message.answer("📢 Kirim <b>teks broadcast</b> (dikirim ke semua user):")
    cq.answer()


# ---------------------------------------------------------------------------
# Edit / kelola channel (admin)
# ---------------------------------------------------------------------------
async def _channel_by_dbid(dbid: int) -> dict | None:
    return await db.query_one("SELECT * FROM channels WHERE id=?", (int(dbid),))


async def _ch_pick_kb(cq: CallbackQuery, title: str, prefix: str):
    channels = await db.get_channels()
    if not channels:
        await cq.message.edit_text(
            "📋 Belum ada channel/grup yang dibuat.\nBuat dulu di menu ➕ atau di website.",
            reply_markup=admin_kb(),
        )
        cq.answer()
        return None
    rows = [[B(f"📛 {c['name']} ({c['type']})", f"{prefix}{c['id']}")] for c in channels[:20]]
    rows.append([B("↩️ Panel Admin", "menu_admin")])
    await cq.message.edit_text(title, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    cq.answer()
    return channels


def _ch_actions_kb(dbid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B("✏️ Ubah Nama", f"editch_name:{dbid}"), B("📝 Ubah Deskripsi", f"editch_about:{dbid}")],
        [B("🔗 Invite Link Baru", f"editch_invite:{dbid}"), B("👁️ Detail & Member", f"editch_detail:{dbid}")],
        [B("🗑️ Hapus di Telegram", f"editch_del:{dbid}")],
        [B("↩️ Pilih Channel Lain", "admin_editch"), B("↩️ Panel Admin", "menu_admin")],
    ])


@router.callback_query(F.data == "admin_editch")
async def cb_admin_editch(cq: CallbackQuery, state: FSMContext):
    if not await is_admin(cq.from_user.id):
        cq.answer("❌ Khusus owner bot", show_alert=True)
        return
    await state.clear()
    await _ch_pick_kb(cq, "✏️ <b>Edit Channel</b> — pilih channel/grup:", "editch_pick:")
    cq.answer()


@router.callback_query(F.data == "admin_chdetail")
async def cb_admin_chdetail(cq: CallbackQuery, state: FSMContext):
    if not await is_admin(cq.from_user.id):
        cq.answer("❌ Khusus owner bot", show_alert=True)
        return
    await state.clear()
    await _ch_pick_kb(cq, "👁️ <b>Detail Channel</b> — pilih channel/grup:", "chdetail_pick:")
    cq.answer()


@router.callback_query(F.data.startswith("editch_pick:"))
async def cb_editch_pick(cq: CallbackQuery):
    dbid = int(cq.data.split(":", 1)[1])
    row = await _channel_by_dbid(dbid)
    if not row:
        cq.answer("Channel tidak ditemukan", show_alert=True)
        return
    await cq.message.edit_text(
        f"📛 <b>{row['name']}</b> ({row['type']})\nID: <code>{row['tg_id']}</code>\n"
        f"Owner: {row.get('owner_label') or row.get('owner_tg_id')}\n\nPilih aksi:",
        parse_mode=ParseMode.HTML,
        reply_markup=_ch_actions_kb(dbid),
    )
    cq.answer()


@router.callback_query(F.data.startswith("chdetail_pick:"))
async def cb_chdetail_pick(cq: CallbackQuery):
    dbid = int(cq.data.split(":", 1)[1])
    row = await _channel_by_dbid(dbid)
    if not row:
        cq.answer("Channel tidak ditemukan", show_alert=True)
        return
    await cq.message.answer("⏳ Mengambil detail...")
    d = await services.channel_detail(row["tg_id"])
    if not d.get("ok"):
        await cq.message.answer(d.get("message", "Gagal"))
    else:
        link = f"https://t.me/{d['username']}" if d.get("username") else "-"
        txt = (
            "👁️ <b>Detail Channel/Grup</b>\n\n"
            f"📛 Nama: {d['title']}\n"
            f"👥 Member: <b>{d['participants_count']:,}</b>\n"
            f"🛡️ Admin: {d.get('admin_count', 0)}\n"
            f"🔗 Link: {link}\n"
            f"🆔 ID: <code>{row['tg_id']}</code>"
            + (f"\n\n📝 {d['about']}" if d.get("about") else "")
        )
        await cq.message.answer(txt, parse_mode=ParseMode.HTML)
    cq.answer()


@router.callback_query(F.data.startswith("editch_name:"))
async def cb_editch_name(cq: CallbackQuery, state: FSMContext):
    dbid = int(cq.data.split(":", 1)[1])
    row = await _channel_by_dbid(dbid)
    if not row:
        cq.answer("Channel tidak ditemukan", show_alert=True)
        return
    await state.set_state(EditChannel.wait_name)
    await state.update_data(dbid=dbid, tg_id=row["tg_id"], name=row["name"])
    await cq.message.answer(f"✏️ Kirim <b>nama baru</b> untuk {row['name']}:")
    cq.answer()


@router.callback_query(F.data.startswith("editch_about:"))
async def cb_editch_about(cq: CallbackQuery, state: FSMContext):
    dbid = int(cq.data.split(":", 1)[1])
    row = await _channel_by_dbid(dbid)
    if not row:
        cq.answer("Channel tidak ditemukan", show_alert=True)
        return
    await state.set_state(EditChannel.wait_about)
    await state.update_data(dbid=dbid, tg_id=row["tg_id"], name=row["name"])
    await cq.message.answer(f"📝 Kirim <b>deskripsi baru</b> untuk {row['name']} (atau /kosong untuk hapus):")
    cq.answer()


@router.callback_query(F.data.startswith("editch_invite:"))
async def cb_editch_invite(cq: CallbackQuery):
    dbid = int(cq.data.split(":", 1)[1])
    row = await _channel_by_dbid(dbid)
    if not row:
        cq.answer("Channel tidak ditemukan", show_alert=True)
        return
    await cq.message.answer("⏳ Membuat invite link baru...")
    r = await services.new_invite(row["tg_id"])
    if r.get("ok") and r.get("invite"):
        await db.execute(
            "UPDATE channels SET invite=? WHERE id=?", (r["invite"], dbid)
        )
        await cq.message.answer(f"🔗 <b>Invite link baru</b>\n<code>{r['invite']}</code>",
                                parse_mode=ParseMode.HTML)
    else:
        await cq.message.answer(r.get("message", "Gagal membuat invite"))
    cq.answer()


@router.callback_query(F.data.startswith("editch_detail:"))
async def cb_editch_detail(cq: CallbackQuery):
    dbid = int(cq.data.split(":", 1)[1])
    row = await _channel_by_dbid(dbid)
    if not row:
        cq.answer("Channel tidak ditemukan", show_alert=True)
        return
    await cq.message.answer("⏳ Mengambil detail...")
    d = await services.channel_detail(row["tg_id"])
    if not d.get("ok"):
        await cq.message.answer(d.get("message", "Gagal"))
    else:
        link = f"https://t.me/{d['username']}" if d.get("username") else "-"
        txt = (
            "👁️ <b>Detail Channel/Grup</b>\n\n"
            f"📛 Nama: {d['title']}\n"
            f"👥 Member: <b>{d['participants_count']:,}</b>\n"
            f"🛡️ Admin: {d.get('admin_count', 0)}\n"
            f"🔗 Link: {link}\n"
            f"🆔 ID: <code>{row['tg_id']}</code>"
            + (f"\n\n📝 {d['about']}" if d.get("about") else "")
        )
        await cq.message.answer(txt, parse_mode=ParseMode.HTML)
    cq.answer()


@router.callback_query(F.data.startswith("editch_del:"))
async def cb_editch_del(cq: CallbackQuery, state: FSMContext):
    dbid = int(cq.data.split(":", 1)[1])
    row = await _channel_by_dbid(dbid)
    if not row:
        cq.answer("Channel tidak ditemukan", show_alert=True)
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B("💀 YA, HAPUS PERMANEN", f"editch_delc:{dbid}")],
        [B("↩️ Batal", "menu_admin")],
    ])
    await cq.message.edit_text(
        f"⚠️ <b>PERINGATAN</b>\n\n"
        f"Channel/grup <b>{row['name']}</b> akan dihapus <b>PERMANEN</b> "
        "dari Telegram. Semua pesan & member hilang. Tidak bisa diurungkan!",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    cq.answer()


@router.callback_query(F.data.startswith("editch_delc:"))
async def cb_editch_delc(cq: CallbackQuery):
    dbid = int(cq.data.split(":", 1)[1])
    row = await _channel_by_dbid(dbid)
    if not row:
        cq.answer("Channel tidak ditemukan", show_alert=True)
        return
    await cq.message.answer("⏳ Menghapus channel di Telegram...")
    r = await services.delete_entity(row["tg_id"])
    await db.remove_channel(dbid)
    txt = r.get("message", "Selesai")
    await cq.message.edit_text(
        txt + "\n\nDihapus juga dari daftar.",
        reply_markup=admin_kb(),
    )
    cq.answer()


# ---------------------------------------------------------------------------
# FSM edit channel
# ---------------------------------------------------------------------------
@router.message(EditChannel.wait_name)
async def fsm_editch_name(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Nama terlalu pendek. /menu untuk kembali.")
        return
    r = await services.edit_entity(data["tg_id"], name=name)
    await db.execute("UPDATE channels SET name=? WHERE id=?", (name, data["dbid"]))
    await message.answer(r.get("message", "Selesai"))


@router.message(EditChannel.wait_about)
async def fsm_editch_about(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    txt = (message.text or "").strip()
    if txt.lower() in ("/kosong", "kosong", "/skip", "-"):
        txt = ""
    r = await services.edit_entity(data["tg_id"], about=txt)
    await message.answer(r.get("message", "Selesai"))


# ---------------------------------------------------------------------------
# Pengisian FSM (pesan teks)
# ---------------------------------------------------------------------------
@router.message(CekUsername.wait)
async def fsm_cek_username(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    result = await services.resolve_username(bot, message.text or "")
    if result.get("ok"):
        t = {"user": "User", "channel": "Channel", "group": "Grup", "supergroup": "Grup (Super)"}.get(
            result["type"], result["type"])
        txt = (
            "✅ <b>Hasil cek ID</b>\n\n"
            f"Nama: {result.get('title') or '-'}\n"
            f"Username: {'@' + result['username'] if result.get('username') else '-'}\n"
            f"Tipe: {t}\n"
            f"ID: <code>{result['display_id']}</code>"
        )
    else:
        txt = result.get("message", "Gagal") + "\n\n💡 Pastikan username-nya publik."
    await message.answer(txt, parse_mode=ParseMode.HTML)
    await touch(message.from_user)


@router.message(CekChatId.wait)
async def fsm_cek_chatid(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    result = await services.resolve_chat_info(bot, message.text or "")
    if result.get("ok"):
        txt = (
            "✅ <b>Hasil cek ID</b>\n\n"
            f"Nama: {result.get('title') or '-'}\n"
            f"Tipe: {result['type']}\n"
            f"ID: <code>{result['display_id']}</code>"
        )
    else:
        txt = (
            result.get("message", "Gagal") +
            "\n\n💡 Untuk channel/grup <b>privat</b>, forward 1 pesan dari sana "
            "ke bot ini."
        )
    await message.answer(txt, parse_mode=ParseMode.HTML)


@router.message(Create.wait_name)
async def fsm_create_name(message: Message, state: FSMContext):
    data = await state.get_data()
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Nama terlalu pendek, coba lagi:")
        return
    await state.update_data(name=name)
    await state.set_state(Create.wait_about)
    await message.answer(
        f"✔️ Nama: <b>{name}</b>\n\nKirim <b>deskripsi singkat</b> "
        "(atau ketik /skip untuk lewati):",
        parse_mode=ParseMode.HTML,
    )


@router.message(Create.wait_about)
async def fsm_create_about(message: Message, state: FSMContext):
    data = await state.get_data()
    if (message.text or "").strip().lower() in ("/skip", "skip", "-"):
        about = ""
    else:
        about = (message.text or "").strip()
    await state.update_data(about=about)
    await _choose_owner(message, state, data)


@router.message(Create.wait_owner)
async def fsm_create_wait_owner(message: Message):
    await message.answer("⚠️ Pilih owner lewat tombol di atas (atau /menu untuk ulang).")


@router.message(Create.wait_custom_id)
async def fsm_create_custom_id(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt.lstrip("-").isdigit():
        await message.answer("ID harus angka. Coba lagi (atau /menu):")
        return
    data = await state.get_data()
    await state.clear()
    status = await message.answer("⏳ Membuat...")
    result = await services.create_entity(
        name=data.get("name", "Tanpa Nama"),
        etype=data.get("etype", "channel"),
        owner_tg_id=int(txt),
        about=data.get("about", ""),
        source="bot",
    )
    await status.edit_text(_format_result(result, txt), parse_mode=ParseMode.HTML)
    await db.add_channel(
        name=result.get("name") or data.get("name", ""),
        ctype=data.get("etype", ""),
        tg_id=result.get("tg_id"),
        username=result.get("username", ""),
        invite=result.get("invite", ""),
        owner_tg_id=int(txt),
        owner_label=txt,
        source="bot",
    )


@router.message(JoinInvite.wait)
async def fsm_join_invite(message: Message, state: FSMContext):
    await state.clear()
    link = (message.text or "").strip()
    if not link:
        await message.answer("Link kosong. /menu untuk kembali.")
        return
    result = await services.join_invite(link)
    await message.answer(result["message"], parse_mode=None)


@router.message(Broadcast.wait)
async def fsm_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    text = (message.text or "").strip()
    if not text:
        return
    users = await db.get_users()
    if not users:
        await message.answer("Belum ada user terdaftar untuk broadcast.")
        return
    status = await message.answer(f"⏳ Mengirim ke {len(users)} user...")
    res = await services.broadcast(bot, users, text)
    await status.edit_text(
        f"📢 Broadcast selesai: ✅ {res['sent']} terkirim, ❌ {res['failed']} gagal "
        "(user yang blok bot / offline)."
    )


@router.message(AddOwner.wait_id)
async def fsm_addowner_id(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if not txt.lstrip("-").isdigit():
        await message.answer("ID harus angka (contoh: 8861238621):")
        return
    await state.update_data(oid=txt)
    await state.set_state(AddOwner.wait_label)
    await message.answer(f"Kirim <b>label/nama</b> untuk ID {txt}:")


@router.message(AddOwner.wait_label)
async def fsm_addowner_label(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await db.add_owner(int(data["oid"]), (message.text or "Owner").strip()[:60], is_admin=True)
    await message.answer("✅ Owner ditambahkan.")


# ---------------------------------------------------------------------------
# Forward pesan -> cek ID chat
# ---------------------------------------------------------------------------
@router.message(F.forward_from_chat)
async def on_forward(message: Message, state: FSMContext):
    if state.get_state() is not None:
        return
    fc = message.forward_from_chat
    t = {"channel": "Channel", "group": "Grup", "supergroup": "Grup (Super)"}.get(fc.type, fc.type)
    display = str(fc.id)
    await message.answer(
        "✅ <b>ID chat yang di-forward</b>\n\n"
        f"Nama: {fc.title or '-'}\n"
        f"Tipe: {t}\n"
        f"ID: <code>{display}</code>",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# AI mode (mode teks bebas)
# ---------------------------------------------------------------------------
@router.message(AIMode.on, F.text)
async def ai_mode_text(message: Message, state: FSMContext):
    u = message.from_user
    user_key = f"tg:{u.id}"
    if not _ai_ok(u.id):
        await message.answer("🚦 Terlalu banyak pesan. Tunggu beberapa menit.")
        return
    history = await db.get_ai_history(user_key, limit=10)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": message.text})
    typing = await message.bot.send_chat_action(message.chat.id, "typing")  # noqa: F841
    await db.add_ai_message(user_key, "user", message.text)
    try:
        reply = await ai_chat(await services.get_cfg(), messages)
        is_error = False
    except AIError as e:
        reply = (
            f"❌ <b>AI error</b>: {e}\n\n"
            "Periksa konfigurasi AI di <b>website → Panel Admin → Pengaturan</b> "
            "(provider / model / key bisa diganti)."
        )
        is_error = True
    except Exception as e:
        reply = (
            f"❌ <b>Gagal terhubung ke AI</b>: {e}\n\n"
            "Periksa network & konfigurasi AI di "
            "<b>website → Panel Admin → Pengaturan</b>."
        )
        is_error = True
    if not is_error:
        await db.add_ai_message(user_key, "assistant", reply)
    for part in _chunk(reply):
        await message.answer(part)


# ---------------------------------------------------------------------------
# Fallback teks
# ---------------------------------------------------------------------------
@router.message(F.text)
async def fallback(message: Message, state: FSMContext):
    await touch(message.from_user)
    await message.answer(
        "🤔 Saya belum paham. Ketik /start atau /help untuk melihat menu.",
        reply_markup=main_kb(await is_admin(message.from_user.id)),
    )


@router.message()
async def fallback_media(message: Message):
    await message.answer(
        "📨 Saat ini saya hanya memproses <b>teks</b>. /start untuk menu.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(await is_admin(message.from_user.id)),
    )


# ---------------------------------------------------------------------------
# BotManager — hidup/mati polling (token bisa diganti dari website)
# ---------------------------------------------------------------------------
class BotManager:
    def __init__(self):
        self.task: asyncio.Task | None = None
        self.bot: Bot | None = None
        self.current_token: str = ""

    async def start(self, token: str):
        await self.stop()
        self.current_token = token
        self.bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.task = asyncio.create_task(self._poll())

    async def _poll(self):
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(router)
        try:
            await self.bot.delete_webhook(drop_pending_updates=True)
            me = await self.bot.get_me()
            appstate.bot_online = True
            appstate.bot_id = me.id
            appstate.bot_username = me.username or ""
            await db.log("info", "bot", f"Bot online: @{me.username} (id={me.id})")
            await dp.start_polling(self.bot)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            appstate.bot_online = False
            appstate.last_error = str(e)
            await db.log("error", "bot", f"Polling error: {e}")
            log.exception("bot polling error")
        finally:
            appstate.bot_online = False

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
            self.task = None
        if self.bot:
            try:
                await self.bot.session.close()
            except Exception:
                pass
            self.bot = None
        appstate.bot_online = False

    async def restart_if_changed(self, token: str):
        """Dipanggil berkala dari website — restart kalau token berubah."""
        if token and token != self.current_token:
            await self.start(token)
        elif not token and self.current_token:
            await self.stop()


bot_manager = BotManager()


# ---------------------------------------------------------------------------
# Error handler global
# ---------------------------------------------------------------------------
@router.errors()
async def on_error(event):
    log.exception("handler error", exc_info=event.exception)
    return True
