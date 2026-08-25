// ============================================================
//  PALLBOT — Bot WhatsApp (mirror fitur bot Telegram)
//  Jalankan: node index.js   (login QR pertama kali, setelahnya otomatis)
// ============================================================
const path = require('path');
const fs = require('fs');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const cfg = require('./config');
const db = require('./db');
const { aiChat } = require('./ai');

// ---------------- util ----------------
const jidOf = (num) => `${String(num).replace(/\D/g, '')}@s.whatsapp.net`;
const numOf = (jid) => (jid || '').split('@')[0];
const now = () => Date.now() / 1000;
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function chunk(text, n = 4000) {
  const out = [];
  while (text.length > n) {
    let cut = text.lastIndexOf('\n', n);
    if (cut < n / 2) cut = n;
    out.push(text.slice(0, cut));
    text = text.slice(cut).trimStart();
  }
  if (text) out.push(text);
  return out.length ? out : ['…'];
}

function parseDur(arg) {
  const m = /^\s*(\d+)\s*(m|menit|min|h|jam|d|hari)\b/i.exec(arg || '');
  if (!m) return null;
  const n = parseInt(m[1], 10);
  const u = m[2].toLowerCase();
  if (u.startsWith('m')) return { secs: n * 60, label: `${n} menit` };
  if (u.startsWith('h') || u.startsWith('j')) return { secs: n * 3600, label: `${n} jam` };
  return { secs: n * 86400, label: `${n} hari` };
}

// ---------------- state ----------------
const states = new Map(); // jid -> {mode, data}
const aiRate = new Map(); // jid -> [timestamps]
const AI_RATE = 30, AI_WINDOW = 600;
function aiOk(jid) {
  const t = now();
  const ts = (aiRate.get(jid) || []).filter((x) => t - x < AI_WINDOW);
  if (ts.length >= AI_RATE) return false;
  ts.push(t);
  aiRate.set(jid, ts);
  return true;
}

function isAdminNum(num) {
  const n = String(num).replace(/\D/g, '');
  if (cfg.waOwnerChat && n === String(cfg.waOwnerChat).replace(/\D/g, '')) return true;
  return cfg.waOwners.some((o) => n === o.num.replace(/\D/g, ''));
}

// ---------------- teks menu ----------------
function menuText(name, admin) {
  let t = `🤖 *PALLBOT — WhatsApp*\nBot multi fungsi milik *Pall*\n\nHai ${name || 'kamu'}! Pilih menu:\n\n`;
  t += `1️⃣ Cek ID\n2️⃣ AI Chat\n3️⃣ Buat Grup\n4️⃣ Chat dengan Owner\n5️⃣ Pengingat\n6️⃣ Waktu (WIB)\n7️⃣ Bantuan`;
  if (admin) t += `\n\n⚙️ _Menu Admin_\n8️⃣ Broadcast\n9️⃣ Daftar User\n🔟 Welcome Grup: _welcome set pesan_ / _welcome off_`;
  t += `\n\n_Ketik nomor untuk memilih._`;
  return t;
}

function helpText() {
  return `📖 *Panduan PallBot (WA)*

• *Cek ID* — lihat nomor WA kamu
• *AI Chat* — ngobrol dengan AI (ketik _stop_ untuk keluar)
• *Buat Grup* — bot membuatkan grup, owner pilih dari daftar
• *Chat Owner* — pesan diteruskan ke owner (Pall)
• *Pengingat* — contoh: _ingat 30m beli makan_
• *Waktu* — waktu Indonesia (WIB)

_Admin (owner):_
• _broadcast pesan..._ — kirim ke semua user
• _welcome set pesan_ / _welcome off_ — sapa member baru (di grup)
• _kick @sebut_ / _promote @sebut_ / _demote @sebut_ (di grup)`;
}

