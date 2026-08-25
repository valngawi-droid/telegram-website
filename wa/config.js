// Konfigurasi — membaca .env di root proyek (sama dengan bot Telegram)
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const env = (k, d = '') => (process.env[k] || d).trim();

// Parse "62886...:Pall Utama|62887...:Pall 2|62889...:Pacar"
const waOwners = env('WA_OWNERS', '')
  .split('|')
  .map((s) => {
    const [num, label] = s.split(':').map((x) => (x || '').trim());
    return num ? { num, label: label || num } : null;
  })
  .filter(Boolean);

module.exports = {
  // AI (sama dengan bot Telegram)
  aiProvider: env('AI_PROVIDER', 'gemini'),
  aiProject: env('AI_PROJECT', '216372639628'),
  aiModel: env('AI_MODEL', 'gemini-2.0-flash'),
  aiKey: env('AI_KEY', ''),
  aiBaseUrl: env('AI_BASE_URL', 'https://api.openai.com/v1'),
  aiOpenAiModel: env('AI_OPENAI_MODEL', 'gpt-4o-mini'),

  // WhatsApp
  waOwnerChat: env('WA_OWNER_CHAT', ''), // nomor WA tujuan "Chat dengan Owner"
  waOwners,                              // daftar owner (buat grup + akses admin)
};
