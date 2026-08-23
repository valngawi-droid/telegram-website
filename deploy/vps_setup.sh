#!/usr/bin/env bash
# ============================================================
#  PallBot — One-Click VPS Setup (Ubuntu/Debian)
#  Jalankan:  bash deploy/vps_setup.sh
#  (butuh sudo/root, atau sudo bash deploy/vps_setup.sh)
# ============================================================
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="/opt/pallbot"
SERVICE_NAME="pallbot"

# user yang menjalankan service (user yang memanggil sudo, atau root)
RUN_USER="${SUDO_USER:-root}"
if [ "$RUN_USER" = "root" ]; then RUN_USER="pallbot"; fi

echo "==> PallBot VPS Setup"
echo "    Source : $SRC_DIR"
echo "    Target : $DEST_DIR"
echo "    User   : $RUN_USER"

# ---------- 1. dependencies ----------
if command -v apt-get >/dev/null; then
  echo "==> Update apt & install python3 + venv..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git
else
  echo "!! Hanya mendukung Ubuntu/Debian (apt). Lanjut manual untuk distro lain."
fi

# ---------- 2. user service ----------
if [ "$RUN_USER" != "root" ] && ! id "$RUN_USER" >/dev/null 2>&1; then
  useradd -m "$RUN_USER"
fi

# ---------- 3. copy app ----------
echo "==> Salin aplikasi ke $DEST_DIR ..."
mkdir -p "$DEST_DIR"
rsync -a --exclude '.git' --exclude '.venv' --exclude 'data' \
      --exclude '__pycache__' --exclude 'node_modules' \
      "$SRC_DIR"/ "$DEST_DIR"/ 2>/dev/null || \
cp -r "$SRC_DIR"/. "$DEST_DIR"/
rm -rf "$DEST_DIR/.git" "$DEST_DIR/.venv"

cd "$DEST_DIR"

# ---------- 4. venv + deps ----------
echo "==> Buat virtualenv & install dependencies..."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# ---------- 5. .env ----------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> .env dibuat dari .env.example — ISI BOT_TOKEN / API_ID / API_HASH!"
  echo "    (atau isi lewat Panel Admin -> Pengaturan di website)"
fi

# ---------- 6. data dir & ownership ----------
mkdir -p data
chown -R "$RUN_USER":"$RUN_USER" "$DEST_DIR"
chmod 600 "$DEST_DIR/.env" 2>/dev/null || true

# ---------- 7. systemd ----------
echo "==> Install systemd service..."
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=PallBot - Bot Telegram Multi Fungsi + Website
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$DEST_DIR
EnvironmentFile=-$DEST_DIR/.env
ExecStart=$DEST_DIR/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
sleep 3

# ---------- 8. status ----------
echo
echo "============================================================"
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "  ✅ PallBot JALAN! (status: $(systemctl is-active $SERVICE_NAME))"
else
  echo "  ⚠️  Service belum aktif — cek:  journalctl -u $SERVICE_NAME -n 50"
fi
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "  Website      : http://${IP:-SERVER_IP}:8000"
echo "  Panel Admin  : http://${IP:-SERVER_IP}:8000/admin  (password: pall123)"
echo "  Log          : journalctl -u $SERVICE_NAME -f"
echo
echo "  LANGKAH SELANJUTNYA:"
echo "  1) Isi token bot:  nano $DEST_DIR/.env   (BOT_TOKEN dari @BotFather,"
echo "     API_ID & API_HASH dari https://my.telegram.org)"
echo "     ATAU langsung lewat Panel Admin -> Pengaturan di website."
echo "  2) Tes AI:         Panel Admin -> Dashboard -> 'Tes Koneksi AI'"
echo "  3) (Opsional) Nginx + HTTPS:  cp deploy/nginx.conf.example /etc/nginx/sites-available/pallbot"
echo "     lalu sesuaikan domain & jalankan: nginx -t && systemctl reload nginx"
echo "     HTTPS: certbot --nginx -d DOMAIN_ANDA"
echo "============================================================"
