# 🤖 PallBot — Bot Telegram + WhatsApp Multi Fungsi

Bot multi fungsi untuk **Telegram & WhatsApp**, jalan 24/7 di VPS.
Dibuat oleh **Pall**. (v5: website dihapus — semua fitur via bot.)

```
┌────────────────────────────┐      ┌────────────────────────────┐
│  BOT TELEGRAM (Python)     │      │  BOT WHATSAPP (Node.js)    │
│  aiogram + telethon        │      │  whatsapp-web.js (QR)      │
│  @celzynokosbot            │      │  nomor WA cadangan         │
├────────────────────────────┤      ├────────────────────────────┤
│ Cek ID (diri/username/     │      │ Cek ID (nomor WA)          │
│ channel/grup/forward)      │      │ AI Chat                    │
│ AI Chat + /ai <teks>       │      │ Buat Grup + pilih owner    │
│ Buat Channel/Grup (userbot │      │ Chat dengan Owner          │
│  + transfer owner)         │      │ Pengingat, Broadcast       │
│ Tambah bot (invite)        │      │ Welcome grup, kick/promote │
│ Moderasi /kick /ban /mute  │      │ Waktu WIB                  │
│ Welcome, Pengingat         │      │                            │
│ Chat dengan Owner          │      │                            │
│ Admin: statistik, owner,   │      │                            │
│ member+limit, edit channel,│      │                            │
│ broadcast, tes AI          │      │                            │
└────────────────────────────┘      └────────────────────────────┘
        SQLite (data/) • .env (config) • userbot session (data/)
```

##  Fitur

**Telegram** (`@celzynokosbot` → `/start`):
- 🔍 Cek ID: diri sendiri, via username, ID channel/grup, forward pesan (channel privat)
- 🤖 AI Chat (mode) + `/ai <teks>` (quick)
- ➕ Buat Channel/Grup via **userbot** + **pilih owner** (lihat bawah)
- 📢 Tambah bot ke channel/grup (invite link) + `/ceklink`
- 👢 Moderasi: `/kick` `/ban` `/unban` `/mute` `/unmute`
- 👋 `/setwelcome {nama}` — sapa member baru
- ⏰ `/ingat 30m pesan` + `/daftaringat` + `/hapusingat 1`
- 💬 Chat dengan Owner (relay dua arah)
- ⚙️ Admin (3 owner): statistik, tes AI, edit channel (nama/deskripsi/username/invite/hapus),
  detail member, tambah owner, **tambah member + limit create**, broadcast, `/bcchannel`
- `/waktu` `/random` `/ping`

**WhatsApp** (nomor bot = nomor cadangan kamu, scan QR sekali):
- 1️⃣ Cek ID (nomor WA) • 2️⃣ AI Chat • 3️⃣ **Buat Grup + pilih owner**
- 4️⃣ Chat dengan Owner • 5️⃣ Pengingat • 6️⃣ Waktu WIB • 7️⃣ Bantuan
- Admin (nomor di `WA_OWNERS`): 8️⃣ Broadcast • 9️⃣ Daftar user • 🔟 `welcome set ...`
- Moderasi grup: `kick @sebut` / `promote @sebut` / `demote @sebut`

> Catatan WA: WhatsApp tidak punya "transfer owner grup" — bot (pembuat) jadi owner
> teknis, dan owner pilihan **dipromosikan jadi admin** (kontrol penuh). Bot bisa di-kick.

##  Sistem Izin Create (Telegram)

Create channel/grup **khusus**:
- 👑 **Owner & pacar** — `8861238621`, `8719750003`, `8897520559` → unlimited + kelola
- 👥 **Member whitelist** (ditambah owner via menu bot / dulu via website) → sampai limit
  (`CREATE_LIMIT`, default 10; per member bisa beda)
- 🚫 **User lain** → ditolak, diarahkan ke "Chat dengan Owner"

##  Kenapa Create Pakai Userbot?

**Telegram melarang bot membuat channel/grup** (`CreateChannelRequest` ditolak server).
Solusi: **userbot** = akun user yang di-login **sekali**:

