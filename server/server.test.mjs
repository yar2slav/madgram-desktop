import test from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes, createCipheriv, createDecipheriv } from 'node:crypto';
import { unlinkSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { openStore, provision, putAlias, hash, append, page } from './store.mjs';
import { makeServer } from './server.mjs';

function seal(key, vault, text) {
  const nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, nonce);
  cipher.setAAD(Buffer.from(`mad-history-v1:${vault}`));
  const ciphertext = Buffer.concat([cipher.update(text), cipher.final()]);
  const blob = Buffer.concat([Buffer.from([1]), nonce, cipher.getAuthTag(), ciphertext]);
  return { id: hash(blob), blob: blob.toString('base64') };
}

function open(key, vault, event) {
  const blob = Buffer.from(event.blob, 'base64');
  assert.equal(blob[0], 1);
  const cipher = createDecipheriv('aes-256-gcm', key, blob.subarray(1, 13));
  cipher.setAAD(Buffer.from(`mad-history-v1:${vault}`));
  cipher.setAuthTag(blob.subarray(13, 29));
  return Buffer.concat([cipher.update(blob.subarray(29)), cipher.final()]);
}

async function setup(t) {
  const db = openStore(':memory:');
  const account = provision(db);
  const server = makeServer(db);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    db.close();
  });
  const origin = `http://127.0.0.1:${server.address().port}`;
  const call = (suffix = '', init = {}, credentials = account) => fetch(
    `${origin}/v1/vaults/${credentials.vault}/events${suffix}`, {
      ...init,
      headers: { Authorization: `Bearer ${credentials.token}`, 'Content-Type': 'application/json', ...init.headers },
    });
  return { db, account, origin, call };
}

test('encrypted history survives transfer without exposing plaintext to the store', async t => {
  const { db, account, call } = await setup(t);
  const key = randomBytes(32);
  const text = Buffer.from(JSON.stringify({ account: '9007199254740993', peer: '-1001234567890', text: 'private message', kind: 'edit' }));
  const event = seal(key, account.vault, text);
  const request = { method: 'POST', body: JSON.stringify({ events: [event] }) };
  assert.equal((await call('', request)).status, 200);
  assert.equal((await call('', request)).status, 200);
  const result = await (await call()).json();
  assert.equal(result.events.length, 1);
  assert.deepEqual(open(key, account.vault, result.events[0]), text);
  assert.equal(Buffer.from(db.prepare('SELECT body FROM events').get().body).includes('private message'), false);
  assert.deepEqual((await (await call(`?after=${result.next}`)).json()).events, []);
});

test('wrong key, swapped vault, modified ciphertext and tag are rejected by the client cipher', () => {
  const key = randomBytes(32);
  const vault = 'a'.repeat(32);
  const event = seal(key, vault, Buffer.from('secret'));
  assert.throws(() => open(randomBytes(32), vault, event));
  assert.throws(() => open(key, 'b'.repeat(32), event));
  for (const offset of [1, 13, 29]) {
    const bytes = Buffer.from(event.blob, 'base64');
    bytes[offset] ^= 1;
    assert.throws(() => open(key, vault, { blob: bytes.toString('base64') }));
  }
});

test('vault isolation and revocation apply to every endpoint', async t => {
  const { db, account, call } = await setup(t);
  const other = provision(db);
  assert.equal((await call('', {}, { ...account, token: other.token })).status, 401);
  assert.equal((await call('', { method: 'POST', body: '{}' }, { ...account, token: other.token })).status, 401);
  const device = provision(db, account.vault, 'second pc');
  assert.equal((await call('', {}, device)).status, 200);
  db.prepare('DELETE FROM tokens WHERE hash=?').run(hash(device.token));
  assert.equal((await call('', {}, device)).status, 401);
  assert.equal((await call()).status, 200);
});

