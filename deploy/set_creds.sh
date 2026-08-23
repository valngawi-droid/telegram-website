#!/usr/bin/env bash
# ============================================================
#  PallBot — Setup Credentials Interaktif
#  Jalankan:  bash deploy/set_creds.sh   (sebagai root)
#  Nanya satu-satu, isi .env, restart service, tampilkan status.
# ============================================================
set -e
ENV=/opt/pallbot/.env
DOMAIN="${DOMAIN:-web.pallrzki.my.id}"

if [ ! -f "$ENV" ]; then
  echo "⚠️  $ENV tidak ditemukan. Jalankan dulu: bash deploy/vps_setup.sh"
  exit 1
fi

# backup .env lama
cp "$ENV" "$ENV.bak.$(date +%Y%m%d_%H%M%S)"
echo "📦 Backup .env dibuat."

setval() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV" 2>/dev/null; then
    # escape karakter khusus sed (&, /, \)
    val_esc=$(printf '%s\n' "$val" | sed 's/[&/\]/\\&/g')
    sed -i "s|^${key}=.*|${key}=${val_esc}|" "$ENV"
  else
    echo "${key}=${val}" >> "$ENV"
  fi
  echo "   ✅ ${key} di-set"
}

echo
echo "═══ PALLBOT — SETUP CREDENTIALS ═══"
echo "(tekan Enter untuk skip field)"
echo

read -rp "🤖 BOT_TOKEN (token @BotFather): " TOKEN
[ -n "$TOKEN" ] && setval BOT_TOKEN "$TOKEN"

read -rp "🔑 API_ID (my.telegram.org): " APIID
[ -n "$APIID" ] && setval API_ID "$APIID"

read -rp "🔑 API_HASH (my.telegram.org): " APIHASH
[ -n "$APIHASH" ] && setval API_HASH "$APIHASH"

read -rp "📛 BOT_USERNAME (tanpa @, contoh: celzynokosbot): " BUN
[ -n "$BUN" ] && setval BOT_USERNAME "$BUN"

read -rp "🤖 AI_KEY (key AI, boleh kosong): " AKEY
[ -n "$AKEY" ] && setval AI_KEY "$AKEY"

read -rp "🔐 ADMIN_PASSWORD baru (kosong = tetap pall123): " APW
[ -n "$APW" ] && setval ADMIN_PASSWORD "$APW"

chmod 600 "$ENV"
echo
echo "🔄 Restart service pallbot..."
systemctl restart pallbot
sleep 6

echo
if systemctl is-active --quiet pallbot; then
  echo "✅ Service pallbot: JALAN"
else
  echo "❌ Service bermasalah — cek: journalctl -u pallbot -n 30"
fi
echo
echo "─── Log terbaru ───"
journalctl -u pallbot -n 15 --no-pager
echo
echo "════════════════════════════════════"
echo "  Cek status di browser:"
echo "  http://$DOMAIN/admin"
echo "  (Bot 🟢 + MTProto 🟢 = semua siap)"
echo "════════════════════════════════════"
