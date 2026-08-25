// Klien AI multi-provider — sama persis dengan bot Telegram
// (Gemini dengan project number / OpenAI-compatible)
const cfg = require('./config');

const SYSTEM_PROMPT =
  'Kamu adalah AI TELEGRAM, asisten AI ramah yang berjalan di dalam bot Telegram/WhatsApp ' +
  'milik Pall. Jawab dalam bahasa yang sama dengan pengguna (biasanya Bahasa Indonesia), ' +
  'singkat, jelas, dan to the point.';

async function gemini(messages) {
  const model = cfg.aiModel || 'gemini-2.0-flash';
  if (!cfg.aiKey) throw new Error('AI_KEY belum diisi di .env');
  const contents = [{ role: 'user', parts: [{ text: SYSTEM_PROMPT }] }];
  for (const m of messages) {
    contents.push({ role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] });
  }
  const url = cfg.aiProject
    ? `https://generativelanguage.googleapis.com/v1beta/projects/${cfg.aiProject}/models/${model}:generateContent`
    : `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'x-goog-api-key': cfg.aiKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents, generationConfig: { maxOutputTokens: 1024, temperature: 0.7 } }),
  });
  if (!r.ok) {
    let msg = r.text.slice(0, 200);
    try { msg = (await r.json()).error?.message || msg; } catch (_) {}
    throw new Error(`Gemini ${r.status}: ${msg}`);
  }
  const data = await r.json();
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
  if (!text) throw new Error('Respons Gemini kosong');
  return text;
}

async function openai(messages) {
  if (!cfg.aiKey) throw new Error('AI_KEY belum diisi di .env');
  const model = cfg.aiOpenAiModel || 'gpt-4o-mini';
  const payload = {
    model,
    max_tokens: 1024,
    messages: [{ role: 'system', content: SYSTEM_PROMPT }, ...messages],
  };
  const r = await fetch(`${cfg.aiBaseUrl.replace(/\/$/, '')}/chat/completions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${cfg.aiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`OpenAI ${r.status}: ${r.text.slice(0, 200)}`);
  const data = await r.json();
  const text = data?.choices?.[0]?.message?.content?.trim();
  if (!text) throw new Error('Respons OpenAI kosong');
  return text;
}

async function aiChat(messages) {
  if (cfg.aiProvider === 'gemini') return gemini(messages);
  return openai(messages);
}

module.exports = { aiChat };
