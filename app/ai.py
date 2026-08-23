"""Klien AI multi-provider.

Provider:
  - gemini  : Google Generative Language API (project number) — default,
              sesuai project "AI TELEGRAM" / projects/216372639628
  - openai  : kompatibel OpenAI /v1/chat/completions (OpenAI, Groq,
              OpenRouter, localhost, dll)

Semua parameter (provider, model, key, project, base url) bisa diubah
langsung dari panel admin website.
"""
from __future__ import annotations

import httpx

SYSTEM_PROMPT = (
    "Kamu adalah AI TELEGRAM, asisten AI ramah yang berjalan di dalam bot "
    "Telegram milik Pall. Jawab dalam bahasa yang sama dengan pengguna "
    "(biasanya Bahasa Indonesia), singkat, jelas, dan to the point. "
    "Kalau diminta bantuan soal Telegram (channel, grup, bot, link invite), "
    "berikan langkah yang praktis."
)


class AIError(Exception):
    pass


async def _gemini(cfg: dict, messages: list[dict]) -> str:
    project = cfg.get("AI_PROJECT", "").strip()
    model = cfg.get("AI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
    key = cfg.get("AI_KEY", "").strip()
    if not key:
        raise AIError("AI_KEY belum diisi (menu Pengaturan / .env)")

    contents = [{"role": "user", "parts": [{"text": SYSTEM_PROMPT}]}]
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    if project:
        url = f"https://generativelanguage.googleapis.com/v1beta/projects/{project}/models/{model}:generateContent"
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            url,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={"contents": contents,
                  "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7}},
        )
    if r.status_code != 200:
        try:
            err = r.json().get("error", {})
            raise AIError(f"Gemini {r.status_code}: {err.get('message', r.text[:200])}")
        except AIError:
            raise
        except Exception:
            raise AIError(f"Gemini {r.status_code}: {r.text[:200]}")

    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        blocked = data.get("promptFeedback", {}).get("blockReason")
        if blocked:
            raise AIError(f"Jawaban diblokir AI (alasan: {blocked})")
        raise AIError("Respons Gemini kosong")


async def _openai(cfg: dict, messages: list[dict]) -> str:
    key = cfg.get("AI_KEY", "").strip()
    if not key:
        raise AIError("AI_KEY belum diisi (menu Pengaturan / .env)")
    base = (cfg.get("AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = cfg.get("AI_OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    payload_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    payload_messages += [
        {"role": "assistant" if m["role"] == "assistant" else "user", "content": m["content"]}
        for m in messages
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": payload_messages, "max_tokens": 1024},
        )
    if r.status_code != 200:
        raise AIError(f"OpenAI {r.status_code}: {r.text[:200]}")
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise AIError("Respons OpenAI kosong")


async def ai_chat(cfg: dict, messages: list[dict]) -> str:
    """Panggil AI. messages = [{role: user|assistant, content: str}]"""
    provider = (cfg.get("AI_PROVIDER") or "gemini").strip().lower()
    if provider == "gemini":
        return await _gemini(cfg, messages)
    if provider in ("openai", "openai-compatible", "openrouter", "groq"):
        return await _openai(cfg, messages)
    raise AIError(f"Provider AI tidak dikenal: {provider}")


async def ai_test(cfg: dict) -> str:
    """Tes koneksi AI — mengembalikan pesan sukses/gagal."""
    reply = await ai_chat(cfg, [{"role": "user", "content": "Balas hanya dengan: OK"}])
    return f"✅ AI ({cfg.get('AI_PROVIDER', 'gemini')}/{cfg.get('AI_MODEL') or cfg.get('AI_OPENAI_MODEL')}) merespons: {reply[:80]}"