// ---------------- client ----------------
const forceLogin = process.argv.includes('--login');
const client = new Client({
  authStrategy: new LocalAuth({ clientId: 'pallbot', dataPath: path.join(__dirname, 'wwebjs_auth') }),
  puppeteer: {
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  },
});

client.on('qr', async (qr) => {
  console.log('\n==============================================');
  console.log('  SCAN QR INI dengan nomor WA BOT (cadangan)');
  console.log('  Telegram-style: WA → Setel → Perangkat Tertaut');
  console.log('==============================================\n');
  console.log(qr);
  try {
    await qrcode.toFile(path.join(__dirname, 'qr.png'), qr);
    console.log('\n(QR juga tersimpan di wa/qr.png)');
  } catch (_) {}
});

client.on('ready', () => {
  console.log('✅ PALLBOT WA siap & online!');
});

client.on('disconnected', (reason) => {
  console.error('❌ Koneksi WA putus:', reason);
  if (String(reason).toUpperCase() === 'LOGGED_OUT') {
    console.log('Session dihapus — jalankan lagi untuk scan QR baru.');
    fs.rmSync(path.join(__dirname, 'wwebjs_auth'), { recursive: true, force: true });
  }
});

// ---------------- fitur ----------------
async function doCekId(msg, jid) {
  db.touchUser(jid, msg.pushname);
  const u = db.getUsers().find((x) => x.jid === jid);
  const pertama = u && u.created_at && now() - u.created_at < 60;
  let t = `🪪 *Cek ID (WhatsApp)*\n\n`;
  t += `Nomor: ${numOf(jid)}\n`;
  t += `Nama (pushname): ${msg.pushname || '-'}\n`;
  t += `JID: \`${jid}\``;
  if (pertama) t += `\n\n👋 Senang kenalan! Ketik *menu* untuk lihat fitur.`;
  msg.reply(t);
}

async function doAiToggle(msg, jid) {
  if (states.get(jid)?.mode === 'aichat') {
    states.delete(jid);
    db.clearHistory(jid);
    msg.reply('⏹️ AI Chat dimatikan & riwayat dihapus.');
    return;
  }
  states.set(jid, { mode: 'aichat' });
  msg.reply('🤖 *AI Chat aktif*\nKirim pesanmu, AI akan menjawab.\nKetik *stop* untuk keluar.');
}

async function doAiText(msg, jid, text) {
  if (!aiOk(jid)) {
    msg.reply('🚦 Terlalu banyak pesan. Tunggu beberapa menit.');
    return;
  }
  await msg.reply('⏳ AI sedang berpikir...');
  const history = db.getHistory(jid, 10).map((m) => ({ role: m.role, content: m.content }));
  history.push({ role: 'user', content: text });
  db.addMsg(jid, 'user', text);
  let reply;
  try {
    reply = await aiChat(history);
  } catch (e) {
    reply = `❌ *AI error*: ${e.message || e}\n\nPeriksa AI_KEY / AI_PROVIDER di .env (VPS).`;
  }
  if (!String(reply).startsWith('❌')) db.addMsg(jid, 'assistant', reply);
  for (const part of chunk(reply)) await msg.reply(part);
}

async function doBuatGrupStart(msg, jid) {
  states.set(jid, { mode: 'buatgrup_nama' });
  msg.reply('➕ *Buat Grup*\n\nKirim *nama grup* baru:');
}

async function doBuatGrupNama(msg, jid, text) {
  const name = text.trim();
  if (name.length < 2) {
    msg.reply('Nama terlalu pendek. Kirim nama grup (min. 2 huruf) atau *batal*.');
    return;
  }
  let list = `0️⃣ Saya sendiri (${numOf(jid)})`;
  cfg.waOwners.forEach((o, i) => {
    list += `\n${i + 1}️⃣ ${o.label} (${o.num})`;
  });
  states.set(jid, { mode: 'buatgrup_owner', name });
  msg.reply(`✔️ Nama: *${name}*\n\n👑 Pilih *owner* grup:\n\n${list}\n\n_Ketik nomor pilihan_ (tanpa emoji).`);
}

