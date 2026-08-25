"""Loop background: sync konfigurasi + pengingat (reminder)."""
from __future__ import annotations

import asyncio
import html
import logging
import time

from . import services
from .bot.bot import bot_manager
from .db import db
from .services import state as appstate

log = logging.getLogger("pallbot.runner")

_mtproto_sig: str = ""


async def sync_loop():
    """Cek berkala: token bot / kredensial MTProto berubah di .env -> restart."""
    global _mtproto_sig
    while True:
        try:
            cfg = await services.get_cfg()
            await bot_manager.restart_if_changed(cfg.get("BOT_TOKEN", ""))
            mt_sig = f"{cfg.get('API_ID')}|{cfg.get('API_HASH')}|{cfg.get('BOT_TOKEN')}"
            want = bool(cfg.get("API_ID") and cfg.get("API_HASH") and cfg.get("BOT_TOKEN"))
            if want and not appstate.mtproto_online and mt_sig != _mtproto_sig:
                _mtproto_sig = mt_sig
                await services.start_mtproto(cfg)
            elif not want:
                _mtproto_sig = ""
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("sync loop error")
        await asyncio.sleep(15)


async def reminder_loop():
    """Kirim pengingat (/ingat) yang sudah jatuh tempo."""
    while True:
        try:
            bot = bot_manager.bot
            if bot is not None and appstate.bot_online:
                for r in await db.get_due_reminders(time.time()):
                    try:
                        await bot.send_message(
                            r["chat_id"],
                            f"⏰ <b>Pengingat:</b>\n\n{html.escape(r['text'])}",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
                    await db.done_reminder(r["id"])
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(20)
