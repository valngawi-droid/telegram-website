"""Userbot (Telethon, mode AKUN USER) — untuk fitur create channel/grup.

Telegram MEMBATASI bot membuat channel/grup (CreateChannelRequest tidak bisa
dipanggil bot). Solusi: userbot — akun user yang di-login sekali lewat
`deploy/userbot_login.py`, session tersimpan di data/pallbot_user.session.

Alur create:
  1. userbot membuat channel/grup (userbot = creator sementara)
  2. kalau owner terpilih == akun userbot   -> selesai (owner sejati)
  3. kalau owner terpilih beda              -> channels.editCreator (butuh
     2FA aktif di akun userbot; sesi baru butuh tunggu 24 jam)
  4. fallback: owner dijadikan admin penuh (rank "Owner")
  5. bot juga ditambah sebagai admin penuh (biar bisa kelola/broadcast)
"""
from __future__ import annotations

import logging
import struct
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.tlobject import TLRequest

from .config import SESSION_DIR
from .db import db

log = logging.getLogger("pallbot.userbot")

USER_SESSION_NAME = "pallbot_user"

_user_client: TelegramClient | None = None


# ---------------------------------------------------------------------------
# Raw request: channels.editCreator#8f38cd1f
#   channel:InputChannel user_id:InputUser password:InputCheckPasswordSRP = Updates
# (belum tersedia di TL generator Telethon 1.44)
# ---------------------------------------------------------------------------
class EditCreatorRequest(TLRequest):
    CONSTRUCTOR_ID = 0x8f38cd1f
    SUBCLASS_OF_ID = 0x0

    def __init__(self, channel, user_id, password):
        self.channel = channel
        self.user_id = user_id
        self.password = password

    async def resolve(self, client, utils):
        self.channel = utils.get_input_channel(await client.get_input_entity(self.channel))
        self.user_id = utils.get_input_user(await client.get_input_entity(self.user_id))

    def _bytes(self):
        return b"".join(
            (
                struct.pack("<I", self.CONSTRUCTOR_ID),
                self.channel._bytes(),
                self.user_id._bytes(),
                self.password._bytes(),
            )
        )

    @classmethod
    def from_reader(cls, reader):
        channel = reader.tgread_object()
        user_id = reader.tgread_object()
        password = reader.tgread_object()
        return cls(channel=channel, user_id=user_id, password=password)


# ---------------------------------------------------------------------------
# Klien userbot
# ---------------------------------------------------------------------------
def _session_path() -> str:
    return str(SESSION_DIR / USER_SESSION_NAME)


def session_exists() -> bool:
    return any(SESSION_DIR.glob(f"{USER_SESSION_NAME}.session*"))


async def get_user_client(cfg: dict) -> TelegramClient | None:
    """Kembalikan client userbot yang connected+authorized, atau None."""
    global _user_client
    if _user_client is not None:
        try:
            if _user_client.is_connected():
                return _user_client
        except Exception:
            pass
    if not session_exists():
        return None
    api_id = cfg.get("API_ID", "")
    api_hash = cfg.get("API_HASH", "")
    if not (api_id and api_hash):
        return None
    try:
        client = TelegramClient(_session_path(), int(api_id), api_hash)
        await client.connect()
        if await client.is_user_authorized():
            _user_client = client
            return client
        await client.disconnect()
    except Exception as e:
        log.warning("userbot connect gagal: %s", e)
        try:
            await client.disconnect()
        except Exception:
            pass
    return None


async def userbot_status(cfg: dict) -> dict:
    st = {
        "configured": bool(cfg.get("API_ID") and cfg.get("API_HASH")),
        "session_exists": session_exists(),
        "logged_in": False,
        "me_id": 0,
        "me_username": "",
        "message": "",
    }
    if not st["configured"]:
        st["message"] = "API_ID/API_HASH belum di-set"
        return st
    if not st["session_exists"]:
        st["message"] = "Belum login — jalankan deploy/userbot_login.py (sekali saja)"
        return st
    client = await get_user_client(cfg)
    if client is None:
        st["message"] = "Session ada tapi tidak bisa login (api id/hash berganti? hapus data/pallbot_user.session* lalu login ulang)"
        return st
    try:
        me = await client.get_me()
        st.update(logged_in=True, me_id=me.id, me_username=me.username or "", message="OK")
    except Exception as e:
        st["message"] = str(e)
    return st


