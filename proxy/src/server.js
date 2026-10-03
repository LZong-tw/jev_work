#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { loadDotEnv, readConfig } from './config.js';
import { KeyStore } from './keys.js';
import { invalidJson, mockModels, mockSystemOne } from './mock.js';
import { UsageStore } from './usage.js';

// Request headers we pass on to Jev. Everything else (cookies, the caller's
// Authorization, forwarding headers) stays at the proxy.
const FORWARD_REQUEST_HEADERS = ['content-type', 'accept', 'accept-language'];
// Upstream response headers the SDKs read: request id (for support) and how long to wait before a retry.
const PASS_RESPONSE_HEADERS = ['x-typesafe-request-id', 'retry-after', 'retry-after-ms'];

export function createProxy(config) {
  const keys = new KeyStore(config.keysFile, config.defaults, { watch: !config.noWatch });
  const usage = new UsageStore(config.usageFile, config.timeZone);
  const logStream = config.logFile ? fs.createWriteStream(config.logFile, { flags: 'a' }) : null;

  if (!config.mockUpstream && !config.upstreamApiKey) {
    console.warn('[proxy] JEV_API_KEY is not set. Upstream calls will fail with 401. Set MOCK_UPSTREAM=1 to rehearse without a key.');
  }
  if (keys.list().length === 0) {
    console.warn(`[proxy] no keys loaded from ${config.keysFile}. Run "npm run keys -- --count 5" to create some.`);
  }

  function log(entry) {
    const line = JSON.stringify({ ts: new Date().toISOString(), ...entry });
    if (!config.quiet) console.log(line);
    logStream?.write(line + '\n');
  }

  // Errors use TypeSafe's own shape, so clients handle proxy and API errors the same way.
  function apiError(status, errorType, message) {
    return { status, body: { detail: { error_type: errorType, message } } };
  }

  function send(res, status, body, headers = {}) {
    const payload = typeof body === 'string' ? body : JSON.stringify(body);
    res.writeHead(status, {
      'content-type': 'application/json; charset=utf-8',
      'content-length': Buffer.byteLength(payload),
      ...corsHeaders(),
      ...headers,
    });
    res.end(payload);
  }

  function corsHeaders() {
    if (!config.corsOrigin) return {};
    return {
      'access-control-allow-origin': config.corsOrigin,
      'access-control-allow-headers': 'authorization, content-type, x-api-key',
      'access-control-allow-methods': 'GET, POST, OPTIONS',
      'access-control-expose-headers': 'x-request-id, x-typesafe-request-id, retry-after, retry-after-ms, x-proxy-budget-remaining-usd',
    };
  }

  function readBody(req) {
    return new Promise((resolve, reject) => {
      const tooLarge = () => Object.assign(new Error(`Body too large (max ${config.maxBodyBytes} bytes)`), { status: 413 });
      if (Number(req.headers['content-length']) > config.maxBodyBytes) return reject(tooLarge());
      const chunks = [];
      let size = 0;
      const onData = (chunk) => {
        size += chunk.length;
        if (size > config.maxBodyBytes) {
          req.off('data', onData);
          reject(tooLarge());
          return;
        }
        chunks.push(chunk);
      };
      req.on('data', onData);
      req.on('end', () => resolve(Buffer.concat(chunks)));
      req.on('error', reject);
    });
  }

  function clientKey(req) {
    const auth = req.headers.authorization || '';
    const m = auth.match(/^Bearer\s+(.+)$/i);
    if (m) return m[1].trim();
    return (req.headers['x-api-key'] || '').trim() || null;
  }

  function isAdmin(req) {
    if (!config.adminToken) return false;
    const token = clientKey(req) || '';
    const a = Buffer.from(token);
    const b = Buffer.from(config.adminToken);
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  }

  // /v1/systemone (and /api/v1/systemone) map to upstream /v1/systemone, so callers
  // only swap the base URL they already use.
  function upstreamPath(pathname) {
    const m = pathname.match(/^(?:\/api)?(\/v1\/[A-Za-z0-9/_-]+)$/);
    return m ? m[1] : null;
  }

  function checkLimits(key) {
    if (!key.enabled) return apiError(403, 'permission_error', 'This API key is disabled.');
    if (key.expiresAt && Date.now() > key.expiresAt) return apiError(403, 'permission_error', 'This API key has expired.');
    const spent = usage.entry(key.name).cost_usd;
    if (key.maxCostUsd != null && spent >= key.maxCostUsd) {
      return apiError(402, 'budget_exceeded_error', 'This key has used its full budget.');
    }
    if (key.dailyRequests && usage.today(key.name).requests >= key.dailyRequests) {
      return apiError(429, 'rate_limit_error', 'Daily request limit reached for this key.');
    }
    const wait = usage.hitRateLimit(key.name, key.rpm);
    if (wait) {
      return { ...apiError(429, 'rate_limit_error', `Too many requests. Try again in ${wait}s.`), headers: { 'retry-after': String(wait) } };
    }
    return null;
  }

  async function callUpstream(method, path, search, body, requestHeaders) {
    if (config.mockUpstream) {
      let r;
      if (path === '/v1/models' && method === 'GET') r = mockModels();
      else if (path === '/v1/systemone' && method === 'POST') {
        try {
          r = mockSystemOne(JSON.parse(body.toString('utf8')));
        } catch (err) {
          r = invalidJson(err);
        }
      } else r = { status: 404, body: { detail: 'Not Found' } };
      const mockHeaders = { 'x-typesafe-request-id': `req_${crypto.randomBytes(16).toString('hex')}` };
      return { status: r.status, body: JSON.stringify(r.body), contentType: 'application/json', headers: mockHeaders };
    }

    const headers = { authorization: `Bearer ${config.upstreamApiKey}`, 'user-agent': 'jev-proxy/1.0' };
    for (const h of FORWARD_REQUEST_HEADERS) if (requestHeaders[h]) headers[h] = requestHeaders[h];

    const res = await fetch(config.upstreamBaseUrl + path + search, {
      method,
      headers,
      body: method === 'GET' || method === 'HEAD' ? undefined : body,
      signal: AbortSignal.timeout(config.upstreamTimeoutMs),
    });
    const passed = {};
    for (const h of PASS_RESPONSE_HEADERS) if (res.headers.has(h)) passed[h] = res.headers.get(h);
    return { status: res.status, body: await res.text(), contentType: res.headers.get('content-type'), headers: passed };
  }

  // Read the token usage for our counters. The body itself is passed on unchanged.
  // TypeSafe bills input tokens only; the cost is computed from the published price.
  function readUsage(text) {
    let json;
    try {
      json = JSON.parse(text);
    } catch {
      return { inputTokens: 0, costUsd: 0 };
    }
    const u = json && typeof json === 'object' ? json.usage : null;
    const inputTokens = Number(u?.input_tokens) || 0;
    const costUsd = u?.cost_usd != null ? Number(u.cost_usd) || 0 : (inputTokens * config.inputPricePerMillion) / 1e6;
    return { inputTokens, costUsd };
  }

  async function handle(req, res) {
    const started = Date.now();
    const requestId = `req_${crypto.randomBytes(16).toString('hex')}`;
    // Errors made by the proxy itself carry the id in both headers, like TypeSafe's own errors.
    const ids = { 'x-request-id': requestId, 'x-typesafe-request-id': requestId };
    const url = new URL(req.url, 'http://proxy.local');
    const { pathname } = url;

    if (req.method === 'OPTIONS') {
      res.writeHead(204, corsHeaders());
      return res.end();
    }

    if (pathname === '/' || pathname === '/health') {
      return send(res, 200, {
        ok: true,
        service: 'jev-proxy',
        mode: config.mockUpstream ? 'mock' : 'live',
        keys: keys.list().length,
      });
    }

    if (pathname.startsWith('/admin/')) {
      if (!isAdmin(req)) return send(res, 401, { detail: { error_type: 'authentication_error', message: 'Admin token required.' } });
      if (pathname === '/admin/usage' && req.method === 'GET') return send(res, 200, usage.data);
      if (pathname === '/admin/keys' && req.method === 'GET') {
        return send(res, 200, keys.list().map((k) => ({ ...k, used: usage.data[k.name] || null })));
      }
      if (pathname === '/admin/keys/reload' && req.method === 'POST') {
        keys.load();
        return send(res, 200, { ok: true, keys: keys.list().length });
      }
      return send(res, 404, { detail: 'Not Found' });
    }

    const path = upstreamPath(pathname);
    if (!path) return send(res, 404, { detail: 'Not Found' });
    if (!['GET', 'POST'].includes(req.method)) return send(res, 405, { detail: 'Method Not Allowed' });

    const key = keys.lookup(clientKey(req));
    if (!key) {
      log({ id: requestId, key: null, path, status: 401 });
      // Same wording as TypeSafe itself.
      const e = apiError(401, 'authentication_error', 'Cannot authenticate with the server. Please check your API key and try again.');
      return send(res, e.status, e.body, ids);
    }

    const blocked = checkLimits(key);
    if (blocked) {
      log({ id: requestId, key: key.name, path, status: blocked.status, code: blocked.body.detail.error_type });
      return send(res, blocked.status, blocked.body, { ...ids, ...blocked.headers });
    }

    let body;
    try {
      body = await readBody(req);
    } catch (err) {
      log({ id: requestId, key: key.name, path, status: err.status || 400, error: err.message });
      // Answer first, then close: the rest of the body is never read.
      res.on('finish', () => req.destroy());
      const e = apiError(err.status || 400, err.status === 413 ? 'request_too_large' : 'api_usage_error', err.message);
      return send(res, e.status, e.body, { ...ids, connection: 'close' });
    }

    let upstream;
    try {
      upstream = await callUpstream(req.method, path, url.search, body, req.headers);
    } catch (err) {
      usage.record(key.name, { ok: false });
      const timeout = err.name === 'TimeoutError' || err.name === 'AbortError';
      log({ id: requestId, key: key.name, path, status: 502, ms: Date.now() - started, error: err.message });
      const e = apiError(502, 'api_error', timeout ? 'Upstream timed out.' : 'Upstream error, retry with backoff.');
      return send(res, e.status, e.body, ids);
    }

    const ok = upstream.status < 400;
    const text = upstream.body;
    const { inputTokens, costUsd } = readUsage(text);
    usage.record(key.name, { ok, inputTokens, costUsd });
    log({ id: requestId, upstream_id: upstream.headers['x-typesafe-request-id'], key: key.name, path, status: upstream.status, ms: Date.now() - started, input_tokens: inputTokens, cost_usd: costUsd });

    const headers = {
      'content-type': upstream.contentType || 'application/json; charset=utf-8',
      'content-length': Buffer.byteLength(text),
      'x-request-id': requestId,
      ...upstream.headers,
      ...corsHeaders(),
    };
    if (key.maxCostUsd != null) {
      const left = Math.max(0, key.maxCostUsd - usage.entry(key.name).cost_usd);
      headers['x-proxy-budget-remaining-usd'] = String(Math.round(left * 1e6) / 1e6);
    }
    res.writeHead(upstream.status, headers);
    res.end(text);
  }

  const server = http.createServer((req, res) => {
    handle(req, res).catch((err) => {
      console.error('[proxy] unexpected error', err);
      if (!res.headersSent) send(res, 500, { detail: { error_type: 'api_error', message: 'Proxy internal error.' } });
      else res.destroy();
    });
  });

  function close() {
    keys.stop();
    usage.stop();
    logStream?.end();
    return new Promise((resolve) => server.close(resolve));
  }

  return { server, close, keys, usage };
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(fs.realpathSync(process.argv[1])).href;
if (isMain) {
  loadDotEnv();
  const config = readConfig();
  const { server, close } = createProxy(config);
  server.listen(config.port, config.host, () => {
    const { port } = server.address();
    console.log(`[proxy] listening on http://${config.host}:${port} (${config.mockUpstream ? 'MOCK' : config.upstreamBaseUrl})`);
  });
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, async () => {
      console.log(`[proxy] ${signal} received, saving usage and shutting down`);
      await close();
      process.exit(0);
    });
  }
}