async function doBuatGrupOwner(msg, jid, text) {
  const st = states.get(jid);
  states.delete(jid);
  if (!st) return msg.reply('Sesi habis. Ketik *menu*.');
  const pick = text.trim().replace(/\D/g, '');
  let ownerNum = numOf(jid);
  let ownerLabel = 'kamu';
  if (pick !== '0' && cfg.waOwners[parseInt(pick, 10) - 1]) {
    const o = cfg.waOwners[parseInt(pick, 10) - 1];
    ownerNum = o.num;
    ownerLabel = o.label;
  } else if (pick !== '0') {
    return msg.reply('Pilihan tidak valid. Ketik *menu* untuk ulang.');
  }
  const status = await msg.reply('⏳ Membuat grup...');
  try {
    const participants = ownerNum === numOf(jid) ? [jid] : [jidOf(ownerNum)];
    const group = await client.createGroup(st.name, participants);
    let note = 'Owner: kamu (pembuat).';
    if (ownerNum !== numOf(jid)) {
      try {
        await client.promoteParticipants(group.id, [jidOf(ownerNum)]);
        note = `✅ ${ownerLabel} dipromosikan jadi *admin grup* (WA tidak punya "transfer owner" — admin = kontrol penuh).`;
      } catch (e) {
        note = `⚠️ ${ownerLabel} belum bisa dipromosi (mungkin belum join). Tambahkan manual sebagai admin.`;
      }
    }
    const info = await group.info();
    let t = `🎉 *Grup berhasil dibuat!*\n\n📛 Nama: ${info.subject}\n🆔 ID: \`${group.id}\`\n👑 ${note}\n\nBot (pembuat) otomatis jadi owner teknis. Silakan di-kick kalau tidak perlu.`;
    await status.reply(t);
  } catch (e) {
    await status.reply(`❌ Gagal membuat grup: ${e.message || e}`);
  }
}

async function doChatOwner(msg, jid, text) {
  if (!cfg.waOwnerChat) {
    msg.reply('❌ Tujuan chat owner belum di-set (WA_OWNER_CHAT di .env).');
    return;
  }
  const name = msg.pushname || numOf(jid);
  const payload = `💬 *Pesan dari ${name}*\n📱 Nomor: ${numOf(jid)}\n\n${text}\n\n_Balas nomor ini untuk membalas user._`;
  try {
    await client.sendMessage(jidOf(cfg.waOwnerChat), { text: payload });
    msg.reply('✅ Pesanmu sudah diteruskan ke owner. Balasan owner akan dikirim ke nomor ini.');
  } catch (e) {
    msg.reply(`❌ Gagal meneruskan ke owner: ${e.message || e}`);
  }
}

function doIngat(msg, jid, text) {
  const parts = text.trim().split(/\s+/);
  if (parts.length < 2) {
    return msg.reply('⏰ Pakai: _ingat 30m beli makan_\nDurasi: _m_enit, _h_ jam, _d_ hari. Contoh: _ingat 2h_, _ingat 1d_');
  }
  const dur = parseDur(parts[1]);
  if (!dur) return msg.reply('Durasi tidak valid. Contoh: _ingat 30m pesan_');
  const body = parts.slice(2).join(' ');
  if (!body) return msg.reply('Tulis juga isi pengingatnya. Contoh: _ingat 5m ambil paket_');
  db.addReminder(jid, now() + dur.secs, body);
  msg.reply(`⏰ Oke! Aku akan ingatkanmu *${dur.label}* lagi:\n\n${body}`);
}