async def stop_userbot():
    global _user_client
    if _user_client is not None:
        try:
            await _user_client.disconnect()
        except Exception:
            pass
        _user_client = None


# ---------------------------------------------------------------------------
# Operasi
# ---------------------------------------------------------------------------
async def _owner_password_check(client: TelegramClient, pw2fa: str):
    """Bangun InputCheckPasswordSRP/Empty untuk editCreator."""
    from telethon.tl.functions.account import CheckPasswordRequest, GetPasswordRequest
    from telethon.tl.types import InputCheckPasswordEmpty

    pw = await client(GetPasswordRequest())
    if not pw.has_password:
        return None, ("Akun userbot belum mengaktifkan 2FA. Telegram mewajibkan 2FA "
                      "aktif untuk transfer ownership. Aktifkan 2FA di akun userbot "
                      "dulu (Settings > Privacy > Two-Step Verification).")
    if not pw2fa:
        return None, ("Akun userbot punya 2FA — isi USER_2FA di .env / Pengaturan "
                      "untuk transfer ownership.")
    check = await client(CheckPasswordRequest(pw, pw2fa))
    return check, None


async def _add_bot_as_admin(client: TelegramClient, chat, bot_id: int):
    """Tambah bot sebagai admin penuh (agar bot bisa kelola & broadcast)."""
    from telethon.tl.functions.channels import EditAdminRequest, InviteToChannelRequest
    from telethon.tl.types import ChatAdminRights

    try:
        try:
            await client(InviteToChannelRequest(chat, [bot_id]))
        except Exception:
            pass
        rights = ChatAdminRights(
            change_info=True, post_messages=True, edit_messages=True,
            delete_messages=True, ban_users=True, invite_users=True,
            pin_messages=True, add_admins=True, manage_call=True,
            other=True, manage_topics=True,
        )
        await client(EditAdminRequest(channel=chat, user_id=bot_id,
                                      admin_rights=rights, rank="PallBot"))
        return True
    except Exception as e:
        log.warning("gagal tambah bot sebagai admin: %s", e)
        return False


async def create_with_user(cfg: dict, name: str, etype: str,
                           owner_tg_id: int, about: str = "") -> dict:
    """Buat channel/grup via userbot + tunjuk owner."""
    from telethon.tl.functions.channels import (
        CreateChannelRequest,
        EditAdminRequest,
        InviteToChannelRequest,
    )
    from telethon.tl.types import ChatAdminRights

    client = await get_user_client(cfg)
    if client is None:
        return {
            "ok": False,
            "message": (
                "❌ Fitur create butuh <b>userbot</b> (akun user) — Telegram "
                "melarang bot membuat channel/grup.\n\n"
                "Jalankan di VPS (sekali saja):\n"
                "<code>cd /opt/pallbot && .venv/bin/python deploy/userbot_login.py</code>"
            ),
        }

    try:
        result = await client(
            CreateChannelRequest(
                title=name, about=about,
                broadcast=(etype == "channel"),
                megagroup=(etype == "group"),
            )
        )
    except Exception as e:
        await db.log("error", "userbot", f"create gagal: {e}")
        return {"ok": False, "message": f"❌ Gagal membuat {etype}: {e}"}

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
        return {"ok": False,
                "message": "Channel/grup dibuat tapi tidak bisa diidentifikasi. Cek manual di Telegram."}

    tg_id = chat.id
    username = getattr(chat, "username", "") or ""
    me = await client.get_me()
    owner_id = int(owner_tg_id)
    notes = []

    # --- tunjuk owner ---
    if owner_id == me.id:
        notes.append(f"Owner: akun userbot sendiri ({me.id}).")
    else:
        # coba transfer ownership sejati (editCreator, butuh 2FA)
        transferred = False
        try:
            check, err = await _owner_password_check(client, cfg.get("USER_2FA", ""))
            if check is None:
                notes.append("ℹ️ " + err)
            else:
                await client(EditCreatorRequest(channel=chat, user_id=owner_id, password=check))
                transferred = True
                notes.append(f"✅ Ownership dipindahkan ke {owner_id}.")
        except Exception as e:
            notes.append(f"ℹ️ Transfer ownership gagal ({e}); "
                         f"owner dijadikan admin penuh sebagai gantinya.")
        if not transferred:
            try:
                try:
                    await client(InviteToChannelRequest(chat, [owner_id]))
                except Exception:
                    pass
                rights = ChatAdminRights(
                    change_info=True, post_messages=True, edit_messages=True,
                    delete_messages=True, ban_users=True, invite_users=True,
                    pin_messages=True, add_admins=True, manage_call=True,
                    other=True, manage_topics=True,
                )
                await client(EditAdminRequest(channel=chat, user_id=owner_id,
                                              admin_rights=rights, rank="Owner"))
                notes.append(f"{owner_id} ditunjuk sebagai admin penuh (rank 'Owner').")
            except Exception as e2:
                notes.append(f"⚠️ Penunjukan owner {owner_id} gagal: {e2}. Tambahkan manual.")

    # --- bot sebagai admin (biar bisa kelola & broadcast) ---
    bot_id = 0
    try:
        import re
        m = re.match(r"^(\d+):", cfg.get("BOT_TOKEN", ""))
        if m:
            bot_id = int(m.group(1))
    except Exception:
        pass
    if bot_id:
        if await _add_bot_as_admin(client, chat, bot_id):
            notes.append("Bot ditambahkan sebagai admin (untuk kelola/broadcast).")

    invite = f"https://t.me/{username}" if username else ""
    if not invite:
        try:
            from telethon.tl.functions.messages import ExportChatInviteRequest
            inv = await client(ExportChatInviteRequest(peer=chat))
            invite = inv.link or ""
        except Exception:
            invite = ""

    await db.log("info", "userbot", f"create {etype} '{name}' id={tg_id} owner={owner_id}")
    return {
        "ok": True,
        "name": name,
        "tg_id": tg_id,
        "username": username,
        "invite": invite,
        "owner_tg_id": owner_id,
        "message": " ".join(notes),
    }


