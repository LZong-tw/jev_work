import crypto from 'node:crypto';
import fs from 'node:fs';

export const KEY_PREFIX = 'jvp_';

export function hashKey(key) {
  return crypto.createHash('sha256').update(key).digest('hex');
}

export function generateKey() {
  return KEY_PREFIX + crypto.randomBytes(24).toString('base64url');
}

/**
 * keys.json format (an array, or { "keys": [...] }):
 *
 *   {
 *     "name": "team-01",          // shown in logs and usage reports
 *     "key_hash": "<sha256 hex>", // preferred: store only the hash
 *     "key": "jvp_...",           // or: plain key (fine for local tests)
 *     "enabled": true,
 *     "rpm": 60,                  // requests per minute
 *     "daily_requests": 2000,     // requests per day (TIME_ZONE)
 *     "max_cost_usd": 1.0,        // lifetime spend cap for this key
 *     "expires_at": "2026-12-31T23:59:59+08:00"
 *   }
 */
export class KeyStore {
  constructor(file, defaults, { watch = true } = {}) {
    this.file = file;
    this.defaults = defaults;
    this.byHash = new Map();
    this.load();
    if (watch && fs.existsSync(file)) {
      fs.watchFile(file, { interval: 2000 }, () => {
        try {
          this.load();
          console.log(`[keys] reloaded ${this.byHash.size} key(s) from ${file}`);
        } catch (err) {
          console.error(`[keys] reload failed, keeping previous keys: ${err.message}`);
        }
      });
    }
  }

  load() {
    const next = new Map();
    if (fs.existsSync(this.file)) {
      const parsed = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      const list = Array.isArray(parsed) ? parsed : parsed.keys || [];
      for (const [i, entry] of list.entries()) {
        const hash = entry.key_hash || (entry.key ? hashKey(entry.key) : null);
        if (!hash) throw new Error(`keys[${i}] needs "key" or "key_hash"`);
        next.set(hash, this.normalize(entry, i));
      }
    }
    this.byHash = next;
  }

  normalize(entry, i) {
    return {
      name: entry.name || `key-${i + 1}`,
      enabled: entry.enabled !== false,
      rpm: entry.rpm ?? this.defaults.rpm,
      dailyRequests: entry.daily_requests ?? this.defaults.dailyRequests,
      maxCostUsd: entry.max_cost_usd ?? this.defaults.maxCostUsd,
      expiresAt: entry.expires_at ? Date.parse(entry.expires_at) : null,
    };
  }

  lookup(key) {
    if (!key) return null;
    return this.byHash.get(hashKey(key)) || null;
  }

  list() {
    return [...this.byHash.values()];
  }

  stop() {
    fs.unwatchFile(this.file);
  }
}