async function doBroadcast(msg, jid, text) {
  const body = text.replace(/^broadcast\s+/i, '').trim();
  if (!body) return msg.reply('Pakai: _broadcast pesan kamu_');
  const users = db.getUsers();
  let ok = 0, fail = 0;
  for (const u of users) {
    try {
      await client.sendMessage(u.jid, { text: `📢 *Broadcast PallBot*\n\n${body}` });
      ok++;
    } catch (_) { fail++; }
  }
  msg.reply(`📢 Broadcast selesai: ✅ ${ok} terkirim, ❌ ${fail} gagal (offline/blokir).`);
}

async function doUsersList(msg, jid) {
  const users = db.getUsers().slice(0, 20);
  if (!users.length) return msg.reply('Belum ada user terdaftar.');
  let t = '👥 *User terdaftar* (WA)\n\n';
  users.forEach((u, i) => {
    t += `${i + 1}. ${u.name || '-'} — \`${numOf(u.jid)}\`\n`;
  });
  msg.reply(t);
}

async function doWelcomeSet(msg, jid, text) {
  const m = /^welcome\s+set\s+([\s\S]+)/i.exec(text);
  if (!m) return msg.reply('Pakai (di grup): _welcome set Selamat datang!_ atau _welcome off_');
  db.setWelcome(msg.from, m[1].trim());
  msg.reply('✅ Welcome message di-set untuk grup ini.');
}

async function handleGroupMod(msg, jid, text) {
  const cmd = /^\/?(kick|promote|demote)\s+@?/i.exec(text.trim());
  if (!cmd) return false;
  const action = cmd[1].toLowerCase();
  const mentioned = (msg.mentionedIds || [])[0];
  if (!mentioned) {
    await msg.reply(`Pakai: _${action} @sebutnama_ (sebut member yang mau di-${action}).`);
    return true;
  }
  try {
    if (action === 'kick') await client.groupRemoveParticipants(jid, [mentioned]);
    else if (action === 'promote') await client.promoteParticipants(jid, [mentioned]);
    else await client.demoteParticipants(jid, [mentioned]);
    await msg.reply(`✅ ${action} berhasil.`);
  } catch (e) {
    await msg.reply(`❌ Gagal ${action}: ${e.message || e}`);
  }
  return true;
}

