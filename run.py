"""Entry point — PallBot (bot Telegram multi fungsi + userbot create channel).

Website sudah dihapus (v5) — semua fitur kini via bot Telegram.
Konfigurasi: file .env di root proyek (lihat .env.example).

Usage:
    python run.py
"""
import asyncio
import logging
import signal
import sys

from app.config import PRESET_OWNERS, config
from app.db import db, init_db
from app import services, userbot
from app.bot.bot import bot_manager
from app.runner import reminder_loop, sync_loop
from app.services import state as appstate


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("pallbot")

    await init_db(PRESET_OWNERS)
    cfg = await services.get_cfg()

    print("=" * 52)
    print("  PALLBOT — bot Telegram multi fungsi (v5, bot-only)")
    print("=" * 52)

    token = cfg.get("BOT_TOKEN", "")
    if token:
        await bot_manager.start(token)
        print("🤖 Bot Telegram: memulai polling...")
    else:
        print("⚠️  BOT_TOKEN kosong di .env — bot tidak jalan. Isi lalu restart.")

    if cfg.get("API_ID") and cfg.get("API_HASH") and token:
        print("🛰️  MTProto: memulai...")
        asyncio.create_task(services.start_mtproto(cfg))
    else:
        print("🛰️  MTProto: belum lengkap (butuh API_ID, API_HASH, BOT_TOKEN)")

    ub = await userbot.userbot_status(cfg)
    if ub["logged_in"]:
        print(f"👤 Userbot: ONLINE @{ub['me_username']} (create channel siap)")
    else:
        print(f"👤 Userbot: belum login — {ub['message']}")
        print("    (fitur create channel/grup butuh userbot: python deploy/userbot_login.py)")

    t_sync = asyncio.create_task(sync_loop())
    t_rem = asyncio.create_task(reminder_loop())
    print("✅ Jalankan. Stop dengan Ctrl+C")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, stop.set)
        except NotImplementedError:
            pass

    await stop.wait()
    print("🛑 Shutdown...")
    t_sync.cancel()
    t_rem.cancel()
    await bot_manager.stop()
    await services.stop_mtproto()
    await userbot.stop_userbot()
    await db.close()
    print("Sudah selesai.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
