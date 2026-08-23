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


# --------------------------------------------------------------------------
# Cek ID via Bot API
# --------------------------------------------------------------------------
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
