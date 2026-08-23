# 🤖 PallBot — Bot Telegram Multi Fungsi × Website

Bot Telegram **multi tombol** yang terhubung dengan **website** (dashboard + panel admin),
dirancang untuk berjalan di **VPS** (Ubuntu/Debian). Dibuat oleh **Pall**.

```
Bot Telegram (aiogram 3)      Website (FastAPI + Jinja2)
┌─────────────────────┐       ┌──────────────────────────┐
│ 🔍 Cek ID           │       │ Beranda, Cek ID, AI Chat │
│ 🤖 AI Chat         │◄─────►│ Panel Admin:             │
│ ➕ Buat Channel/Grup│  sama │  • Buat Channel/Grup    │
│ 📢 Tambah Bot      │  proses│  • Daftar Channel       │
│ ℹ️ Info            │       │  • Pengaturan (token/AI)│
│ ⚙️ Admin           │       │  • Statistik + Log      │
└─────────────────────┘       └──────────────────────────┘
        MTProto (Telethon): buat channel/grup + tunjuk owner, join invite
        SQLite: settings, owners, users, channels, AI history, logs
```

## ✨ Fitur

| Fitur | Di Bot | Di Website |
|---|---|---|
| Cek ID diri sendiri | ✅ `/id` atau menu | ✅ |
| Cek ID via username (user/channel/grup publik) | ✅ | ✅ |
| Cek ID channel/grup (ID numerik) | ✅ | ✅ |
| Cek ID channel/grup **privat** (forward pesan) | ✅ | — |
| Buat **channel** baru | ✅ | ✅ |
| Buat **grup** (super) baru | ✅ | ✅ |
| **Pilih owner** saat membuat (Pall utama / akun 2 / pacar, atau ID custom) | ✅ | ✅ |
| Tambah bot ke channel/grup (invite link → bot join otomatis) | ✅ | ✅ |
| **AI Chat** (AI TELEGRAM) | ✅ | ✅ |
| Statistik & log | ✅ (admin) | ✅ |
| Kelola daftar owner | ✅ (admin) | ✅ |
| Broadcast ke semua user | ✅ (admin) | — |
| Ubah token / API / AI config tanpa edit file | — | ✅ |

**Owner default (admin bot & pilihan owner):**

| ID | Label |
|---|---|
| `8861238621` | Pall (Akun Utama) |
| `8719750003` | Pall (Akun Kedua) |
| `8897520559` | Pacar Pall |

> 💡 **Catatan penting soal "owner":** membuat channel/grup + memindahkan
> ownership **sejati** (`channels.editCreator`) hanya bisa dilakukan oleh
> **akun user** (perlu login HP + password 2FA) — bot **tidak bisa** melakukannya.
> Jadi PallBot menggunakan cara standar bot reseller channel: bot membuat
> channel/grup (bot jadi creator), lalu owner pilihan ditunjuk sebagai
> **admin penuh dengan rank "Owner"** (semua hak: manage channel, tambah admin,
> post, dll). Ini sudah penuh kendali di channel tersebut.

##  Struktur

```
run.py               # entry point (uvicorn: website + bot + MTProto)
app/
  config.py          # config (.env + DB, prioritas DB > .env)
  db.py              # SQLite (aiosqlite)
  ai.py              # klien AI (Gemini / OpenAI-compatible)
  services.py        # logika inti: create channel/grup, owner, join, cek ID
  bot/bot.py         # bot aiogram: menu, FSM, admin, AI mode
  web/app.py         # FastAPI: halaman + REST API
  web/auth.py        # login admin (password + signed cookie)
  web/templates/     # halaman (tema gelap ala Telegram)
static/              # CSS/JS
deploy/
  vps_setup.sh       # one-click setup VPS
  nginx.conf.example # reverse proxy + HTTPS
data/                # SQLite + session (otomatis, jangan di-commit)
```

## 🚀 Deploy di VPS (1 perintah)

Butuh VPS Ubuntu 20.04+/Debian 11+ dengan `root`/`sudo`.

```bash
# 1. clone / salin folder ini ke VPS
git clone <repo> /root/telegram-website && cd /root/telegram-website

# 2. jalankan setup
sudo bash deploy/vps_setup.sh
```

Script akan: install python3+venv → copy app ke `/opt/pallbot` → install
dependencies → buat `.env` → install **systemd service `pallbot`** → start.

```
# cek status
systemctl status pallbot
journalctl -u pallbot -f        # live log
```

Website langsung bisa dibuka di `http://IP_VPS:8000`
(panel admin: `http://IP_VPS:8000/admin`, password default **`pall123`**).

### Isi kredensial (pilih salah satu)

