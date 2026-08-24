"""Konfigurasi aplikasi.

Prioritas nilai: database (diubah via panel admin) > file .env > default.
Secrets (token, api key) HANYA disimpan di .env / database, tidak pernah
dihardcode di frontend.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ------------------------------------------------------------------ default
DEFAULTS = {
    # Telegram
    "BOT_TOKEN": "",
    "API_ID": "",
    "API_HASH": "",
    "BOT_USERNAME": "pallbot",
    # Admin website
    "ADMIN_PASSWORD": "pall123",
    # AI
    "AI_PROVIDER": "gemini",          # gemini | openai
    "AI_PROJECT": "216372639628",     # project number Google (Gemini)
    "AI_MODEL": "gemini-2.0-flash",
    "AI_KEY": "",                     # JANGAN hardcode — isi di .env / Panel Admin
    "AI_BASE_URL": "https://api.openai.com/v1",
    "AI_OPENAI_MODEL": "gpt-4o-mini",
    # Izin & limit create channel/grup
    "CREATE_LIMIT": "10",             # default limit per member yang di-whitelist
    "OWNER_CHAT_ID": "8861238621",    # tujuan "Chat dengan Owner" (Pall utama)
    # Userbot (akun user untuk fitur create channel/grup)
    "USER_PHONE": "",                 # nomor login userbot, format 62812...
    "USER_2FA": "",                   # password 2FA akun userbot (untuk transfer owner)
    # Lainnya
    "WEB_PORT": "8000",
}

# Key yang boleh ditampilkan ke frontend (tanpa nilai rahasia)
SAFE_SETTINGS = [
    "BOT_USERNAME", "AI_PROVIDER", "AI_PROJECT", "AI_MODEL",
    "AI_BASE_URL", "AI_OPENAI_MODEL", "CREATE_LIMIT", "OWNER_CHAT_ID",
    "USER_PHONE",
]

# Key rahasia — nilai-nya tidak pernah dikirim ke browser
SECRET_SETTINGS = ["BOT_TOKEN", "API_ID", "API_HASH", "ADMIN_PASSWORD",
                   "AI_KEY", "USER_2FA"]

# Pemilik bot (admin) — bisa ditambah via database
PRESET_OWNERS = [
    (8861238621, "Pall (Akun Utama)"),
    (8719750003, "Pall (Akun Kedua)"),
    (8897520559, "Pacar Pall"),
]

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "pallbot.db"
SESSION_DIR = DATA_DIR


def _env(key: str) -> str:
    val = os.getenv(key, "")
    return val.strip()


def env_config() -> dict:
    """Konfigurasi dari .env (atau default)."""
    return {k: (_env(k) if _env(k) else DEFAULTS.get(k, "")) for k in DEFAULTS}


class Config:
    """Akses konfigurasi: DB settings > .env > default."""

    def __init__(self):
        self._base = env_config()

    # -- generic -----------------------------------------------------------
    def all_env(self) -> dict:
        return dict(self._base)

    def get(self, key: str, db_value: str | None = None) -> str:
        if db_value is not None and str(db_value).strip():
            return str(db_value).strip()
        return self._base.get(key, "")

    def apply_db(self, settings: dict) -> dict:
        """Gabungkan base dengan settings dari DB -> dict final."""
        out = dict(self._base)
        for k in out:
            if k in settings and str(settings[k]).strip():
                out[k] = str(settings[k]).strip()
        return out


config = Config()
