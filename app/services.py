"""Layanan inti — dipakai bersama oleh bot Telegram dan website.

- MTProto (Telethon, mode bot) : buat channel/grup, pindahkan ownership,
  join invite link, cek info chat.
- Bot API (aiogram)            : resolve username, info bot.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import AuthKeyUnregisteredError, RPCError

from .config import SESSION_DIR, config
from .db import db

log = logging.getLogger("pallbot")

SESSION_NAME = "pallbot_mtproto"


class State:
    """Status runtime yang dibaca dashboard website."""
    bot_online = False
    bot_username = ""
    bot_id = 0
    mtproto_online = False
    mtproto_ready = False   # True kalau api_id/hash + token sudah di-set
    last_error = ""
    updated_at = 0.0


state = State()


def _touch():
    state.updated_at = time.time()


# --------------------------------------------------------------------------
# Konfigurasi final (DB > .env)
# --------------------------------------------------------------------------
async def get_cfg() -> dict:
    settings = await db.get_settings()
    return config.apply_db(settings)


# --------------------------------------------------------------------------
# MTProto (Telethon)
# --------------------------------------------------------------------------
_tg_client: TelegramClient | None = None


async def get_mtproto() -> TelegramClient | None:
    global _tg_client
    if _tg_client and _tg_client.is_connected():
        return _tg_client
    return None


async def start_mtproto(cfg: dict) -> tuple[bool, str]:
    """Start client MTProto dengan kredensial bot. Idempoten."""
    global _tg_client
    api_id = cfg.get("API_ID", "")
    api_hash = cfg.get("API_HASH", "")
    token = cfg.get("BOT_TOKEN", "")

    if not (api_id and api_hash and token):
        state.mtproto_ready = False
        msg = "Belum lengkap: butuh BOT_TOKEN + API_ID + API_HASH (Pengaturan / .env)"
        state.last_error = msg
        _touch()
        return False, msg
    state.mtproto_ready = True

    # hentikan client lama
    await stop_mtproto()

    client = TelegramClient(
        str(SESSION_DIR / SESSION_NAME),
        int(api_id),
        api_hash,
    )
    try:
        await client.start(bot_token=token)
        me = await client.get_me()
        _tg_client = client
        state.mtproto_online = True
        state.last_error = ""
        _touch()
        await db.log("info", "mtproto", f"MTProto online sebagai @{me.username} (id={me.id})")
        return True, f"✅ MTProto online: @{me.username}"
    except AuthKeyUnregisteredError:
        # api id/hash berganti — hapus session lama
        for f in SESSION_DIR.glob(f"{SESSION_NAME}.session*"):
            f.unlink(missing_ok=True)
        await client.disconnect()
        try:
            await client.start(bot_token=token)
            me = await client.get_me()
            _tg_client = client
            state.mtproto_online = True
            return True, f"✅ MTProto online (session baru): @{me.username}"
        except Exception as e:
            state.last_error = str(e)
            return False, f"❌ Gagal start MTProto: {e}"
    except Exception as e:
        state.mtproto_online = False
        state.last_error = str(e)
        await db.log("error", "mtproto", f"Gagal start: {e}")
        return False, f"❌ Gagal start MTProto: {e}"


async def stop_mtproto():
    global _tg_client
    if _tg_client:
        try:
            await _tg_client.disconnect()
        except Exception:
            pass
        _tg_client = None
    state.mtproto_online = False
    _touch()


# --------------------------------------------------------------------------
# Buat Channel / Grup + pilih owner
# --------------------------------------------------------------------------
async def create_entity(
    name: str,
    etype: str,            # "channel" | "group"
    owner_tg_id: int,
    about: str = "",
    source: str = "bot",
) -> dict:
    """Buat channel/grup baru, lalu pindahkan ownership ke owner_tg_id.

    Return dict: {ok, name, tg_id, username, invite, owner_tg_id, message}
    """
    from telethon.tl.functions.channels import (
        CreateChannelRequest,
        EditAdminRequest,
        InviteToChannelRequest,
    )
    from telethon.tl.types import ChatAdminRights

    client = await get_mtproto()
    if client is None:
        ok, msg = await start_mtproto(await get_cfg())
        if not ok:
            return {"ok": False, "message": msg}
        client = await get_mtproto()

    me = await client.get_me()
    full_rights = ChatAdminRights(
        change_info=True, post_messages=True, edit_messages=True,
        delete_messages=True, ban_users=True, invite_users=True,
        pin_messages=True, add_admins=True, manage_call=True,
        other=True, manage_topics=True,
    )

    try:
        result = await client(
            CreateChannelRequest(
                title=name, about=about,
                broadcast=(etype == "channel"),
                megagroup=(etype == "group"),
            )
        )
        # ambil chat yang baru dibuat dari Updates
        chat = None
        for c in (getattr(result, "chats", None) or []):
            if getattr(c, "title", None) == name:
                chat = c
                break
        if chat is None:
            for c in (getattr(result, "chats", None) or []):
                chat = c
        if chat is None:
            for d in (getattr(result, "dialogs", None) or []):
                c = getattr(d, "chat", None) or getattr(d, "peer", None)
                if c is not None:
                    chat = c
                    break
        if chat is None:
            return {"ok": False, "message": "Channel/grup dibuat tapi tidak bisa diidentifikasi. Cek manual di Telegram."}
        tg_id = chat.id
        username = getattr(chat, "username", "") or ""

        # --- tunjuk owner terpilih sebagai admin penuh (rank "Owner") ---
        # Catatan: transfer ownership *sejati* (channels.editCreator) hanya bisa
        # dilakukan akun user + password 2FA, tidak bisa oleh bot. Jadi owner
        # ditunjuk sebagai admin penuh dengan rank "Owner" — persis seperti
        # bot reseller channel pada umumnya.
        owner_note = ""
        owner_id = int(owner_tg_id)
        if owner_id != me.id:
            try:
                try:
                    await client(InviteToChannelRequest(chat, [owner_id]))
                except RPCError:
                    pass  # sudah member
                await client(EditAdminRequest(
                    channel=chat,
                    user_id=owner_id,
                    admin_rights=full_rights,
                    rank="Owner",
                ))
                owner_note = (f"{owner_id} ditunjuk sebagai admin penuh "
                              f"dengan rank 'Owner' (semua hak admin).")
            except Exception as e2:
                owner_note = (f"⚠️ Channel/grup sudah dibuat, tapi penunjukan "
                              f"owner {owner_id} gagal: {e2}. Tambahkan manual.")
        else:
            owner_note = f"Owner tetap bot ({me.id})."

        # --- invite link (jika ada) ---
        invite = f"https://t.me/{username}" if username else ""
        if not invite:
            try:
                from telethon.tl.functions.messages import ExportChatInviteRequest
                inv = await client(ExportChatInviteRequest(peer=chat))
                invite = inv.link or ""
            except Exception:
                invite = ""

        return {
            "ok": True,
            "name": name,
            "tg_id": tg_id,
            "username": username,
            "invite": invite,
            "owner_tg_id": int(owner_tg_id),
            "message": owner_note,
        }
    except Exception as e:
        await db.log("error", "mtproto", f"create_entity gagal: {e}")
        return {"ok": False, "message": f"❌ Gagal membuat {etype}: {e}"}


async def join_invite(link: str) -> dict:
    """Bot join channel/grup lewat invite link (atau username publik)."""
    from telethon.tl.functions.messages import ImportChatInviteRequest

    client = await get_mtproto()
    if client is None:
        ok, msg = await start_mtproto(await get_cfg())
        if not ok:
            return {"ok": False, "message": msg}
        client = await get_mtproto()

    link = link.strip()
    if link and not link.startswith("http") and not link.startswith("@"):
        link = f"https://t.me/+{link}" if not link.startswith("/") else link
    try:
        chat = await client(ImportChatInviteRequest(link))
        name = getattr(chat, "title", str(chat))
        return {"ok": True, "name": name, "tg_id": chat.id,
                "message": f"✅ Bot bergabung ke {name}"}
    except Exception as e:
        return {"ok": False, "message": f"❌ Gagal join: {e}"}


# --------------------------------------------------------------------------
# Kelola channel/grup yang sudah dibuat
# --------------------------------------------------------------------------
async def edit_entity(tg_id: int, name: str | None = None,
                      about: str | None = None) -> dict:
    """Ubah nama (title) dan/atau deskripsi (about) channel/grup."""
    from telethon.tl.functions.channels import EditTitleRequest
    from telethon.tl.functions.messages import EditChatAboutRequest

    client = await get_mtproto()
    if client is None:
        ok, msg = await start_mtproto(await get_cfg())
        if not ok:
            return {"ok": False, "message": msg}
        client = await get_mtproto()
    try:
        peer = await client.get_input_entity(int(tg_id))
        if name is not None and name.strip():
            await client(EditTitleRequest(channel=peer, title=name.strip()))
        if about is not None:
            await client(EditChatAboutRequest(peer=peer, about=about.strip()[:500]))
        return {"ok": True, "message": "✅ Berhasil diperbarui"}
    except Exception as e:
        return {"ok": False, "message": f"❌ Gagal edit: {e}"}


async def channel_detail(tg_id: int) -> dict:
    """Detail channel/grup: jumlah member, username, deskripsi."""
    from telethon.tl.functions.channels import GetFullChannelRequest

    client = await get_mtproto()
    if client is None:
        ok, msg = await start_mtproto(await get_cfg())
        if not ok:
            return {"ok": False, "message": msg}
        client = await get_mtproto()
    try:
        peer = await client.get_input_entity(int(tg_id))
        full = await client(GetFullChannelRequest(channel=peer))
        fc = full.full_chat
        return {
            "ok": True,
            "title": getattr(fc, "title", ""),
            "username": getattr(fc, "username", "") or "",
            "about": getattr(fc, "about", "") or "",
            "participants_count": getattr(fc, "participants_count", 0),
            "admin_count": getattr(fc, "admins_count", 0),
        }
    except Exception as e:
        return {"ok": False, "message": f"❌ Gagal ambil detail: {e}"}


async def new_invite(tg_id: int) -> dict:
    """Buat invite link baru untuk channel/grup."""
    from telethon.tl.functions.messages import ExportChatInviteRequest

    client = await get_mtproto()
    if client is None:
        ok, msg = await start_mtproto(await get_cfg())
        if not ok:
            return {"ok": False, "message": msg}
        client = await get_mtproto()
    try:
        peer = await client.get_input_entity(int(tg_id))
        inv = await client(ExportChatInviteRequest(peer=peer))
        link = inv.link or ""
        return {"ok": True, "invite": link,
                "message": f"✅ Invite link baru: {link}" if link else "✅ Link: (kosong, pakai username)"}
    except Exception as e:
        return {"ok": False, "message": f"❌ Gagal buat invite: {e}"}


async def delete_entity(tg_id: int) -> dict:
    """Hapus channel/grup di Telegram (TIDAK BISA DIURAI KEMBALI!)."""
    from telethon.tl.functions.channels import DeleteChannelRequest

    client = await get_mtproto()
    if client is None:
        ok, msg = await start_mtproto(await get_cfg())
        if not ok:
            return {"ok": False, "message": msg}
        client = await get_mtproto()
    try:
        peer = await client.get_input_entity(int(tg_id))
        await client(DeleteChannelRequest(channel=peer))
        return {"ok": True, "message": "✅ Channel/grup dihapus permanen dari Telegram"}
    except Exception as e:
        return {"ok": False, "message": f"❌ Gagal hapus: {e}"}


async def set_username(tg_id: int, username: str) -> dict:
    """Set username publik (@...) untuk channel/grup."""
    from telethon.tl.functions.channels import UpdateUsernameRequest

    client = await get_mtproto()
    if client is None:
        ok, msg = await start_mtproto(await get_cfg())
        if not ok:
            return {"ok": False, "message": msg}
        client = await get_mtproto()
    username = username.strip().lstrip("@")
    if not username:
        return {"ok": False, "message": "❌ Username kosong"}
    try:
        peer = await client.get_input_entity(int(tg_id))
        await client(UpdateUsernameRequest(channel=peer, username=username))
        return {"ok": True, "username": username,
                "message": f"✅ Username publik di-set: @{username}"}
    except Exception as e:
        return {"ok": False, "message": f"❌ Gagal set username: {e}"}


async def check_invite(link: str) -> dict:
    """Cek invite link channel/grup sebelum join (preview info)."""
    from telethon.tl.functions.messages import CheckChatInviteRequest

    client = await get_mtproto()
    if client is None:
        ok, msg = await start_mtproto(await get_cfg())
        if not ok:
            return {"ok": False, "message": msg}
        client = await get_mtproto()
    link = link.strip()
    if link and not link.startswith("http") and not link.startswith("@"):
        link = f"https://t.me/+{link}" if not link.startswith("/") else link
    try:
        chat = await client(CheckChatInviteRequest(link))
        return {
            "ok": True,
            "title": getattr(chat, "title", "") or getattr(chat, "username", "") or "?",
            "username": getattr(chat, "username", "") or "",
            "participants_count": getattr(chat, "participants_count", 0),
            "type": getattr(chat, "broadcast", False) and "channel" or "group",
        }
    except Exception as e:
        return {"ok": False, "message": f"❌ Invite link tidak valid / tidak bisa diakses: {e}"}


# --------------------------------------------------------------------------
# Role & izin create (owner / member whitelist / user biasa)
# --------------------------------------------------------------------------
async def get_role(tg_id: int) -> str:
    """'owner' (3 preset) | 'member' (whitelist) | 'user'."""
    row = await db.query_one(
        "SELECT 1 AS x FROM owners WHERE tg_id=?", (int(tg_id),)
    )
    if row:
        return "owner"
    row = await db.query_one(
        "SELECT 1 AS x FROM creators WHERE tg_id=?", (int(tg_id),)
    )
    if row:
        return "member"
    return "user"


async def global_create_limit() -> int:
    try:
        return max(0, int((await get_cfg()).get("CREATE_LIMIT", "10")))
    except (ValueError, TypeError):
        return 10


async def create_permission(tg_id: int) -> dict:
    """Cek izin + sisa limit untuk create channel/grup.

    Return: {allowed: bool, role: str, limit: int|None, used: int, reason: str}
    """
    tg_id = int(tg_id)
    role = await get_role(tg_id)
    if role == "owner":
        return {"allowed": True, "role": "owner", "limit": None,
                "used": 0, "reason": "Owner"}
    if role == "member":
        c = await db.get_creator(tg_id)
        used = (c.get("used") if c else None) or 0
        limit = (c.get("max_create") if c else None)
        if not limit:
            limit = await global_create_limit()
        if used >= limit:
            return {"allowed": False, "role": "member", "limit": limit,
                    "used": used,
                    "reason": f"Limit create kamu sudah habis ({used}/{limit}). "
                              f"Hubungi owner untuk tambah limit."}
        return {"allowed": True, "role": "member", "limit": limit,
                "used": used, "reason": f"Sisa limit: {limit - used}"}
    return {"allowed": False, "role": "user", "limit": None, "used": 0,
            "reason": "Fitur create channel/grup khusus <b>owner</b> dan "
                      "<b>member yang diizinkan owner</b>. Hubungi owner "
                      "lewat menu 💬 Chat dengan Owner untuk minta izin."}


async def record_creation(tg_id: int):
    """Tingkatkan counter used (hanya member; owner tanpa limit)."""
    tg_id = int(tg_id)
    if await get_role(tg_id) == "member":
        await db.bump_creator_used(tg_id)


# --------------------------------------------------------------------------
# Chat dengan Owner (relay user <-> owner)
# --------------------------------------------------------------------------
# relay: message_id di chat owner -> tg_id user pengirim
OWNER_RELAY: dict[int, int] = {}


async def send_to_owner(bot, from_user, text: str) -> tuple[bool, str]:
    """Teruskan pesan user ke owner (dengan konteks pengirim)."""
    import html as _html
    cfg = await get_cfg()
    owner_id = int(cfg.get("OWNER_CHAT_ID", "8861238621"))
    name = _html.escape(from_user.full_name or "User")
    uname = f"@{_html.escape(from_user.username)}" if from_user.username else "-"
    payload = (
        f"💬 <b>Pesan dari {name}</b> ({uname})\n"
        f"🆔 ID: <code>{from_user.id}</code>\n\n"
        f"{_html.escape(text)}\n\n"
        f"<i>↩️ Reply pesan ini untuk membalas user.</i>"
    )
    try:
        msg = await bot.send_message(owner_id, payload, parse_mode="HTML")
        OWNER_RELAY[msg.id] = int(from_user.id)
        await db.log("info", "owner-chat",
                     f"Pesan dari {from_user.id} diteruskan ke owner")
        return True, ("✅ Pesanmu sudah diteruskan ke owner. "
                      "Balasan owner akan diteruskan ke kamu.")
    except Exception as e:
        return False, f"❌ Gagal meneruskan ke owner: {e}"


async def route_owner_reply(bot, text: str, target_user_id: int) -> bool:
    """Teruskan balasan owner ke user yang bersangkutan."""
    import html as _html
    try:
        await bot.send_message(
            int(target_user_id),
            f"💬 <b>Balasan dari Owner</b>:\n\n{_html.escape(text)}",
            parse_mode="HTML",
        )
        return True
    except Exception:
        return False
async def resolve_username(bot, username: str) -> dict:
    """Cek ID dari username publik (@user, @channel, @grup)."""
    username = username.strip()
    if username and not username.startswith("@"):
        username = "@" + username
    try:
        chat = await bot.get_chat(chat_id=username)
    except Exception as e:
        return {"ok": False, "message": f"❌ Tidak ditemukan: {e}"}
    ctype = chat.type
    return {
        "ok": True,
        "id": chat.id,
        "display_id": str(chat.id),
        "type": ctype,
        "username": getattr(chat, "username", None),
        "title": getattr(chat, "title", "") or (getattr(chat, "first_name", "") or ""),
    }


async def resolve_chat_info(bot, chat_id: str) -> dict:
    """Cek info chat dari ID numerik (mis. -1001234567890 atau 123456789)."""
    try:
        cid = int(str(chat_id).strip())
    except ValueError:
        return {"ok": False, "message": "❌ ID harus angka"}
    try:
        chat = await bot.get_chat(chat_id=cid)
    except Exception as e:
        return {"ok": False, "message": f"❌ Tidak bisa diakses: {e}"}
    return {
        "ok": True,
        "id": chat.id,
        "display_id": str(chat.id),
        "type": chat.type,
        "username": getattr(chat, "username", None),
        "title": getattr(chat, "title", "") or (getattr(chat, "first_name", "") or ""),
    }


async def broadcast(bot, users, text: str, media=None) -> dict:
    """Kirim pesan ke semua user yang pernah pakai bot."""
    sent, failed = 0, 0
    for u in users:
        try:
            if media:
                await bot.send_photo(u["tg_id"], media=media["photo"], caption=text)
            else:
                await bot.send_message(u["tg_id"], text)
            sent += 1
        except Exception:
            failed += 1
    return {"sent": sent, "failed": failed}
