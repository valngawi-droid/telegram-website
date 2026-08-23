"""FastAPI app — website + REST API PallBot."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .. import services
from ..ai import AIError, ai_chat, ai_test
from ..bot.bot import bot_manager
from ..config import SAFE_SETTINGS, SECRET_SETTINGS, config
from ..db import db, init_db
from ..services import state as appstate
from . import auth

log = logging.getLogger("pallbot.web")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "web" / "templates"))
templates.env.globals["app_name"] = "PallBot"


def _ts(ts):
    if not ts:
        return ""
    from datetime import datetime
    return datetime.fromtimestamp(float(ts)).strftime("%d/%m/%Y %H:%M")


templates.env.filters["ts"] = _ts


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
_mtproto_sig: str = ""


async def _sync_loop():
    """Cek berkala: token bot / kredensial MTProto berubah di DB -> restart."""
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
        except Exception as e:
            log.exception("sync loop error")
        await asyncio.sleep(15)


APP_STARTED_AT = time.time()


async def _reminder_loop():
    """Kirim pengingat (/ingat) yang sudah jatuh tempo."""
    import time as _t
    while True:
        try:
            bot = bot_manager.bot
            if bot is not None and appstate.bot_online:
                for r in await db.get_due_reminders(_t.time()):
                    try:
                        await bot.send_message(
                            r["chat_id"],
                            f"⏰ <b>Pengingat:</b>\n\n{r['text']}",
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    from ..config import PRESET_OWNERS
    await init_db(PRESET_OWNERS)
    cfg = await services.get_cfg()
    token = cfg.get("BOT_TOKEN", "")
    if token:
        await bot_manager.start(token)
        if cfg.get("API_ID") and cfg.get("API_HASH"):
            global _mtproto_sig
            _mtproto_sig = f"{cfg.get('API_ID')}|{cfg.get('API_HASH')}|{token}"
            asyncio.create_task(services.start_mtproto(cfg))
    task = asyncio.create_task(_sync_loop())
    rem_task = asyncio.create_task(_reminder_loop())
    yield
    task.cancel()
    rem_task.cancel()
    await bot_manager.stop()
    await services.stop_mtproto()
    await db.close()


app = FastAPI(title="PallBot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    password: str


class CekIdIn(BaseModel):
    username: str


class CreateIn(BaseModel):
    name: str
    type: str  # channel | group
    about: str = ""
    owner_tg_id: int
    username: str = ""  # optional: username publik @...


class JoinIn(BaseModel):
    link: str


class AIIn(BaseModel):
    message: str
    user_key: str = "web"


class SettingsIn(BaseModel):
    values: dict[str, str]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
async def _cfg() -> dict:
    return await services.get_cfg()


def _public_status() -> dict:
    return {
        "bot_online": appstate.bot_online,
        "bot_username": appstate.bot_username,
        "bot_id": appstate.bot_id,
        "mtproto_online": appstate.mtproto_online,
        "mtproto_ready": appstate.mtproto_ready,
        "last_error": appstate.last_error,
        "updated_at": appstate.updated_at,
    }


async def _counts() -> dict:
    users = await db.get_users()
    channels = await db.get_channels()
    owners = await db.get_owners()
    return {"users": len(users), "channels": len(channels), "owners": len(owners)}


def _page(request: Request, name: str, **ctx):
    cfg = config.all_env()
    ctx.update({
        "bot_username": appstate.bot_username or cfg.get("BOT_USERNAME", ""),
        "bot_online": appstate.bot_online,
        "mtproto_online": appstate.mtproto_online,
    })
    return templates.TemplateResponse(request, name, ctx)


# ---------------------------------------------------------------------------
# Halaman publik
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    counts = await _counts()
    return _page(request, "index.html", counts=counts)


@app.get("/cekid", response_class=HTMLResponse)
async def page_cekid(request: Request):
    return _page(request, "cekid.html")


@app.get("/ai", response_class=HTMLResponse)
async def page_ai(request: Request):
    return _page(request, "ai.html")


@app.get("/admin/login", response_class=HTMLResponse)
async def page_login(request: Request, error: str = ""):
    return _page(request, "login.html", error=error)


@app.get("/channels", response_class=HTMLResponse)
async def page_channels_public(request: Request):
    return _page(request, "channels_public.html",
                 bot_online=appstate.bot_online)


# ---------------------------------------------------------------------------
# Halaman admin
# ---------------------------------------------------------------------------
async def _require_admin(request: Request) -> bool:
    if not await auth.is_admin_request(request):
        return False
    return True


@app.get("/admin", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    if not await _require_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    cfg = await _cfg()
    logs = await db.get_logs(30)
    users = await db.get_users()
    users.sort(key=lambda u: u.get("last_used") or 0, reverse=True)
    return _page(request, "dashboard.html",
                 status=_public_status(), counts=await _counts(),
                 ai_provider=cfg.get("AI_PROVIDER"),
                 ai_model=cfg.get("AI_MODEL") or cfg.get("AI_OPENAI_MODEL"),
                 logs=logs, users=users)


@app.get("/admin/buat", response_class=HTMLResponse)
async def page_create(request: Request):
    if not await _require_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    return _page(request, "create.html", owners=await db.get_owners())


@app.get("/admin/channels", response_class=HTMLResponse)
async def page_channels(request: Request):
    if not await _require_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    return _page(request, "channels.html", channels=await db.get_channels())


@app.get("/admin/pengaturan", response_class=HTMLResponse)
async def page_settings(request: Request):
    if not await _require_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    cfg = await _cfg()
    safe = {k: cfg.get(k, "") for k in SAFE_SETTINGS}
    return _page(request, "settings.html", values=safe)


@app.get("/admin/cekeluar", include_in_schema=False)
async def page_logout(request: Request):
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("pallbot_admin")
    return resp


# ---------------------------------------------------------------------------
# API publik
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def api_health():
    up = int(time.time() - APP_STARTED_AT)
    return {
        "ok": True,
        "app": "PallBot",
        "uptime": up,
        "uptime_str": (
            f"{up // 3600}j {(up % 3600) // 60}m" if up >= 3600 else f"{up // 60}m {up % 60}s"
        ),
        "bot": _public_status(),
        "counts": await _counts(),
    }


@app.get("/api/channels/public")
async def api_channels_public():
    """Daftar channel/grup untuk halaman publik (tanpa data sensitif)."""
    channels = await db.get_channels()
    out = []
    for c in channels:
        link = f"https://t.me/{c['username']}" if c.get("username") else (c.get("invite") or "")
        out.append({
            "name": c["name"],
            "type": c["type"],
            "owner": c.get("owner_label") or "",
            "link": link,
            "created_at": c.get("created_at"),
        })
    return {"ok": True, "channels": out}


@app.get("/api/status")
async def api_status():
    return _public_status()


@app.post("/api/cekid")
async def api_cekid(data: CekIdIn):
    username = data.username.strip()
    if not username:
        return JSONResponse({"ok": False, "message": "Username kosong"}, status_code=400)
    if not appstate.bot_online or not bot_manager.bot:
        return JSONResponse(
            {"ok": False,
             "message": "Bot offline. Isi BOT_TOKEN di Panel Admin → Pengaturan dulu."})
    text = username.lstrip("@")
    if text.lstrip("-").isdigit():
        result = await services.resolve_chat_info(bot_manager.bot, username)
    else:
        result = await services.resolve_username(bot_manager.bot, username)
    return result


@app.post("/api/ai")
async def api_ai(data: AIIn, request: Request):
    msg = (data.message or "").strip()
    if not msg:
        return JSONResponse({"ok": False, "message": "Pesan kosong"}, status_code=400)
    if len(msg) > 2000:
        msg = msg[:2000]
    user_key = (data.user_key or "web")[:64] or "web"
    history = await db.get_ai_history(user_key, limit=10)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": msg})
    await db.add_ai_message(user_key, "user", msg)
    try:
        reply = await ai_chat(await _cfg(), messages)
    except AIError as e:
        return JSONResponse({"ok": False, "message": str(e)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": f"Gagal terhubung ke AI: {e}"})
    await db.add_ai_message(user_key, "assistant", reply)
    return {"ok": True, "reply": reply}


# ---------------------------------------------------------------------------
# API admin
# ---------------------------------------------------------------------------
async def _admin_guard(request: Request):
    if not await auth.is_admin_request(request):
        raise HTTPException(status_code=401, detail="Login dulu")


@app.post("/api/login")
async def api_login(data: LoginIn, request: Request):
    cfg = await _cfg()
    if not await auth.check_password(cfg, data.password):
        raise HTTPException(status_code=401, detail="Password salah")
    token = auth.make_token(await auth.get_secret())
    resp = JSONResponse({"ok": True, "token": token})
    resp.set_cookie("pallbot_admin", token, httponly=True, samesite="lax", max_age=60 * 60 * 12)
    return resp


@app.post("/api/logout")
async def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("pallbot_admin")
    return resp


@app.get("/api/owners")
async def api_owners(request: Request):
    await _admin_guard(request)
    return {"ok": True, "owners": await db.get_owners()}


@app.post("/api/create")
async def api_create(data: CreateIn, request: Request):
    await _admin_guard(request)
    if data.type not in ("channel", "group"):
        raise HTTPException(400, "type harus channel atau group")
    if len(data.name.strip()) < 2:
        raise HTTPException(400, "nama terlalu pendek")
    if not data.owner_tg_id:
        raise HTTPException(400, "owner_tg_id wajib diisi")
    result = await services.create_entity(
        name=data.name.strip(),
        etype=data.type,
        owner_tg_id=int(data.owner_tg_id),
        about=(data.about or "").strip()[:500],
        source="website",
    )
    username_out = result.get("username", "")
    # set username publik (opsional)
    if result.get("ok") and data.username.strip():
        u = await services.set_username(result.get("tg_id"), data.username)
        if u.get("ok"):
            username_out = u["username"]
            result["username"] = username_out
            result["invite"] = f"https://t.me/{username_out}"
        else:
            result["message"] = (result.get("message", "") +
                                 f" Username publik gagal: {u.get('message')}").strip()
    if result.get("ok"):
        owners = {o["tg_id"]: o["label"] for o in await db.get_owners()}
        label = owners.get(result["owner_tg_id"], str(result["owner_tg_id"]))
        await db.add_channel(
            name=result.get("name", data.name),
            ctype=data.type,
            tg_id=result.get("tg_id"),
            username=username_out,
            invite=result.get("invite", ""),
            owner_tg_id=result["owner_tg_id"],
            owner_label=label,
            source="website",
        )
    return result


@app.post("/api/join")
async def api_join(data: JoinIn, request: Request):
    await _admin_guard(request)
    if not data.link.strip():
        raise HTTPException(400, "link kosong")
    return await services.join_invite(data.link)


@app.get("/api/channels")
async def api_channels(request: Request):
    await _admin_guard(request)
    return {"ok": True, "channels": await db.get_channels()}


@app.delete("/api/channels/{cid}")
async def api_delete_channel(cid: int, request: Request):
    await _admin_guard(request)
    await db.remove_channel(cid)
    return {"ok": True}


@app.get("/api/logs")
async def api_logs(request: Request):
    await _admin_guard(request)
    return {"ok": True, "logs": await db.get_logs(100)}


@app.post("/api/ai/test")
async def api_ai_test(request: Request):
    await _admin_guard(request)
    try:
        return {"ok": True, "message": await ai_test(await _cfg())}
    except AIError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:
        return {"ok": False, "message": f"Error koneksi: {e}"}


class AIKeyIn(BaseModel):
    user_key: str = "web"


@app.post("/api/ai/clear")
async def api_ai_clear(data: AIKeyIn):
    user_key = (data.user_key or "web")[:64] or "web"
    await db.clear_ai_history(user_key)
    return {"ok": True}


@app.get("/api/users")
async def api_users(request: Request):
    await _admin_guard(request)
    users = await db.get_users()
    users.sort(key=lambda u: u.get("last_used") or 0, reverse=True)
    return {"ok": True, "users": users}


class BroadcastIn(BaseModel):
    text: str


@app.post("/api/broadcast")
async def api_broadcast(data: BroadcastIn, request: Request):
    await _admin_guard(request)
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(400, "teks kosong")
    if not appstate.bot_online or not bot_manager.bot:
        return {"ok": False, "message": "Bot offline — broadcast tidak bisa dikirim"}
    users = await db.get_users()
    res = await services.broadcast(bot_manager.bot, users, text)
    return {"ok": True, **res}


class EditChIn(BaseModel):
    name: str | None = None
    about: str | None = None


@app.post("/api/channels/{cid}/edit")
async def api_ch_edit(cid: int, data: EditChIn, request: Request):
    await _admin_guard(request)
    row = await db.query_one("SELECT * FROM channels WHERE id=?", (int(cid),))
    if not row:
        raise HTTPException(404, "channel tidak ditemukan")
    result = await services.edit_entity(row["tg_id"], name=data.name, about=data.about)
    if result.get("ok"):
        if data.name and data.name.strip():
            await db.execute("UPDATE channels SET name=? WHERE id=?",
                             (data.name.strip(), int(cid)))
    return result


@app.post("/api/channels/{cid}/invite")
async def api_ch_invite(cid: int, request: Request):
    await _admin_guard(request)
    row = await db.query_one("SELECT * FROM channels WHERE id=?", (int(cid),))
    if not row:
        raise HTTPException(404, "channel tidak ditemukan")
    result = await services.new_invite(row["tg_id"])
    if result.get("ok") and result.get("invite"):
        await db.execute("UPDATE channels SET invite=? WHERE id=?",
                         (result["invite"], int(cid)))
    return result


@app.post("/api/channels/{cid}/detail")
async def api_ch_detail(cid: int, request: Request):
    await _admin_guard(request)
    row = await db.query_one("SELECT * FROM channels WHERE id=?", (int(cid),))
    if not row:
        raise HTTPException(404, "channel tidak ditemukan")
    return await services.channel_detail(row["tg_id"])


@app.delete("/api/channels/{cid}/tg")
async def api_ch_delete_tg(cid: int, request: Request):
    await _admin_guard(request)
    row = await db.query_one("SELECT * FROM channels WHERE id=?", (int(cid),))
    if not row:
        raise HTTPException(404, "channel tidak ditemukan")
    result = await services.delete_entity(row["tg_id"])
    if result.get("ok"):
        await db.remove_channel(cid)
    return result


@app.post("/api/settings")
async def api_settings(data: SettingsIn, request: Request):
    await _admin_guard(request)
    allowed = list(config.all_env().keys())
    changed = {}
    for k, v in (data.values or {}).items():
        if k not in allowed:
            continue
        old = await db.query_one("SELECT value FROM settings WHERE key=?", (k,))
        old_val = old["value"] if old else ""
        new_val = str(v).strip()
        if new_val != old_val:
            if new_val:
                await db.set_setting(k, new_val)
            else:
                await db.execute("DELETE FROM settings WHERE key=?", (k,))
            changed[k] = True
    await db.log("info", "admin", f"Pengaturan diubah: {', '.join(changed) or '-'}")

    # restart layanan terkait
    cfg = await _cfg()
    if changed.get("BOT_TOKEN") or changed.get("ADMIN_PASSWORD"):
        pass
    if changed.get("BOT_TOKEN"):
        await bot_manager.restart_if_changed(cfg.get("BOT_TOKEN", ""))
    if any(k in changed for k in ("API_ID", "API_HASH", "BOT_TOKEN")):
        global _mtproto_sig
        _mtproto_sig = ""  # paksa cek ulang di sync loop / langsung
        if cfg.get("API_ID") and cfg.get("API_HASH") and cfg.get("BOT_TOKEN"):
            ok, msg = await services.start_mtproto(cfg)
            _mtproto_sig = f"{cfg.get('API_ID')}|{cfg.get('API_HASH')}|{cfg.get('BOT_TOKEN')}"
    return {"ok": True, "changed": list(changed.keys())}


@app.post("/api/owners")
async def api_add_owner(data: dict, request: Request):
    await _admin_guard(request)
    tg_id = int(data.get("tg_id", 0))
    label = str(data.get("label", "Owner")).strip()[:60]
    if not tg_id or not label:
        raise HTTPException(400, "tg_id dan label wajib")
    await db.add_owner(tg_id, label, is_admin=bool(data.get("is_admin", True)))
    return {"ok": True}


@app.delete("/api/owners/{tg_id}")
async def api_remove_owner(tg_id: int, request: Request):
    await _admin_guard(request)
    await db.remove_owner(tg_id)
    return {"ok": True}