```bash
cd /opt/pallbot && .venv/bin/python deploy/userbot_login.py
```

Alur: userbot buat channel (jadi creator) → **transfer ownership sejati** ke owner
pilihan via `channels.editCreator` (butuh **2FA aktif** di akun userbot +
session berumur > 24 jam) → kalau belum bisa, owner jadi **admin penuh rank "Owner"**.
Bot juga otomatis jadi admin channel (kelola + broadcast).

##  Struktur

```
run.py               # entry: bot Telegram + userbot + loop (tanpa website)
app/
  config.py          # config dari .env
  db.py              # SQLite: settings, owners, creators, users, channels, reminders, welcome
  ai.py              # AI: Gemini (project 216372639628) / OpenAI-compatible
  services.py        # create/edit/detail/invite/delete/ceklink (userbot-first, bot-fallback)
  userbot.py         # userbot: login session, create_with_user, editCreator (raw 0x8f38cd1f)
  bot/bot.py         # bot aiogram: semua menu + FSM + admin
  runner.py          # loop: sync .env, reminder
wa/
  index.js           # bot WhatsApp (whatsapp-web.js): menu, AI, buat grup, dll
  config.js / ai.js / db.js
deploy/
  vps_setup.sh       # install utama (python + systemd pallbot)
  wa_setup.sh        # install bot WA (node + chromium + systemd pallbot-wa)
  userbot_login.py   # login userbot sekali jalan
  set_creds.sh       # setup .env interaktif
data/                # SQLite + session (gitignored)
```

##  Konfigurasi (.env)

| Key | Fungsi |
|---|---|
| `BOT_TOKEN` | token @BotFather |
| `API_ID` / `API_HASH` | my.telegram.org (MTProto) |
| `USER_PHONE` / `USER_2FA` | akun userbot (create channel) |
| `AI_PROVIDER` / `AI_PROJECT` / `AI_MODEL` / `AI_KEY` | AI (Gemini default) |
| `CREATE_LIMIT` / `OWNER_CHAT_ID` | limit member, tujuan chat owner |
| `WA_OWNER_CHAT` / `WA_OWNERS` | bot WhatsApp: tujuan chat owner + daftar owner/admin |

**JANGAN commit `.env` berisi key asli.** `.env.example` hanya template.

##  Perintah VPS

```bash
systemctl status pallbot          # bot Telegram
systemctl status pallbot-wa       # bot WhatsApp
journalctl -u pallbot -f          # log
journalctl -u pallbot-wa -f       # log WA (QR muncul di sini)
sudo bash deploy/vps_setup.sh     # (re)install bot Telegram — aman dijalankan ulang
sudo bash deploy/wa_setup.sh      # (re)install bot WhatsApp
```

##  Troubleshooting

| Gejala | Solusi |
|---|---|
| Bot offline | cek `BOT_TOKEN`; `journalctl -u pallbot -n 50` |
| MTProto AUTH_KEY_UNREGISTERED | `rm /opt/pallbot/data/pallbot_mtproto.session*` + restart |
| Create: "cannot be executed as a bot" | userbot belum login → `python deploy/userbot_login.py` |
| Transfer ownership: PASSWORD_MISSING | aktifkan 2FA di akun userbot, tunggu 24 jam |
| Transfer ownership: SESSION_TOO_FRESH | session baru login → tunggu 24 jam (owner tetap dapat admin penuh) |
| WA: QR tidak muncul | `journalctl -u pallbot-wa -n 100`; pastikan node + dependensi chromium terpasang |
| WA: disconnect terus | `rm -rf /opt/pallbot/wa/wwebjs_auth` lalu restart (scan QR lagi) |
| AI 401 ACCESS_TOKEN_TYPE_UNSUPPORTED | ganti `AI_MODEL`/`AI_KEY`/`AI_PROVIDER` di .env, restart |
| Lupa mau hapus data | `rm -rf /opt/pallbot/data` (settings, owner list, history — semua reset) |
