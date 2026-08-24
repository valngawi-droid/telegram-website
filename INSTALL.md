#  Install PallBot di VPS — Step by Step

Bot Telegram multi fungsi + website, jalan 24/7 di VPS Ubuntu/Debian.
Estimasi waktu: **15-25 menit** (tergantung bikin bot & credentials).

---

## STEP 0 — Persiapan

Kamu butuh:
- ✅ VPS **Ubuntu 20.04/22.04/24.04** atau **Debian 11+** (min 1GB RAM, 10GB disk)
- ✅ Bisa akses SSH (`ssh root@IP_VPS` atau `ssh user@IP_VPS`)
- ✅ 1 akun Telegram (punya 3: Pall utama, akun 2, pacar)

---

## STEP 1 — Ambil file proyek ke VPS

**Opsi A — lewat Git (recommended):**
```bash
ssh root@IP_VPS
apt update && apt install -y git
git clone URL_REPO_KAMU /root/telegram-website
cd /root/telegram-website
```

**Opsi B — upload manual (SFTP/SCP/FileZilla):**
- Upload seluruh isi folder proyek ke `/root/telegram-website` di VPS.

---

## STEP 2 — Install one-click

```bash
cd /root/telegram-website
sudo bash deploy/vps_setup.sh
```

Script otomatis melakukan:
1. Install `python3` + `python3-venv`
2. Copy aplikasi ke `/opt/pallbot`
3. Buat virtualenv + install semua dependensi
4. Buat file `.env`
5. Install **systemd service `pallbot`** (auto-restart kalau mati/reboot)
6. Start service

**Cek hasil:**
```bash
systemctl status pallbot          # harus "active (running)"
journalctl -u pallbot -f          # live log (Ctrl+C untuk keluar)
```

Website langsung live di: `http://IP_VPS:8000`

---

## STEP 3 — Buat bot di BotFather (kalau belum punya)

1. Buka Telegram → cari **@BotFather** → tekan Start
2. Kirim `/newbot`
3. Pilih **nama** bot (misal: `PallBot`)
4. Pilih **username** bot (harus diakhiri `bot`, misal: `pallbot_jagoan`)
5. **Salin TOKEN** yang diberikan, format: `123456789:AAH...xyz`

⚠️ Jaga token ini seperti password.

---

## STEP 4 — Ambil API ID & API Hash

1. Buka **https://my.telegram.org** → login dengan nomor Telegram-mu
   (nomor bisa nomor manapun dari 3 akun)
2. Klik **API development tools**
3. Isi form (App title: `PallBot`, short name: `pallbot`) → Submit
4. Catat:
   - `api_id` = angka (misal `123456`)
   - `api_hash` = kode hex (misal `0123456789abcdef0123456789abcdef`)

---

## STEP 5 — Isi credentials (pilih salah satu)

### Opsi A — lewat website (paling gampang, no SSH lagi):

1. Buka `http://IP_VPS:8000/admin`
2. Login password: **`pall123`**
3. Klik tab **Pengaturan**, isi:
   | Field | Isi |
   |---|---|
   | `BOT_TOKEN` | token dari @BotFather |
   | `API_ID` | angka dari my.telegram.org |
   | `API_HASH` | hex dari my.telegram.org |
   | `BOT_USERNAME` | username bot tanpa @ |
4. **💾 Simpan** → bot & MTProto **otomatis restart** (tunggu ~10 detik)
5. **SEGERA ubah password admin** di field "Password Admin Website"

### Opsi B — lewat file:
```bash
nano /opt/pallbot/.env
# isi:
#   BOT_TOKEN=123456789:AAH...
#   API_ID=123456
#   API_HASH=0123456789abcdef...
#   BOT_USERNAME=pallbot_jagoan
#   ADMIN_PASSWORD=ganti-password-kamu
sudo systemctl restart pallbot
```

---

## STEP 5b — Login Userbot (WAJIB untuk fitur Buat Channel/Grup)

> ⚠️ **Telegram melarang BOT membuat channel/grup.** Fitur create memakai
> **akun user** (userbot). Login **sekali saja** di VPS:

```bash
# 1. set nomor userbot di .env (salah satu akunmu):
nano /opt/pallbot/.env
#    USER_PHONE=628861238621     (tanpa +, tanpa 0 di depan 8)
#    USER_2FA=...                (password 2FA akun ini, kalau ada)

# 2. jalankan login:
cd /opt/pallbot
.venv/bin/python deploy/userbot_login.py
#    → masukin kode 5 digit dari Telegram
#    → (kalau ada) masukin password 2FA
#    → self-test: buat channel "Uji Userbot" lalu hapus
```

**Syarat transfer ownership (pilih owner selain akun userbot):**
- Akun userbot harus punya **2FA aktif** (Settings → Privacy → Two-Step)
- 2FA baru diubah / session baru login → **tunggu 24 jam** (aturan Telegram)
- Kalau syarat belum terpenuhi: owner tetap dapat **admin penuh rank "Owner"**

Setelah login, dashboard nampil **Userbot 🟢 Login**.

---

## STEP 6 — Verifikasi semuanya jalan

1. Buka `http://IP_VPS:8000/admin` → Dashboard:
   - 🤖 Bot: **🟢 Online**
   - 🛰️ MTProto: **🟢 Online**
