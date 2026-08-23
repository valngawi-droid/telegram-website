"""Entry point — jalankan website + bot Telegram.

Usage:
    python run.py            # pakai port dari .env (default 8000)
    WEB_PORT=9000 python run.py
"""
import os

import uvicorn

from app.config import config

if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT") or config.all_env().get("WEB_PORT") or 8000)
    uvicorn.run(
        "app.web.app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
