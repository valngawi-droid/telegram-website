#!/usr/bin/env python3
"""Login USERBOT sekali jalan — WAJIB untuk fitur create channel/grup.

Jalankan di VPS:
    cd /opt/pallbot
    .venv/bin/python deploy/userbot_login.py

Script akan:
  1. minta kode login yang dikirim Telegram ke nomormu
  2. (kalau ada 2FA) minta password 2FA
  3. menyimpan session ke data/pallbot_user.session  (tidak perlu login lagi)
  4. self-test: buat channel "Uji Userbot" lalu hapus lagi

Catatan penting:
  - Telegram mewajibkan 2FA AKTIF di akun ini untuk transfer ownership.
    Kalau 2FA belum aktif, aktifkan dulu di Telegram, tunggu 24 jam,
    lalu transfer ownership baru bisa.
  - Sesi baru juga harus berumur > 24 jam untuk transfer ownership pertama.
    (Create channel tetap langsung bisa.)
"""
import asyncio
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.chdir(BASE)

from dotenv import load_dotenv
load_dotenv(BASE / ".env")


def get_env(k):
    return os.getenv(k, "").strip()


async def main():
    from telethon import TelegramClient

    api_id = get_env("API_ID")
    api_hash = get_env("API_HASH")
    phone = get_env("USER_PHONE")

    print("=" * 56)
    print("  PALLBOT — LOGIN USERBOT (sekali saja)")
    print("=" * 56)

    if not (api_id and api_hash):
        print("❌ API_ID / API_HASH belum di-set di .env")
        print("   nano /opt/pallbot/.env  →  API_ID=... API_HASH=...")
        return
    if not phone:
        print("❌ USER_PHONE belum di-set di .env")
        print("   Contoh: USER_PHONE=628861238621  (tanpa +, tanpa 0 di depan 8)")
        print("   Pakai salah satu akunmu yang MAU jadi akun userbot.")
        return

    (BASE / "data").mkdir(exist_ok=True)
    session = str(BASE / "data" / "pallbot_user")

    client = TelegramClient(session, int(api_id), api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ Sudah login: @{me.username} (id={me.id})")
    else:
        print(f"\n📱 Login untuk nomor: {phone}")
        print("   Cek aplikasi Telegram kamu untuk kode 5 digit...\n")
        await client.start(phone=phone)  # interaktif: code + 2FA (jika ada)
        me = await client.get_me()
        print(f"\n✅ Login sukses: {me.first_name} @{me.username} (id={me.id})")

    # --- cek 2FA ---
    from telethon.tl.functions.account import GetPasswordRequest
    pw = await client(GetPasswordRequest())
    if pw.has_password:
        print("🔐 2FA: AKTIF di akun ini (wajib untuk transfer ownership).")
        if not get_env("USER_2FA"):
            print("⚠️  USER_2FA belum di-set di .env — isi password 2FA-mu")
            print("    agar fitur 'pilih owner' (transfer ownership) bisa jalan.")
    else:
        print("⚠️  2FA: BELUM AKTIF. Telegram mewajibkan 2FA untuk transfer")
        print("    ownership. Aktifkan: Telegram → Settings → Privacy →")
        print("    Two-Step Verification, lalu tunggu 24 jam.")

    # --- self-test: create + delete ---
    print("\n🧪 Self-test: membuat channel 'Uji Userbot' ...")
    try:
        from telethon.tl.functions.channels import (
            CreateChannelRequest,
            DeleteChannelRequest,
        )
        r = await client(
            CreateChannelRequest(title="Uji Userbot", about="akan dihapus")
        )
        chat = None
        for c in (getattr(r, "chats", None) or []):
            if getattr(c, "title", None) == "Uji Userbot":
                chat = c
                break
        if chat is None and getattr(r, "chats", None):
            chat = r.chats[0]
        if chat is None:
            print("⚠️  Channel dibuat tapi tidak terdeteksi — cek manual di Telegram")
        else:
            print(f"✅ Channel dibuat: id={chat.id}")
            await client(DeleteChannelRequest(channel=chat))
            print("✅ Channel dihapus lagi. Userbot SIAP dipakai!")
    except Exception as e:
        print(f"❌ Self-test gagal: {e}")
        print("   (Fitur create mungkin tidak bisa dipakai — cek akses 2FA/verifikasi)")

    # --- simpan string session (opsional, backup) ---
    try:
        ss = await client.session.save()
        print("\n🔑 String session (backup, JANGAN di-share):")
        print(ss)
    except Exception:
        pass

    await client.disconnect()
    print("\nSelesai. Sekarang fitur 'Buat Channel/Grup' siap dipakai.")


if __name__ == "__main__":
    asyncio.run(main())