// ---------------- routing pesan ----------------
client.on('message', async (msg) => {
  try {
    if (msg.fromMe) return;
    const jid = msg.from;
    const inGroup = jid.endsWith('@g.us');
    const text = (msg.body || '').trim();
    const name = msg.pushname;
    const isAdmin = isAdminNum(numOf(jid));
    const st = states.get(jid);

    // --- mode aktif ---
    if (st && !inGroup) {
      if (text.toLowerCase() === 'batal') { states.delete(jid); return msg.reply('❌ Dibatalkan. Ketik *menu*.'); }
      if (st.mode === 'aichat') {
        if (text.toLowerCase() === 'stop') {
          states.delete(jid); db.clearHistory(jid);
          return msg.reply('⏹️ AI Chat dimatikan & riwayat dihapus.');
        }
        return doAiText(msg, jid, text);
      }
      if (st.mode === 'buatgrup_nama') return doBuatGrupNama(msg, jid, text);
      if (st.mode === 'buatgrup_owner') return doBuatGrupOwner(msg, jid, text);
      if (st.mode === 'chatowner') { states.delete(jid); return doChatOwner(msg, jid, text); }
    }

    // --- grup: welcome set / moderasi (admin) ---
    if (inGroup) {
      if (isAdmin) {
        if (/^welcome\s+off$/i.test(text)) { db.setWelcome(jid, null); return msg.reply('✅ Welcome dimatikan untuk grup ini.'); }
        if (/^welcome\s+set\s+/i.test(text)) return doWelcomeSet(msg, jid, text);
        const handled = await handleGroupMod(msg, jid, text);
        if (handled) return;
      }
      return; // di grup hanya admin command yang diproses
    }

    // --- private: menu & command ---
    const isNew = !db.getUsers().find((u) => u.jid === jid);
    db.touchUser(jid, name);

    const t = text.toLowerCase();
    if (t === 'menu' || t === 'start' || t === 'help' || t === 'halo' || t === 'hai' || t === 'hi' || isNew) {
      return msg.reply(menuText(name, isAdmin));
    }
    if (t === '1' || t === 'cekid' || t === 'cek id') return doCekId(msg, jid);
    if (t === '2' || t === 'ai') return doAiToggle(msg, jid);
    if (t === '3' || t === 'buatgrup' || t === 'buat grup') return doBuatGrupStart(msg, jid);
    if (t === '4' || t === 'chatowner' || t === 'chat owner') {
      states.set(jid, { mode: 'chatowner' });
      return msg.reply('💬 *Chat dengan Owner*\n\nKirim pesanmu — akan diteruskan ke Pall:');
    }
    if (t === '5' || t.startsWith('ingat ')) return doIngat(msg, jid, text);
    if (t === '6' || t === 'waktu' || t === 'jam') {
      const wib = new Date().toLocaleTimeString('id-ID', { timeZone: 'Asia/Jakarta', hour12: false });
      return msg.reply(`🕐 *${wib} WIB`);
    }
    if (t === '7' || t === 'bantuan') return msg.reply(helpText());
    if (isAdmin && t === '8') return doBroadcast(msg, jid, 'broadcast');
    if (isAdmin && t.startsWith('broadcast ')) return doBroadcast(msg, jid, text);
    if (isAdmin && t === '9') return doUsersList(msg, jid);
    if (t.startsWith('stop') && st && st.mode === 'aichat') {
      states.delete(jid); db.clearHistory(jid);
      return msg.reply('⏹️ AI Chat dimatikan & riwayat dihapus.');
    }
    // teks bebas tanpa mode: arahkan ke menu / AI ringan
    if (text.length > 0) {
      return msg.reply(`🤔 Fitur ini lewat menu. Ketik *menu*.\n\n(atau *2* untuk AI Chat)`);
    }
  } catch (e) {
    console.error('error handle message:', e);
  }
});

// welcome member baru
client.on('group-participants-add', async (g, participants) => {
  try {
    const w = db.getWelcome(g.id);
    if (!w) return;
    for (const p of participants) {
      const info = await client.getContactById(p);
      const nama = info.pushname || numOf(p);
      await g.sendMessage(`👋 Selamat datang *${nama}*!\n\n${w}`);
    }
  } catch (e) {
    console.error('welcome error:', e);
  }
});

// pengingat
setInterval(async () => {
  try {
    for (const r of db.dueReminders(now())) {
      try {
        await client.sendMessage(r.jid, { text: `⏰ *Pengingat:*\n\n${r.text}` });
      } catch (_) {}
      db.doneReminder(r.id);
    }
  } catch (_) {}
}, 30000).unref();

// ---------------- start ----------------
(async () => {
  if (!cfg.aiKey) console.warn('⚠️  AI_KEY kosong di .env — fitur AI tidak akan jalan.');
  if (!cfg.waOwnerChat) console.warn('⚠️  WA_OWNER_CHAT kosong — fitur "Chat dengan Owner" mati.');
  if (!cfg.waOwners.length) console.warn('⚠️  WA_OWNERS kosong — pilih owner & deteksi admin pakai WA_OWNER_CHAT saja.');
  if (forceLogin) {
    console.log('🔄 Mode paksa login — hapus session lama...');
    fs.rmSync(path.join(__dirname, 'wwebjs_auth'), { recursive: true, force: true });
  }
  await client.initialize();
  await client.login();
  console.log('Menunggu koneksi/QR... (Ctrl+C untuk stop)');
  console.log('Tip: tail -f log, atau jalankan via systemd lalu `journalctl -u pallbot-wa -f` untuk lihat QR.');
})();

process.on('SIGINT', async () => { await client.destroy(); process.exit(0); });
