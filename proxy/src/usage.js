import fs from 'node:fs';

/** Day string like "2026-10-01" in the given IANA time zone. */
export function dayKey(timeZone, date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
}

/**
 * Per-key counters: lifetime totals plus per-day buckets.
 * Persisted to a JSON file so quotas survive restarts.
 */
export class UsageStore {
  constructor(file, timeZone) {
    this.file = file;
    this.timeZone = timeZone;
    this.data = {};
    this.dirty = false;
    this.recent = new Map(); // name -> timestamps (ms) of requests in the last minute
    if (file && fs.existsSync(file)) {
      try {
        this.data = JSON.parse(fs.readFileSync(file, 'utf8'));
      } catch (err) {
        console.error(`[usage] could not read ${file}, starting fresh: ${err.message}`);
      }
    }
    if (file) {
      this.timer = setInterval(() => this.flush(), 5000);
      this.timer.unref();
    }
  }

  entry(name) {
    if (!this.data[name]) {
      this.data[name] = { requests: 0, errors: 0, input_tokens: 0, cost_usd: 0, days: {} };
    }
    return this.data[name];
  }

  today(name) {
    const e = this.entry(name);
    const d = dayKey(this.timeZone);
    if (!e.days[d]) e.days[d] = { requests: 0, input_tokens: 0, cost_usd: 0 };
    return e.days[d];
  }

  /** Sliding one-minute window. Returns seconds to wait, or 0 if allowed (and counts the hit). */
  hitRateLimit(name, rpm, now = Date.now()) {
    if (!rpm || rpm <= 0) return 0;
    const list = (this.recent.get(name) || []).filter((t) => now - t < 60_000);
    if (list.length >= rpm) {
      this.recent.set(name, list);
      return Math.max(1, Math.ceil((60_000 - (now - list[0])) / 1000));
    }
    list.push(now);
    this.recent.set(name, list);
    return 0;
  }

  record(name, { ok, inputTokens = 0, costUsd = 0 }) {
    const e = this.entry(name);
    const t = this.today(name);
    e.requests += 1;
    t.requests += 1;
    if (!ok) e.errors += 1;
    e.input_tokens += inputTokens;
    t.input_tokens += inputTokens;
    e.cost_usd = round(e.cost_usd + costUsd);
    t.cost_usd = round(t.cost_usd + costUsd);
    e.last_used_at = new Date().toISOString();
    this.dirty = true;
  }

  flush() {
    if (!this.file || !this.dirty) return;
    const tmp = `${this.file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this.data, null, 2));
    fs.renameSync(tmp, this.file);
    this.dirty = false;
  }

  stop() {
    clearInterval(this.timer);
    this.flush();
  }
}

function round(n) {
  return Math.round(n * 1e9) / 1e9;
}
