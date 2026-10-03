import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { after, before, describe, test } from 'node:test';
import { loadDotEnv, readConfig } from '../src/config.js';
import { KeyStore, generateKey, hashKey, KEY_PREFIX } from '../src/keys.js';
import { createProxy } from '../src/server.js';
import { UsageStore, dayKey } from '../src/usage.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'jev-proxy-more-'));
const listen = (server) => new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
const closeServer = (server) => new Promise((resolve) => server.close(resolve));

describe('config', () => {
  test('loadDotEnv reads quotes and comments but never overrides real env vars', () => {
    const dir = tmp();
    const file = path.join(dir, '.env');
    fs.writeFileSync(file, '# comment\nJEVT_A="quoted value"\nJEVT_B=\'single\'\nJEVT_C=plain=with=equals\nnot a line\nJEVT_KEEP=from-file\n');
    process.env.JEVT_KEEP = 'from-env';
    loadDotEnv(file);
    assert.equal(process.env.JEVT_A, 'quoted value');
    assert.equal(process.env.JEVT_B, 'single');
    assert.equal(process.env.JEVT_C, 'plain=with=equals');
    assert.equal(process.env.JEVT_KEEP, 'from-env');
    for (const k of ['JEVT_A', 'JEVT_B', 'JEVT_C', 'JEVT_KEEP']) delete process.env[k];
    loadDotEnv(path.join(dir, 'missing.env')); // no file: no error
  });

  test('readConfig defaults and parsing', () => {
    const d = readConfig({});
    assert.equal(d.port, 8787);
    assert.equal(d.upstreamBaseUrl, 'https://api.typesafe.ai');
    assert.equal(d.mockUpstream, false);
    assert.equal(d.inputPricePerMillion, 0.042); // US$42 per billion input tokens
    assert.equal(d.timeZone, 'Asia/Taipei');
    assert.equal(d.defaults.maxCostUsd, null);
    const c = readConfig({
      PORT: '9000', UPSTREAM_BASE_URL: 'http://x/api///', MOCK_UPSTREAM: 'yes', INPUT_PRICE_PER_MILLION: '1.5',
      DEFAULT_RPM: 'abc', DEFAULT_MAX_COST_USD: '2.5', USAGE_FILE: '',
    });
    assert.equal(c.port, 9000);
    assert.equal(c.upstreamBaseUrl, 'http://x/api');
    assert.equal(c.mockUpstream, true);
    assert.equal(c.inputPricePerMillion, 1.5);
    assert.equal(c.defaults.rpm, 60); // invalid number falls back
    assert.equal(c.defaults.maxCostUsd, 2.5);
    assert.equal(c.usageFile, null); // empty = do not persist
  });
});

