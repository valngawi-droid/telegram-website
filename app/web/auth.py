"""Login admin sederhana: password + token sesi (itsdangerous).

Secret key sesi disimpan di DB sehingga token tetap valid setelah restart.
"""
from __future__ import annotations

import hashlib

from fastapi import Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from ..db import db

SALT = "pallbot-admin-v1"
MAX_AGE = 60 * 60 * 12  # 12 jam


async def get_secret() -> str:
    row = await db.query_one("SELECT value FROM settings WHERE key='__secret'")
    if row and row["value"]:
        return row["value"]
    import secrets as _s
    secret = _s.token_hex(32)
    await db.set_setting("__secret", secret)
    return secret


def verify_token(secret: str, token: str) -> bool:
    s = URLSafeTimedSerializer(secret, salt=SALT)
    try:
        s.loads(token, max_age=MAX_AGE)
        return True
    except BadSignature:
        return False


def make_token(secret: str) -> str:
    s = URLSafeTimedSerializer(secret, salt=SALT)
    return s.dumps({"role": "admin"})


async def check_password(cfg: dict, password: str) -> bool:
    expected = cfg.get("ADMIN_PASSWORD", "")
    return bool(expected) and password == expected


async def is_admin_request(request: Request) -> bool:
    token = request.cookies.get("pallbot_admin", "")
    if not token:
        return False
    secret = await get_secret()
    return verify_token(secret, token)