2. Di Telegram, tambah bot-mu → kirim `/start` → semua tombol muncul ✅
3. Uji fitur cepat:
   - `/id` → muncul ID kamu
   - Menu 🔍 Cek ID → cek username `@telegram`
   - ➕ Buat Channel → nama `Uji1` → skip → pilih owner → 🎉 harus jadi
   - 🤖 AI Chat → kirim "Halo" (lihat STEP 7 kalau AI error)
4. **Tes Koneksi AI**: Dashboard → tombol 🧪
   - Kalau ❌ `401 ACCESS_TOKEN_TYPE_UNSUPPORTED` → di Pengaturan ganti
     **AI_MODEL** (coba `gemini-2.5-flash` / `gemini-flash-latest`) atau
     ganti **AI_KEY** (buat key baru di aistudio.google.com/apikey), atau
     pindah provider ke `openai-compatible`.

---

## STEP 7 — Nginx + domain + HTTPS (recommended)

```bash
# 1. install nginx
apt install -y nginx

# 2. copy config
cp /opt/pallbot/deploy/nginx.conf.example /etc/nginx/sites-available/pallbot
ln -s /etc/nginx/sites-available/pallbot /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default

# 3. set domain kamu (point DNS A record ke IP VPS dulu)
nano /etc/nginx/sites-available/pallbot
#   server_name DOMAIN_KAMU.com;

# 4. test + reload
nginx -t && systemctl reload nginx
```

Akses sekarang: `http://DOMAIN_KAMU.com`

**HTTPS (SSL gratis):**
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d DOMAIN_KAMU.com
# pilih redirect ke HTTPS
```
Sekarang: `https://DOMAIN_KAMU.com` 🔒 (auto-renew SSL otomatis)

> Kalau pakai nginx/HTTPS, jangan buka port 8000 ke publik (lebih aman).

---

## STEP 8 — Firewall (keamanan VPS)

```bash
ufw allow OpenSSH          # port 22 (SSH)
ufw allow 80/tcp           # HTTP
ufw allow 443/tcp          # HTTPS
# tanpa nginx, buka juga: ufw allow 8000/tcp
ufw enable
ufw status
```

---

## STEP 9 — Install sebagai aplikasi di HP (PWA)

Website sudah PWA — jadi aplikasi di HP tanpa Play Store:
- **Android (Chrome):** buka website → menu ⋮ → **Tambah ke layar utama / Install aplikasi**
- **iPhone (Safari):** tombol Share → **Tamb. ke Layar Utama**

Muncul ikon PallBot di home screen, fullscreen, bisa offline.
Mau **APK**? Paste URL website di **PWABuilder.com** → generate APK.

---

## 🔧 Perawatan harian (command cheat sheet)

```bash
systemctl status pallbot       # cek status
journalctl -u pallbot -f       # live log (Ctrl+C keluar)
sudo systemctl restart pallbot # restart
sudo systemctl stop pallbot    # stop

# UPDATE proyek (setelah git pull):
cd /root/telegram-website && git pull
sudo bash deploy/vps_setup.sh  # aman dijalankan ulang (idempoten)

# Reset total data (settings, daftar channel, history AI):
sudo systemctl stop pallbot
sudo rm -rf /opt/pallbot/data
sudo systemctl start pallbot
```

---

## 🆘 Troubleshooting

| Gejala | Solusi |
|---|---|
| `systemctl` bilang service failed | `journalctl -u pallbot -n 100` → biasanya typo `.env` / python belum install |
| Bot 🔴 offline | Token salah/expired. Cek token di @BotFather (`/token`), paste ulang di Pengaturan |
| MTProto 🔴, log `AUTH_KEY_UNREGISTERED` | API_ID/HASH berganti → `sudo rm /opt/pallbot/data/pallbot_mtproto.session*` → `systemctl restart pallbot` |
| MTProto 🔴, log `FLOOD_WAIT` | Terlalu banyak request → tunggu beberapa menit, retry |
| Buat channel: "Belum lengkap..." | API_ID / API_HASH / BOT_TOKEN belum lengkap di Pengaturan |
| AI 401 `ACCESS_TOKEN_TYPE_UNSUPPORTED` | Key `AQ.` baru kadang ditolak REST — ganti model/key/provider di Pengaturan, lalu Tes AI |
| Website tidak bisa dibuka dari luar | Firewall: `ufw allow 80,443` (atau 8000). Atau cek security group provider VPS (Cloudflare/Vultr/dll) |
| Lupa password admin | `sqlite3 /opt/pallbot/data/pallbot.db "DELETE FROM settings WHERE key='ADMIN_PASSWORD';"` → `systemctl restart pallbot` → kembali ke `pall123` |
| Port 8000 dipakai aplikasi lain | Ubah `WEB_PORT=8080` di `/opt/pallbot/.env` + `proxy_pass` di nginx → restart |

---

## ✅ Checklist sebelum pakai

- [ ] `systemctl status pallbot` = active
- [ ] Dashboard: Bot 🟢 + MTProto 🟢
- [ ] Tes AI 🧪 = ✅
- [ ] Bot `/start` muncul tombol menu
- [ ] Create channel uji berhasil + owner terpilih jadi admin "Owner"
- [ ] Password admin sudah diganti
- [ ] Nginx + HTTPS + firewall aktif
- [ ] Install PWA di HP

🎉 Selesai — bot siap dipakai!