**Opsi A — lewat website (paling gampang):**
buka `http://IP_VPS:8000/admin` → login `pall123` → **Pengaturan** → isi:
- `BOT_TOKEN` — dari [@BotFather](https://t.me/BotFather) → `/newbot`
- `API_ID` & `API_HASH` — dari [my.telegram.org](https://my.telegram.org)
  → *API Development Tools* (untuk fitur buat channel/grup)
- `BOT_USERNAME` — username bot (tanpa @)
- simpan → bot & MTProto otomatis restart.

**Opsi B — edit file:**
```bash
sudo nano /opt/pallbot/.env     # isi BOT_TOKEN, API_ID, API_HASH
sudo systemctl restart pallbot
```

### Nginx + HTTPS (opsional, recommended)

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/pallbot
sudo ln -s /etc/nginx/sites-available/pallbot /etc/nginx/sites-enabled/
# edit server_name jadi domain-mu, lalu:
sudo nginx -t && sudo systemctl reload nginx
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d DOMAIN_ANDA
```

## 🤖 Cara Pakai Bot

Kirim `/start` ke bot → muncul **menu tombol**:

1. **🔍 Cek ID**
   - *ID Saya* → ID + username kamu.
   - *Cek ID via Username* → ketik `@username` (user/channel/grup publik).
   - *Cek ID Channel/Grup* → ketik ID (mis. `-1001234567890`).
     Untuk channel/grup **privat**: forward 1 pesan dari sana ke bot.
2. **🤖 AI Chat** → ngobrol dengan AI (pakai API key yang kamu set).
   Tekan ⏹️ untuk keluar.
3. **➕ Buat Channel / ➕ Buat Grup**
   → kirim nama → kirim deskripsi (atau `/skip`) → **pilih owner**
   (tombol: Pall utama / Pall akun 2 / Pacar / input ID manual)
   → bot membuat + menunjuk owner → dapat link/ID.
4. **📢 Tambah Bot** → kirim invite link channel/grup, bot langsung join.
5. **ℹ️ Info** → tentang bot.
6. **⚙️ Admin** (hanya 3 owner) → statistik, tes AI, tambah/list owner,
   daftar channel, broadcast.

Komando: `/start` `/menu` `/help` `/id`

## 🤖 Konfigurasi AI

API key kamu (`AQ.…`) adalah **key AI Studio Google (format baru `AQ.`)**
untuk project **AI TELEGRAM** (`projects/216372639628`).
Default sudah di-set:

| Setting | Nilai |
|---|---|
| `AI_PROVIDER` | `gemini` |
| `AI_PROJECT` | `216372639628` |
| `AI_MODEL` | `gemini-2.0-flash` |
| `AI_KEY` | `AQ.Ab8RN6Ix-…` (dari kamu) |

> ⚠️ Catatan: key format `AQ.` kadang ditolak REST endpoint Gemini
> (`401 ACCESS_TOKEN_TYPE_UNSUPPORTED`) — masalah umum format key baru ini.
> Kalau tes AI gagal, di **Panel Admin → Pengaturan** kamu bisa:
> - ganti **model** (mis. `gemini-2.5-flash`, `gemini-flash-latest`), atau
> - bikin key `AIza…` baru dari [AI Studio](https://aistudio.google.com/apikey) /
>   [Google Cloud Credentials](https://console.cloud.google.com/apis/credentials)
>   (restrict ke Gemini API), atau
> - pindah ke provider **openai-compatible** (isi `AI_BASE_URL` + `AI_KEY` +
>   `AI_OPENAI_MODEL`; jalan juga untuk Groq/OpenRouter/local).
>
> Pakai tombol **🧪 Tes Koneksi AI** di Dashboard untuk verifikasi.

## 🔐 Keamanan

- Password admin default `pall123` — **ubah segera** di Pengaturan.
- Token/key hanya disimpan di `.env` / SQLite di server, **tidak pernah**
  dikirim ke browser (hanya status "terisi/kosong").
- Sesi admin = signed cookie (12 jam).
- `.env` di-`chmod 600` oleh script setup.

## 🛠️ Troubleshooting

| Masalah | Solusi |
|---|---|
| Bot 🔴 offline | Cek `BOT_TOKEN` di Pengaturan; cek log `journalctl -u pallbot -f` |
| MTProto 🔴 | Butuh `API_ID` + `API_HASH` + `BOT_TOKEN`; kalau `AUTH_KEY_UNREGISTERED`, hapus `data/pallbot_mtproto.session*` lalu restart |
| Buat channel gagal "You are not the owner" | Pastikan MTProto online (bot harus creator) |
| AI 401 `ACCESS_TOKEN_TYPE_UNSUPPORTED` | Lihat bagian Konfigurasi AI (ganti model/key/provider) |
| Port 8000 bentrok | Ubah `WEB_PORT` di `.env` (dan nginx `proxy_pass`) |
| Reset data | Hapus isi folder `data/` lalu restart (settings & daftar hilang) |

## 📄 Lisensi

Private — dibuat khusus untuk Pall.
