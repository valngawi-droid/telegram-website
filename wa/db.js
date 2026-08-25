// Database SQLite (better-sqlite3) — data khusus bot WA
const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');

const dataDir = path.join(__dirname, '..', 'data');
fs.mkdirSync(dataDir, { recursive: true });
const db = new Database(path.join(dataDir, 'pallbot_wa.db'));
db.pragma('journal_mode = WAL');

db.exec(`
CREATE TABLE IF NOT EXISTS wa_users (
  jid TEXT PRIMARY KEY,
  name TEXT,
  created_at REAL,
  last_used REAL
);
CREATE TABLE IF NOT EXISTS wa_groups (
  jid TEXT PRIMARY KEY,
  welcome TEXT,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS wa_msgs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  jid TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS wa_reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  jid TEXT NOT NULL,
  due_ts REAL NOT NULL,
  text TEXT NOT NULL,
  done INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_wa_msgs ON wa_msgs(jid, id);
`);

const now = () => Date.now() / 1000;

module.exports = {
  touchUser(jid, name) {
    db.prepare(
      `INSERT INTO wa_users(jid, name, created_at, last_used) VALUES(?,?,?,?)
       ON CONFLICT(jid) DO UPDATE SET name=excluded.name, last_used=excluded.last_used`
    ).run(jid, name || '', now(), now());
  },
  getUsers() {
    return db.prepare('SELECT * FROM wa_users ORDER BY last_used DESC').all();
  },
  setWelcome(jid, text) {
    db.prepare(
      `INSERT INTO wa_groups(jid, welcome, created_at) VALUES(?,?,?)
       ON CONFLICT(jid) DO UPDATE SET welcome=excluded.welcome`
    ).run(jid, text || null, now());
  },
  getWelcome(jid) {
    const r = db.prepare('SELECT welcome FROM wa_groups WHERE jid=?').get(jid);
    return r ? r.welcome : null;
  },
  addMsg(jid, role, content) {
    db.prepare('INSERT INTO wa_msgs(jid, role, content, created_at) VALUES(?,?,?,?)')
      .run(jid, role, content, now());
  },
  getHistory(jid, limit = 10) {
    const rows = db.prepare(
      'SELECT role, content FROM wa_msgs WHERE jid=? ORDER BY id DESC LIMIT ?'
    ).all(jid, limit);
    return rows.reverse();
  },
  clearHistory(jid) {
    db.prepare('DELETE FROM wa_msgs WHERE jid=?').run(jid);
  },
  addReminder(jid, dueTs, text) {
    db.prepare('INSERT INTO wa_reminders(jid, due_ts, text) VALUES(?,?,?)')
      .run(jid, dueTs, text);
  },
  dueReminders(t) {
    return db.prepare('SELECT * FROM wa_reminders WHERE done=0 AND due_ts<=?').all(t);
  },
  doneReminder(id) {
    db.prepare('UPDATE wa_reminders SET done=1 WHERE id=?').run(id);
  },
};
