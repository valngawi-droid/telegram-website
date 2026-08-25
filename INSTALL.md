#  Install PallBot di VPS — Step by Step (Bot Telegram + WhatsApp)

Estimasi: **30-45 menit** (termasuk scan QR WhatsApp).

## STEP 0 — Persiapan
- VPS Ubuntu 20.04+/Debian 11+ (min 1GB RAM, 20GB disk)
- Akses SSH
- Bot Telegram: **@celzynokosbot** (sudah dibuat) + token
- **Nomor WA cadangan** (SIM/eSIM) untuk bot WhatsApp

## STEP 1 — Ambil kode
```bash
ssh root@IP_VPS
apt update && apt install -y git
git clone -b arena/01a02ea5-telegram-website https://github.com/valngawi-droid/telegram-website.git /root/telegram-website
cd /root/telegram-website
```

## STEP 2 — Install bot Telegram (1 command)
```bash
sudo bash deploy/vps_setup.sh
```
→ python + venv + dependensi + systemd `pallbot` + start.

## STEP 3 — Isi credentials (1 command, interaktif)
```bash
bash deploy/set_creds.sh
```
Nanya satu-satu (Enter = skip): BOT_TOKEN, API_ID, API_HASH, BOT_USERNAME,
AI_KEY, ADMIN_PASSWORD, USER_PHONE, USER_2FA.

*(Atau manual: `nano /opt/pallbot/.env` — lihat `.env.example`)*

## STEP 4 — Login Userbot (WAJIB untuk Buat Channel)
> Telegram melarang bot membuat channel — create memakai akun user (sekali login).

```bash
cd /opt/pallbot
.venv/bin/python deploy/userbot_login.py
```
→ masukkan kode 5 digit dari Telegram → (kalau ada) password 2FA →
self-test otomatis (buat + hapus channel "Uji Userbot").

⚠️ Untuk **transfer ownership** (pilih owner selain akun userbot):
akun userbot harus **2FA aktif** + **24 jam** sejak 2FA diubah/login.
Sebelum itu, owner tetap dapat **admin penuh rank "Owner"**.

## STEP 5 — Install bot WhatsApp
1. Isi nomor-nomor WA di `.env`:
```bash
nano /opt/pallbot/.env
#   WA_OWNER_CHAT=62886...        ← nomor WA tujuan "Chat dengan Owner"
#   WA_OWNERS=62886...:Pall Utama|62887...:Pall 2|62889...:Pacar
```
2. Install:
```bash
sudo bash deploy/wa_setup.sh
```
→ install Node 20 + chromium + `npm install` + systemd `pallbot-wa` + start.

3. **Scan QR** (sekali saja):
```bash
journalctl -u pallbot-wa -f        # QR muncul di terminal
# atau: cat /opt/pallbot/wa/qr.png (di VPS) — lebih gampang: jalankan manual
cd /opt/pallbot/wa && node index.js
```
Di HP (nomor WA cadangan): **WhatsApp → Setelan → Perangkat tertaut →
Tautkan perangkat** → scan QR. Session tersimpan permanen di `wa/wwebjs_auth/`.

## STEP 6 — Tes semua
- **Telegram:** kirim `/start` ke @celzynokosbot → menu tombol
  → uji Cek ID, Buat Channel (owner pilihan), AI Chat
- **WhatsApp:** chat nomor bot → ketik `menu` → uji AI, Buat Grup, Chat Owner
- `systemctl status pallbot pallbot-wa` → keduanya `active`

##  Matikan / Hentikan

| Tujuan | Perintah |
|---|---|
| Stop bot Telegram (bisa nyala lagi) | `systemctl stop pallbot` |
| Stop bot WA (bisa nyala lagi) | `systemctl stop pallbot-wa` |
| Stop semua + jangan auto-start saat reboot | `systemctl disable --now pallbot pallbot-wa` |
| Bot Telegram OFFLINE permanen | @BotFather → /mybots → API Token → **Revoke** |
| Hapus bot Telegram total | @BotFather → /mybots → **Delete bot** |
| Bot WA "ganti nomor" / reset | `systemctl stop pallbot-wa && rm -rf /opt/pallbot/wa/wwebjs_auth && systemctl start pallbot-wa` → scan QR lagi |

##  Firewall (satu kali)
```bash
ufw allow OpenSSH && ufw allow 22 && ufw enable
```
(Bot memakai koneksi **keluar** ke Telegram/WhatsApp — tidak perlu buka port masuk.)

##  Update (nanti)
```bash
cd /root/telegram-website && git pull
sudo bash deploy/vps_setup.sh    # sync kode python ke /opt/pallbot
sudo bash deploy/wa_setup.sh     # sync kode wa + npm install
```
