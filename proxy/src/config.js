import fs from 'node:fs';
import path from 'node:path';

// Minimal .env loader: KEY=value lines, '#' comments, optional quotes.
// Real environment variables always win over the file.
export function loadDotEnv(file = path.resolve(process.cwd(), '.env')) {
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (!(key in process.env)) process.env[key] = value;
  }
}

function num(value, fallback) {
  if (value === undefined || value === '') return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function bool(value, fallback) {
  if (value === undefined || value === '') return fallback;
  return ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase());
}

export function readConfig(env = process.env) {
  return {
    port: num(env.PORT, 8787),
    host: env.HOST || '0.0.0.0',

    // Upstream Jev API. The proxy forwards /v1/* to `${upstreamBaseUrl}/v1/*`.
    upstreamBaseUrl: (env.UPSTREAM_BASE_URL || 'https://api.typesafe.ai').replace(/\/+$/, ''),
    upstreamApiKey: env.JEV_API_KEY || '',
    upstreamTimeoutMs: num(env.UPSTREAM_TIMEOUT_MS, 30_000),

    // Answer locally with a fake Jev. No upstream key needed. Good for rehearsals and tests.
    mockUpstream: bool(env.MOCK_UPSTREAM, false),

    keysFile: path.resolve(env.KEYS_FILE || 'keys.json'),
    usageFile: env.USAGE_FILE === '' ? null : path.resolve(env.USAGE_FILE || 'usage.json'),
    logFile: env.LOG_FILE ? path.resolve(env.LOG_FILE) : null,
    adminToken: env.ADMIN_TOKEN || '',

    // Limits used when a key does not set its own.
    defaults: {
      rpm: num(env.DEFAULT_RPM, 60),
      dailyRequests: num(env.DEFAULT_DAILY_REQUESTS, 2000),
      maxCostUsd: env.DEFAULT_MAX_COST_USD ? num(env.DEFAULT_MAX_COST_USD, null) : null,
    },

    maxBodyBytes: num(env.MAX_BODY_BYTES, 512 * 1024),
    // TypeSafe price: US$42 per billion input tokens (output tokens are free). Used for budgets.
    inputPricePerMillion: num(env.INPUT_PRICE_PER_MILLION, 0.042),
    corsOrigin: env.CORS_ORIGIN ?? '*',
    // Time zone used to decide when "today" ends for daily limits.
    timeZone: env.TIME_ZONE || 'Asia/Taipei',
  };
}