describe('keys', () => {
  test('generated keys have the prefix and are unique', () => {
    const a = generateKey();
    assert.ok(a.startsWith(KEY_PREFIX));
    assert.ok(a.length > 30);
    assert.notEqual(a, generateKey());
    assert.equal(hashKey('abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  });

  test('KeyStore accepts plain keys or hashes, applies defaults, reloads', () => {
    const file = path.join(tmp(), 'keys.json');
    fs.writeFileSync(file, JSON.stringify({ keys: [{ key: 'jvp_a' }, { name: 'b', key_hash: hashKey('jvp_b'), rpm: 5, expires_at: '2030-01-01T00:00:00Z' }] }));
    const store = new KeyStore(file, { rpm: 60, dailyRequests: 100, maxCostUsd: null }, { watch: false });
    assert.equal(store.lookup('jvp_a').name, 'key-1');
    assert.equal(store.lookup('jvp_a').rpm, 60);
    assert.equal(store.lookup('jvp_b').rpm, 5);
    assert.equal(store.lookup('jvp_b').expiresAt, Date.parse('2030-01-01T00:00:00Z'));
    assert.equal(store.lookup('nope'), null);
    assert.equal(store.lookup(null), null);

    fs.writeFileSync(file, JSON.stringify([{ key: 'jvp_c', enabled: false }]));
    store.load();
    assert.equal(store.lookup('jvp_a'), null);
    assert.equal(store.lookup('jvp_c').enabled, false);

    fs.writeFileSync(file, JSON.stringify([{ name: 'broken' }]));
    assert.throws(() => store.load(), /needs "key" or "key_hash"/);
    assert.equal(store.lookup('jvp_c').name, 'key-1'); // failed reload keeps the old keys
  });
});

describe('usage store', () => {
  test('dayKey follows the time zone', () => {
    const lateUtc = new Date('2026-10-01T20:00:00Z'); // 04:00 next day in Taipei
    assert.equal(dayKey('UTC', lateUtc), '2026-10-01');
    assert.equal(dayKey('Asia/Taipei', lateUtc), '2026-10-02');
  });

  test('sliding one-minute window', () => {
    const u = new UsageStore(null, 'UTC');
    const t0 = 1_000_000;
    assert.equal(u.hitRateLimit('k', 2, t0), 0);
    assert.equal(u.hitRateLimit('k', 2, t0 + 1000), 0);
    assert.equal(u.hitRateLimit('k', 2, t0 + 2000), 58); // wait until the first hit is 60 s old
    assert.equal(u.hitRateLimit('k', 2, t0 + 60_001), 0); // first hit expired
    assert.equal(u.hitRateLimit('k', 0, t0), 0); // 0 = unlimited
  });

  test('counts and survives a restart', () => {
    const file = path.join(tmp(), 'usage.json');
    const u = new UsageStore(file, 'UTC');
    u.record('alice', { ok: true, inputTokens: 10, costUsd: 0.1 });
    u.record('alice', { ok: false });
    u.stop();
    const again = new UsageStore(file, 'UTC');
    const e = again.entry('alice');
    assert.equal(e.requests, 2);
    assert.equal(e.errors, 1);
    assert.equal(e.input_tokens, 10);
    assert.equal(e.cost_usd, 0.1);
    assert.equal(again.today('alice').requests, 2);
    again.stop();
  });
});

describe('create-keys script', () => {
  test('writes only hashes to keys.json and plain keys to the handout', () => {
    const dir = tmp();
    const script = path.join(here, '..', 'scripts', 'create-keys.js');
    const args = ['--count', '3', '--prefix', 'seat', '--max-cost', '0.5', '--rpm', '90', '--daily', '500',
      '--expires', '2026-10-02T00:00:00+08:00', '--base-url', 'https://proxy.example/api'];
    execFileSync(process.execPath, [script, ...args], { cwd: dir });
    const keys = JSON.parse(fs.readFileSync(path.join(dir, 'keys.json'), 'utf8'));
    assert.deepEqual(keys.map((k) => k.name), ['seat-01', 'seat-02', 'seat-03']);
    for (const k of keys) {
      assert.equal(k.key, undefined);
      assert.match(k.key_hash, /^[0-9a-f]{64}$/);
      assert.equal(k.max_cost_usd, 0.5);
      assert.equal(k.rpm, 90);
      assert.equal(k.daily_requests, 500);
      assert.equal(k.expires_at, '2026-10-01T16:00:00.000Z');
    }
    const rows = fs.readFileSync(path.join(dir, 'keys-handout.csv'), 'utf8').trim().split('\n');
    assert.equal(rows[0], 'name,api_key,base_url');
    const plain = rows.slice(1).map((r) => r.split(','));
    assert.deepEqual(plain.map((r) => hashKey(r[1])), keys.map((k) => k.key_hash));
    assert.ok(plain.every((r) => r[2] === 'https://proxy.example/api'));
    const html = fs.readFileSync(path.join(dir, 'keys-handout.html'), 'utf8');
    assert.ok(html.includes(plain[0][1]) && html.includes('https://proxy.example/api'));

    // running again appends new names and keeps the old keys
    execFileSync(process.execPath, [script, '--count', '2', '--prefix', 'seat'], { cwd: dir });
    const more = JSON.parse(fs.readFileSync(path.join(dir, 'keys.json'), 'utf8'));
    assert.deepEqual(more.map((k) => k.name), ['seat-01', 'seat-02', 'seat-03', 'seat-04', 'seat-05']);
    assert.equal(more[0].key_hash, keys[0].key_hash);
  });

  test('rejects a bad count', () => {
    const script = path.join(here, '..', 'scripts', 'create-keys.js');
    assert.throws(() => execFileSync(process.execPath, [script, '--count', 'zero'], { cwd: tmp(), stdio: 'pipe' }));
  });
});

describe('proxy edge cases', () => {
  let upstream;
  let proxy;
  let base;
  let dir;
  let mode = 'ok';
  const seen = [];
  const OK_BODY = { model: 'jev-1.13.0', answers: { a: { type: 'noul', noul: 0.5 } }, usage: { input_tokens: 10, output_tokens: 5 } };

  before(async () => {
    upstream = http.createServer((req, res) => {
      let body = '';
      req.on('data', (c) => (body += c));
      req.on('end', () => {
        seen.push({ method: req.method, url: req.url, body });
        if (mode === 'hang') return; // never answers
        if (mode === 'text') {
          res.writeHead(503, { 'content-type': 'text/plain' });
          return res.end('maintenance');
        }
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify(OK_BODY));
      });
    });
    const upPort = await listen(upstream);
    dir = tmp();
    fs.writeFileSync(path.join(dir, 'keys.json'), JSON.stringify([
      { name: 'daily', key: 'jvp_daily', daily_requests: 2 },
      { name: 'old', key: 'jvp_old', expires_at: '2020-01-01T00:00:00Z' },
      { name: 'free', key: 'jvp_free' },
      { name: 'budget', key: 'jvp_budget', max_cost_usd: 0.015 },
    ]));
    proxy = createProxy({
      ...readConfig({}),
      upstreamBaseUrl: `http://127.0.0.1:${upPort}/api`,
      upstreamApiKey: 'apikey_owner',
      upstreamTimeoutMs: 300,
      keysFile: path.join(dir, 'keys.json'),
      usageFile: path.join(dir, 'usage.json'),
      logFile: path.join(dir, 'proxy.log'),
      adminToken: 'admin-secret',
      maxBodyBytes: 1000,
      quiet: true,
      noWatch: true,
    });
    base = `http://127.0.0.1:${await listen(proxy.server)}`;
  });

  after(async () => {
    await proxy.close();
    upstream.closeAllConnections?.();
    await closeServer(upstream);
  });

  const call = (key, init = {}, p = '/v1/systemone') =>
    fetch(base + p, { method: 'POST', body: '{"model":"jev-latest","state":"x","questions":{}}', ...init, headers: { authorization: `Bearer ${key}`, ...(init.headers || {}) } });
  const errorType = async (res) => (await res.json()).detail.error_type;

  test('daily limit', async () => {
    mode = 'ok';
    assert.equal((await call('jvp_daily')).status, 200);
    assert.equal((await call('jvp_daily')).status, 200);
    const r = await call('jvp_daily');
    assert.equal(r.status, 429);
    assert.equal(await errorType(r), 'rate_limit_error');
  });

  test('expired key', async () => {
    const r = await call('jvp_old');
    assert.equal(r.status, 403);
    assert.equal(await errorType(r), 'permission_error');
  });

  test('no budget header when the key has no budget; body passed on as is', async () => {
    const r = await call('jvp_free');
    assert.equal(r.headers.get('x-proxy-budget-remaining-usd'), null);
    assert.deepEqual(await r.json(), OK_BODY);
  });

  test('body too large is rejected with 413', async () => {
    const r = await call('jvp_free', { body: 'x'.repeat(5000) });
    assert.equal(r.status, 413);
    assert.equal(await errorType(r), 'request_too_large');
    // streamed body without Content-Length: checked while reading
    const stream = new ReadableStream({ start(c) { for (let i = 0; i < 5; i++) c.enqueue(new TextEncoder().encode('y'.repeat(400))); c.close(); } });
    const r2 = await call('jvp_free', { body: stream, duplex: 'half' });
    assert.equal(r2.status, 413);
    assert.equal((await call('jvp_free')).status, 200); // proxy still healthy
  });

  test('upstream timeout and non-JSON errors', async () => {
    mode = 'hang';
    let r = await call('jvp_free');
    assert.equal(r.status, 502);
    assert.deepEqual(await r.json(), { detail: { error_type: 'api_error', message: 'Upstream timed out.' } });
    mode = 'text';
    r = await call('jvp_free');
    assert.equal(r.status, 503);
    assert.equal(await r.text(), 'maintenance'); // passed through unchanged
    mode = 'ok';
  });

  test('GET and query strings are forwarded; other methods are not', async () => {
    seen.length = 0;
    const r = await fetch(`${base}/v1/models?x=1`, { headers: { authorization: 'Bearer jvp_free' } });
    assert.equal(r.status, 200);
    assert.deepEqual([seen[0].method, seen[0].url, seen[0].body], ['GET', '/api/v1/models?x=1', '']);
    assert.equal((await call('jvp_free', { method: 'PUT' })).status, 405);
    assert.equal((await call('jvp_free', {}, '/api/v2/systemone')).status, 404);
    assert.equal((await call('jvp_free', {}, '/api/v1/../../etc')).status, 404);
  });

  test('CORS preflight', async () => {
    const r = await fetch(`${base}/v1/systemone`, { method: 'OPTIONS' });
    assert.equal(r.status, 204);
    assert.equal(r.headers.get('access-control-allow-origin'), '*');
    assert.match(r.headers.get('access-control-allow-headers'), /authorization/);
  });

  test('admin endpoints', async () => {
    const admin = { authorization: 'Bearer admin-secret' };
    assert.equal((await fetch(`${base}/admin/usage`, { headers: { authorization: 'Bearer wrong' } })).status, 401);
    const usage = await (await fetch(`${base}/admin/usage`, { headers: admin })).json();
    assert.ok(usage.daily.requests >= 2);
    const keys = await (await fetch(`${base}/admin/keys`, { headers: admin })).json();
    assert.deepEqual(keys.map((k) => k.name).sort(), ['budget', 'daily', 'free', 'old']);
    assert.ok(!JSON.stringify(keys).includes('jvp_')); // never shows keys or hashes
    assert.ok(!JSON.stringify(keys).includes(hashKey('jvp_free')));
    fs.writeFileSync(path.join(dir, 'keys.json'), JSON.stringify([{ name: 'new', key: 'jvp_new' }]));
    const reload = await (await fetch(`${base}/admin/keys/reload`, { method: 'POST', headers: admin })).json();
    assert.deepEqual(reload, { ok: true, keys: 1 });
    assert.equal((await call('jvp_new')).status, 200);
    assert.equal((await call('jvp_free')).status, 401);
    assert.equal((await fetch(`${base}/admin/nope`, { headers: admin })).status, 404);
  });

  test('the log has one JSON line per request and never the request body', async () => {
    await call('jvp_new', { body: '{"state":"SECRET-CUSTOMER-DATA","questions":{}}' });
    await new Promise((r) => setTimeout(r, 50));
    const lines = fs.readFileSync(path.join(dir, 'proxy.log'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
    assert.ok(lines.length >= 10);
    assert.ok(lines.every((l) => l.ts && 'status' in l));
    assert.ok(!fs.readFileSync(path.join(dir, 'proxy.log'), 'utf8').includes('SECRET-CUSTOMER-DATA'));
  });

  test('admin is disabled when no admin token is configured', async () => {
    const p = createProxy({ ...readConfig({}), keysFile: path.join(dir, 'keys.json'), usageFile: null, quiet: true, noWatch: true, mockUpstream: true });
    const port = await listen(p.server);
    assert.equal((await fetch(`http://127.0.0.1:${port}/admin/usage`, { headers: { authorization: 'Bearer ' } })).status, 401);
    await p.close();
  });
});

describe('budget survives a restart', () => {
  test('a spent key stays spent after the proxy restarts', async () => {
    const dir = tmp();
    const keysFile = path.join(dir, 'keys.json');
    const usageFile = path.join(dir, 'usage.json');
    fs.writeFileSync(keysFile, JSON.stringify([{ name: 'b', key: 'jvp_b', max_cost_usd: 0.0000001 }]));
    const cfg = { ...readConfig({}), mockUpstream: true, keysFile, usageFile, quiet: true, noWatch: true };
    const body = JSON.stringify({ model: 'jev-latest', state: 'a long enough state to cost something', questions: { q: { type: 'noul', instructions: 'ok?' } } });
    const hit = async (port) => (await fetch(`http://127.0.0.1:${port}/v1/systemone`, { method: 'POST', headers: { authorization: 'Bearer jvp_b' }, body })).status;

    let p = createProxy(cfg);
    let port = await listen(p.server);
    assert.equal(await hit(port), 200);
    assert.equal(await hit(port), 402);
    await p.close(); // flushes usage.json

    p = createProxy(cfg);
    port = await listen(p.server);
    assert.equal(await hit(port), 402);
    await p.close();
  });
});