async def userbot_manage(cfg: dict, tg_id: int, action: str,
                         **kwargs) -> dict | None:
    """Coba operasi (edit/detail/invite/username/delete) lewat userbot.

    Return None kalau userbot tidak tersedia (panggilan fallback ke bot).
    """
    client = await get_user_client(cfg)
    if client is None:
        return None
    try:
        if action == "edit":
            if kwargs.get("name"):
                from telethon.tl.functions.channels import EditTitleRequest
                await client(EditTitleRequest(channel=tg_id, title=kwargs["name"].strip()))
            if kwargs.get("about") is not None:
                from telethon.tl.functions.messages import EditChatAboutRequest
                await client(EditChatAboutRequest(peer=tg_id, about=kwargs["about"].strip()[:500]))
            return {"ok": True, "message": "✅ Berhasil diperbarui"}
        if action == "detail":
            from telethon.tl.functions.channels import GetFullChannelRequest
            full = await client(GetFullChannelRequest(channel=tg_id))
            fc = full.full_chat
            return {
                "ok": True,
                "title": getattr(fc, "title", ""),
                "username": getattr(fc, "username", "") or "",
                "about": getattr(fc, "about", "") or "",
                "participants_count": getattr(fc, "participants_count", 0),
                "admin_count": getattr(fc, "admins_count", 0),
            }
        if action == "invite":
            from telethon.tl.functions.messages import ExportChatInviteRequest
            inv = await client(ExportChatInviteRequest(peer=tg_id))
            link = inv.link or ""
            return {"ok": True, "invite": link,
                    "message": f"✅ Invite link baru: {link}" if link else "✅ (tanpa link)"}
        if action == "username":
            from telethon.tl.functions.channels import UpdateUsernameRequest
            await client(UpdateUsernameRequest(channel=tg_id, username=kwargs["username"].strip()))
            return {"ok": True, "username": kwargs["username"].strip().lstrip("@"),
                    "message": f"✅ Username publik di-set: @{kwargs['username'].strip().lstrip('@')}"}
        if action == "delete":
            from telethon.tl.functions.channels import DeleteChannelRequest
            await client(DeleteChannelRequest(channel=tg_id))
            return {"ok": True, "message": "✅ Channel/grup dihapus permanen dari Telegram"}
    except Exception as e:
        return {"ok": False, "message": f"❌ Gagal ({action}): {e}"}
    return None