test('aliases are compatible with tele and etag tracks exact response bytes', async t => {
  const { db, origin } = await setup(t);
  putAlias(db, 'short', 'real_user', 1);
  const response = await fetch(`${origin}/v1/badges`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const etag = response.headers.get('etag');
  assert.equal(etag, `"${hash(bytes)}"`);
  assert.deepEqual(JSON.parse(bytes).usernames.short, { username: 'real_user', position: 1 });
  assert.equal((await fetch(`${origin}/v1/badges`, { headers: { 'If-None-Match': etag } })).status, 304);
  for (const candidate of [`W/${etag}`, `"other", W/${etag}`, '*']) {
    assert.equal((await fetch(`${origin}/v1/badges`, { headers: { 'If-None-Match': candidate } })).status, 304);
  }
  assert.equal((await fetch(`${origin}/v1/badges`, { headers: { 'If-None-Match': 'W/"other"' } })).status, 200);
  putAlias(db, 'short', 'another_user');
  assert.equal((await fetch(`${origin}/v1/badges`, { headers: { 'If-None-Match': etag } })).status, 200);
  assert.throws(() => putAlias(db, 'a', 'test'));
  assert.throws(() => putAlias(db, 'same', 'same'));
});

test('invalid input and quota failure leave no partial batch', async t => {
  const { db, account, call } = await setup(t);
  assert.equal((await call('?after=-1')).status, 400);
  assert.equal((await call('?after=9223372036854775808')).status, 400);
  assert.equal((await call('', { method: 'POST', body: '{' })).status, 400);
  const key = randomBytes(32);
  const event = seal(key, account.vault, Buffer.from('a'));
  assert.equal((await call('', { method: 'POST', body: JSON.stringify({ events: [{ ...event, id: '0'.repeat(64) }] }) })).status, 400);
  db.prepare('UPDATE vaults SET quota=40').run();
  assert.equal((await call('', { method: 'POST', body: JSON.stringify({ events: [event, seal(key, account.vault, Buffer.from('b'))] }) })).status, 413);
  assert.equal(db.prepare('SELECT count(*) AS n FROM events').get().n, 0);
});

test('cursors preserve integers beyond javascript number precision', () => {
  const db = openStore(':memory:');
  try {
    const account = provision(db);
    db.prepare('INSERT INTO events(seq,vault,id,body) VALUES (?,?,?,?)').run(9007199254740993n, account.vault, 'a'.repeat(64), Buffer.alloc(29, 1));
    append(db, account.vault, [seal(randomBytes(32), account.vault, Buffer.from('next'))]);
    const result = page(db, account.vault, 9007199254740993n);
    assert.equal(result.next, '9007199254740994');
    assert.equal(result.events.length, 1);
  } finally { db.close(); }
});

test('history, aliases and device tokens survive reopening the database', () => {
  const path = join(tmpdir(), `mad-server-test-${randomBytes(16).toString('hex')}.sqlite`);
  let db;
  try {
    db = openStore(path);
    const account = provision(db);
    putAlias(db, 'short', 'canonical_user');
    const key = randomBytes(32);
    append(db, account.vault, [seal(key, account.vault, Buffer.from('retained after restart'))]);
    db.close();
    db = openStore(path);
    const result = page(db, account.vault, 0n);
    assert.equal(open(key, account.vault, result.events[0]).toString(), 'retained after restart');
    assert.equal(db.prepare('SELECT username FROM aliases WHERE alias=?').get('short').username, 'canonical_user');
    assert.equal(db.prepare('SELECT vault FROM tokens WHERE hash=?').get(hash(account.token)).vault, account.vault);
  } finally {
    db?.close();
    for (const suffix of ['', '-wal', '-shm']) if (existsSync(path + suffix)) unlinkSync(path + suffix);
  }
});

test('admin refuses to overwrite credentials or create a device without a vault', () => {
  const path = join(tmpdir(), `mad-admin-test-${randomBytes(16).toString('hex')}`);
  const output = path + '.json';
  const run = (...args) => spawnSync(process.execPath, [fileURLToPath(new URL('admin.mjs', import.meta.url)), ...args], {
    env: { ...process.env, MAD_DATABASE: path }, encoding: 'utf8',
  });
  let db;
  try {
    assert.equal(run('create-vault', output).status, 0);
    assert.notEqual(run('create-vault', output).status, 0);
    assert.notEqual(run('add-device', path + '-second.json').status, 0);
    db = openStore(path);
    assert.equal(db.prepare('SELECT count(*) AS n FROM vaults').get().n, 1);
    assert.equal(db.prepare('SELECT count(*) AS n FROM tokens').get().n, 1);
  } finally {
    db?.close();
    for (const suffix of ['', '-wal', '-shm', '.json', '-second.json']) if (existsSync(path + suffix)) unlinkSync(path + suffix);
  }
});
