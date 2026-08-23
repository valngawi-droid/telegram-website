"""Database SQLite (aiosqlite) — satu koneksi per proses, dilock untuk aman."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import aiosqlite

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS owners (
    tg_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_used REAL
);
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    tg_id INTEGER,
    username TEXT,
    invite TEXT,
    owner_tg_id INTEGER,
    owner_label TEXT,
    source TEXT DEFAULT 'bot',
    created_at REAL
);
CREATE TABLE IF NOT EXISTS ai_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    level TEXT,
    source TEXT,
    message TEXT
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    tg_id INTEGER,
    due_ts REAL NOT NULL,
    text TEXT NOT NULL,
    done INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS welcome (
    chat_id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    updated REAL
);
CREATE INDEX IF NOT EXISTS idx_ai_user ON ai_messages(user_key, id);
"""


class DB:
    def __init__(self):
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self):
        self._conn = await aiosqlite.connect(DB_PATH)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def execute(self, sql: str, params: tuple = ()) -> int:
        async with self._lock:
            cur = await self._conn.execute(sql, params)
            await self._conn.commit()
            return cur.lastrowid or 0

    async def query(self, sql: str, params: tuple = ()) -> list[dict]:
        async with self._lock:
            cur = await self._conn.execute(sql, params)
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = await self.query(sql, params, )
        return rows[0] if rows else None

    # ------------------------- settings -----------------------------------
    async def get_settings(self) -> dict:
        rows = await self.query("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows}

    async def set_setting(self, key: str, value: str):
        await self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    # ------------------------- owners -------------------------------------
    async def get_owners(self) -> list[dict]:
        return await self.query("SELECT tg_id, label, is_admin FROM owners ORDER BY tg_id")

    async def add_owner(self, tg_id: int, label: str, is_admin: bool = False):
        await self.execute(
            "INSERT OR REPLACE INTO owners(tg_id, label, is_admin) VALUES(?,?,?)",
            (int(tg_id), label, 1 if is_admin else 0),
        )

    async def remove_owner(self, tg_id: int):
        await self.execute("DELETE FROM owners WHERE tg_id=?", (int(tg_id),))

    # ------------------------- users --------------------------------------
    async def touch_user(self, tg_id: int, username: str = "", first_name: str = ""):
        await self.execute(
            "INSERT INTO users(tg_id, username, first_name, last_used) VALUES(?,?,?,?) "
            "ON CONFLICT(tg_id) DO UPDATE SET username=excluded.username, "
            "first_name=excluded.first_name, last_used=excluded.last_used",
            (int(tg_id), username or "", first_name or "", time.time()),
        )

    async def get_users(self) -> list[dict]:
        return await self.query("SELECT tg_id, username, first_name, last_used FROM users")

    # ------------------------- channels -----------------------------------
    async def add_channel(self, name, ctype, tg_id, username, invite, owner_tg_id, owner_label, source):
        await self.execute(
            "INSERT INTO channels(name, type, tg_id, username, invite, owner_tg_id, owner_label, source, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (name, ctype, tg_id or 0, username or "", invite or "",
             owner_tg_id or 0, owner_label or "", source, time.time()),
        )

    async def get_channels(self) -> list[dict]:
        return await self.query("SELECT * FROM channels ORDER BY id DESC")

    async def remove_channel(self, cid: int):
        await self.execute("DELETE FROM channels WHERE id=?", (int(cid),))

    # ------------------------- AI history ---------------------------------
    async def add_ai_message(self, user_key: str, role: str, content: str):
        await self.execute(
            "INSERT INTO ai_messages(user_key, role, content, created_at) VALUES(?,?,?,?)",
            (user_key, role, content, time.time()),
        )

    async def get_ai_history(self, user_key: str, limit: int = 12) -> list[dict]:
        rows = await self.query(
            "SELECT role, content FROM ai_messages WHERE user_key=? ORDER BY id DESC LIMIT ?",
            (user_key, limit),
        )
        return list(reversed(rows))

    async def clear_ai_history(self, user_key: str):
        await self.execute("DELETE FROM ai_messages WHERE user_key=?", (user_key,))

    # ------------------------- logs ----------------------------------------
    async def log(self, level: str, source: str, message: str):
        await self.execute(
            "INSERT INTO logs(ts, level, source, message) VALUES(?,?,?,?)",
            (time.time(), level, source, message[:2000]),
        )

    async def get_logs(self, limit: int = 50) -> list[dict]:
        return await self.query("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))

    # ------------------------- reminders ------------------------------------
    async def add_reminder(self, chat_id: int, tg_id: int, due_ts: float, text: str) -> int:
        return await self.execute(
            "INSERT INTO reminders(chat_id, tg_id, due_ts, text) VALUES(?,?,?,?)",
            (int(chat_id), tg_id or 0, due_ts, text),
        )

    async def get_due_reminders(self, now: float) -> list[dict]:
        return await self.query(
            "SELECT * FROM reminders WHERE done=0 AND due_ts<=?", (now,)
        )

    async def done_reminder(self, rid: int):
        await self.execute("UPDATE reminders SET done=1 WHERE id=?", (int(rid),))

    async def remove_reminder(self, rid: int):
        await self.execute("DELETE FROM reminders WHERE id=?", (int(rid),))

    async def get_reminders(self, chat_id: int = None) -> list[dict]:
        if chat_id is None:
            return await self.query(
                "SELECT * FROM reminders WHERE done=0 ORDER BY due_ts"
            )
        return await self.query(
            "SELECT * FROM reminders WHERE done=0 AND chat_id=? ORDER BY due_ts",
            (int(chat_id),),
        )

    # ------------------------- welcome ---------------------------------------
    async def set_welcome(self, chat_id: int, text: str):
        await self.execute(
            "INSERT INTO welcome(chat_id, text, updated) VALUES(?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET text=excluded.text, updated=excluded.updated",
            (int(chat_id), text, time.time()),
        )

    async def get_welcome(self, chat_id: int) -> str | None:
        row = await self.query_one("SELECT text FROM welcome WHERE chat_id=?", (int(chat_id),))
        return row["text"] if row else None

    async def del_welcome(self, chat_id: int):
        await self.execute("DELETE FROM welcome WHERE chat_id=?", (int(chat_id),))


db = DB()


async def init_db(preset_owners: list[tuple[int, str]]):
    await db.connect()
    owners = await db.get_owners()
    if not owners:
        for tg_id, label in preset_owners:
            await db.add_owner(tg_id, label, is_admin=True)
    await db.log("info", "system", "Database siap")
