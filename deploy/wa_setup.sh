#!/usr/bin/env bash
# ============================================================
#  PallBot WA — Install bot WhatsApp di VPS (Ubuntu/Debian)
#  Jalankan:  sudo bash deploy/wa_setup.sh
#  Butuh: node 20+ (auto-install), nomor WA cadangan untuk scan QR
# ============================================================
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="/opt/pallbot"
RUN_USER="${SUDO_USER:-root}"
[ "$RUN_USER" = "root" ] && RUN_USER="pallbot"

echo "==> PallBot WA Setup"

# ---------- 1. Node.js 20 ----------
if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]; then
  echo "==> Install Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
echo "    node $(node -v) / npm $(npm -v)"

# ---------- 2. dependensi chromium (untuk whatsapp-web.js) ----------
echo "==> Install dependensi chromium..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libasound2t64 libasound2 libpango-1.0-0 libcairo2 2>/dev/null || \
apt-get install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libasound2 libpango-1.0-0 libcairo2

# ---------- 3. sync kode ----------
echo "==> Sync kode ke $DEST_DIR ..."
mkdir -p "$DEST_DIR"
rsync -a --exclude '.git' --exclude '.venv' --exclude 'data' --exclude 'node_modules' \
      --exclude '__pycache__' --exclude 'wa/wwebjs_auth' --exclude 'wa/qr.png' \
      "$SRC_DIR"/ "$DEST_DIR"/ 2>/dev/null || cp -r "$SRC_DIR"/. "$DEST_DIR"/

# ---------- 4. npm install ----------
echo "==> npm install (whatsapp-web.js + chromium download, bisa 2-5 menit)..."
cd "$DEST_DIR/wa"
npm install --no-audit --no-fund

# ---------- 5. ownership ----------
chown -R "$RUN_USER":"$RUN_USER" "$DEST_DIR"
[ -f "$DEST_DIR/.env" ] && chmod 600 "$DEST_DIR/.env"

# ---------- 6. systemd ----------
echo "==> Install systemd service pallbot-wa..."
cat > /etc/systemd/system/pallbot-wa.service <<EOF
[Unit]
Description=PallBot WA - Bot WhatsApp
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$DEST_DIR/wa
Environment=HOME=$DEST_DIR
ExecStart=/usr/bin/node index.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pallbot-wa
systemctl restart pallbot-wa
sleep 5

echo
echo "============================================================"
if systemctl is-active --quiet pallbot-wa; then
  echo "  ✅ Service pallbot-wa JALAN"
else
  echo "  ⚠️  Cek: journalctl -u pallbot-wa -n 50"
fi
echo
echo "  LANGKAH SELANJUTNYA — SCAN QR (sekali saja):"
echo "  1) cat $DEST_DIR/wa/qr.png   (atau: journalctl -u pallbot-wa -f)"
echo "     → QR muncul di terminal"
echo "  2) Di HP dengan nomor WA CADANGAN:"
echo "     WhatsApp → Setelan → Perangkat tertaut → Tautkan perangkat"
echo "  3) Scan QR-nya. Selesai — session tersimpan permanen."
echo
echo "  Cek status : systemctl status pallbot-wa"
echo "  Live log   : journalctl -u pallbot-wa -f"
echo "  Login ulang: systemctl stop pallbot-wa && cd $DEST_DIR/wa"
echo "               && sudo -u $RUN_USER rm -rf wwebjs_auth && systemctl start pallbot-wa"
echo "============================================================"
