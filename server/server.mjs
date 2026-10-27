import { createServer } from 'node:http';
import { resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openStore, hash, feed, append, page, vaultPattern } from './store.mjs';

const maxBody = 8 * 1024 * 1024;

async function bodyOf(request) {
  if (Number(request.headers['content-length']) > maxBody) {
    throw Object.assign(new Error('request too large'), { status: 413 });
  }
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maxBody) throw Object.assign(new Error('request too large'), { status: 413 });
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw Object.assign(new Error('invalid json'), { status: 400 }); }
}

export function makeServer(db) {
  const buckets = new Map();
  const server = createServer({ requestTimeout: 15000, headersTimeout: 10000, maxHeaderSize: 8192 }, async (request, response) => {
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    const send = (status, value) => {
      response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
      response.end(value === undefined ? undefined : JSON.stringify(value));
    };
    try {
      const url = new URL(request.url, 'http://localhost');
      if (request.method === 'GET' && url.pathname === '/v1/badges') {
        const body = feed(db);
        const etag = `"${hash(body)}"`;
        response.setHeader('ETag', etag);
        const matches = (request.headers['if-none-match'] ?? '').split(',').some(value => {
          const tag = value.trim();
          return tag === '*' || tag.replace(/^W\//, '') === etag;
        });
        if (matches) return send(304);
        response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        return response.end(body);
      }
      const match = /^\/v1\/vaults\/([a-f0-9]{32})\/events$/.exec(url.pathname);
      if (!match || !vaultPattern.test(match[1])) return send(404, { error: 'not found' });
      const vault = match[1];
      const bearer = /^Bearer ([a-f0-9]{64})$/.exec(request.headers.authorization ?? '');
      if (!bearer || !db.prepare('SELECT 1 FROM tokens WHERE hash=? AND vault=?').get(hash(bearer[1]), vault)) {
        return send(401, { error: 'unauthorized' });
      }
      const minute = Math.floor(Date.now() / 60000);
      const key = hash(bearer[1]);
      const bucket = buckets.get(key);
      const count = bucket?.minute === minute ? bucket.count + 1 : 1;
      if (buckets.size >= 10000) for (const [id, old] of buckets) if (old.minute !== minute) buckets.delete(id);
      if (!buckets.has(key) && buckets.size >= 10000) return send(503, { error: 'busy' });
      buckets.set(key, { minute, count });
      if (count > 120) {
        response.setHeader('Retry-After', '60');
        return send(429, { error: 'rate limit' });
      }
      if (request.method === 'GET') {
        const after = url.searchParams.get('after') ?? '0';
        if (!/^(0|[1-9][0-9]{0,18})$/.test(after) || BigInt(after) > 9223372036854775807n) {
          return send(400, { error: 'invalid cursor' });
        }
        return send(200, page(db, vault, BigInt(after)));
      }
      if (request.method === 'POST') {
        if ((request.headers['content-type'] ?? '').split(';')[0] !== 'application/json') {
          return send(415, { error: 'json required' });
        }
        const body = await bodyOf(request);
        append(db, vault, body?.events);
        return send(200, { ok: true });
      }
      response.setHeader('Allow', 'GET, POST');
      return send(405, { error: 'method not allowed' });
    } catch (error) {
      if (!response.headersSent) send(error.status ?? 500, { error: error.status ? error.message : 'internal error' });
      else response.end();
    }
  });
  server.maxConnections = 128;
  return server;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const path = process.env.MAD_DATABASE;
  if (!path || !isAbsolute(path)) throw new Error('set MAD_DATABASE to an absolute path outside the source tree');
  const db = openStore(path);
  const server = makeServer(db);
  const host = process.env.MAD_HOST ?? '127.0.0.1';
  const port = Number(process.env.MAD_PORT ?? 8787);
  server.listen(port, host, () => console.log(`mad server listening on ${host}:${port}`));
  const stop = () => server.close(() => { db.close(); process.exit(0); });
  process.on('SIGINT', stop);
  process.on('SIGTERM', stop);
}
