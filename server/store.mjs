import { DatabaseSync } from 'node:sqlite';
import { createHash, randomBytes } from 'node:crypto';

export const hash = data => createHash('sha256').update(data).digest('hex');
export const limit = 2 * 1024 * 1024;
export const idPattern = /^[a-f0-9]{64}$/;
export const vaultPattern = /^[a-f0-9]{32}$/;

export function openStore(path) {
  const db = new DatabaseSync(path);
  db.exec(`
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=FULL;
    PRAGMA foreign_keys=ON;
    PRAGMA busy_timeout=5000;
    CREATE TABLE IF NOT EXISTS vaults(id TEXT PRIMARY KEY, quota INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, vault TEXT NOT NULL REFERENCES vaults(id), label TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, vault TEXT NOT NULL REFERENCES vaults(id), id TEXT NOT NULL, body BLOB NOT NULL, UNIQUE(vault,id));
    CREATE INDEX IF NOT EXISTS events_cursor ON events(vault,seq);
    CREATE TABLE IF NOT EXISTS aliases(alias TEXT PRIMARY KEY, username TEXT NOT NULL, position INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
  `);
  db.prepare('INSERT OR IGNORE INTO config VALUES (?,?)').run('salt', randomBytes(16).toString('base64'));
  return db;
}

export function provision(db, vault = null, label = 'device') {
  const token = randomBytes(32).toString('hex');
  db.exec('BEGIN IMMEDIATE');
  try {
    if (vault === null) {
      vault = randomBytes(16).toString('hex');
      db.prepare('INSERT INTO vaults VALUES (?,?)').run(vault, 512 * 1024 * 1024);
    } else if (!vaultPattern.test(vault) || !db.prepare('SELECT id FROM vaults WHERE id=?').get(vault)) {
      throw new Error('unknown vault');
    }
    db.prepare('INSERT INTO tokens VALUES (?,?,?)').run(hash(token), vault, label);
    db.exec('COMMIT');
    return { version: 1, vault, token };
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
}

export function feed(db) {
  const usernames = Object.create(null);
  for (const row of db.prepare('SELECT * FROM aliases ORDER BY alias').all()) {
    usernames[row.alias] = { username: row.username, position: row.position };
  }
  return Buffer.from(JSON.stringify({
    salt: db.prepare('SELECT value FROM config WHERE key=?').get('salt').value,
    argon2: { memory: 8192, passes: 1, lanes: 1 },
    peers: {}, usernames, notices: [],
  }));
}

export function putAlias(db, alias, username, position = 0) {
  alias = alias.replace(/^@/, '').toLowerCase();
  username = username.replace(/^@/, '').toLowerCase();
  if (!/^[a-z][a-z0-9_]{1,31}$/.test(alias) || !/^[a-z][a-z0-9_]{3,31}$/.test(username)
      || alias === username || !Number.isInteger(position) || position < 0 || position > 1000) {
    throw new Error('invalid alias, username or position');
  }
  if (!db.prepare('SELECT alias FROM aliases WHERE alias=?').get(alias)
      && db.prepare('SELECT count(*) AS n FROM aliases').get().n >= 1000) {
    throw new Error('alias limit reached');
  }
  db.prepare('INSERT INTO aliases VALUES (?,?,?) ON CONFLICT(alias) DO UPDATE SET username=excluded.username, position=excluded.position').run(alias, username, position);
}

export function append(db, vault, events) {
  if (!Array.isArray(events) || events.length < 1 || events.length > 32) {
    throw Object.assign(new Error('invalid batch'), { status: 400 });
  }
  const values = events.map(event => {
    if (!event || !idPattern.test(event.id) || typeof event.blob !== 'string'
        || event.blob.length > Math.ceil(limit / 3) * 4) {
      throw Object.assign(new Error('invalid event'), { status: 400 });
    }
    const body = Buffer.from(event.blob, 'base64');
    if (body.length < 29 || body.length > limit || body.toString('base64') !== event.blob
        || body[0] !== 1 || hash(body) !== event.id) {
      throw Object.assign(new Error('invalid envelope'), { status: 400 });
    }
    return { id: event.id, body };
  });
  db.exec('BEGIN IMMEDIATE');
  try {
    const quota = db.prepare('SELECT quota FROM vaults WHERE id=?').get(vault).quota;
    let bytes = db.prepare('SELECT coalesce(sum(length(body)),0) AS n FROM events WHERE vault=?').get(vault).n;
    const insert = db.prepare('INSERT OR IGNORE INTO events(vault,id,body) VALUES (?,?,?)');
    for (const { id, body } of values) {
      if (db.prepare('SELECT 1 FROM events WHERE vault=? AND id=?').get(vault, id)) continue;
      if (bytes + body.length > quota) throw Object.assign(new Error('vault quota reached'), { status: 413 });
      insert.run(vault, id, body);
      bytes += body.length;
    }
    db.exec('COMMIT');
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
}

export function page(db, vault, after) {
  const query = db.prepare('SELECT seq,id,body FROM events WHERE vault=? AND seq>? ORDER BY seq LIMIT 64');
  query.setReadBigInts(true);
  const events = [];
  let bytes = 0;
  let cursor = after;
  for (const row of query.iterate(vault, after)) {
    if (bytes + row.body.length > 4 * 1024 * 1024) break;
    bytes += row.body.length;
    cursor = row.seq;
    events.push({ seq: String(row.seq), id: row.id, blob: Buffer.from(row.body).toString('base64') });
  }
  return { events, next: String(cursor) };
}
