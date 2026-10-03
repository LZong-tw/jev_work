#!/usr/bin/env node
// Create proxy keys for participants.
//
//   npm run keys -- --count 30 --prefix team --max-cost 0.50 --expires 2026-10-02 \
//                   --base-url https://jev-proxy.example.com/api
//
// keys.json gets only the SHA-256 hashes. The plain keys are written ONCE to
// keys-handout.csv and keys-handout.html (printable cards). Keep those safe.
import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { generateKey, hashKey } from '../src/keys.js';

const { values: args } = parseArgs({
  options: {
    count: { type: 'string', default: '1' },
    prefix: { type: 'string', default: 'user' },
    rpm: { type: 'string' },
    daily: { type: 'string' },
    'max-cost': { type: 'string' },
    expires: { type: 'string' },
    out: { type: 'string', default: 'keys.json' },
    handout: { type: 'string', default: 'keys-handout' },
    'base-url': { type: 'string', default: 'http://localhost:8787' },
    help: { type: 'boolean', short: 'h' },
  },
});

if (args.help) {
  console.log(`Usage: node scripts/create-keys.js [options]
  --count N          how many keys (default 1)
  --prefix NAME      name prefix, e.g. team -> team-01, team-02 (default user)
  --rpm N            requests per minute per key
  --daily N          requests per day per key
  --max-cost USD     lifetime spend cap per key
  --expires DATE     ISO date/time when keys stop working
  --out FILE         keys file to append to (default keys.json)
  --handout NAME     base name for the .csv/.html handout (default keys-handout)
  --base-url URL     proxy base URL printed on the handout`);
  process.exit(0);
}

const count = Number(args.count);
if (!Number.isInteger(count) || count < 1) {
  console.error('--count must be a positive integer');
  process.exit(1);
}

const outFile = path.resolve(args.out);
const existing = fs.existsSync(outFile) ? JSON.parse(fs.readFileSync(outFile, 'utf8')) : [];
const list = Array.isArray(existing) ? existing : existing.keys || [];
const names = new Set(list.map((k) => k.name));

const width = String(list.length + count).length < 2 ? 2 : String(list.length + count).length;
const created = [];
let n = 1;
while (created.length < count) {
  const name = `${args.prefix}-${String(n).padStart(width, '0')}`;
  n += 1;
  if (names.has(name)) continue;
  const key = generateKey();
  const entry = { name, key_hash: hashKey(key), enabled: true, created_at: new Date().toISOString() };
  if (args.rpm) entry.rpm = Number(args.rpm);
  if (args.daily) entry.daily_requests = Number(args.daily);
  if (args['max-cost']) entry.max_cost_usd = Number(args['max-cost']);
  if (args.expires) entry.expires_at = new Date(args.expires).toISOString();
  list.push(entry);
  names.add(name);
  created.push({ name, key });
}

fs.writeFileSync(outFile, JSON.stringify(list, null, 2) + '\n');

const csv = ['name,api_key,base_url', ...created.map((c) => `${c.name},${c.key},${args['base-url']}`)].join('\n') + '\n';
fs.writeFileSync(`${args.handout}.csv`, csv);

const esc = (s) => s.replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch]);
const cards = created
  .map(
    (c) => `<div class="card"><div class="name">${esc(c.name)}</div>
<div class="label">JEV_BASE_URL</div><code>${esc(args['base-url'])}</code>
<div class="label">JEV_API_KEY</div><code>${esc(c.key)}</code></div>`,
  )
  .join('\n');
fs.writeFileSync(
  `${args.handout}.html`,
  `<!doctype html><meta charset="utf-8"><title>Jev workshop keys</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.card{border:1px dashed #888;border-radius:8px;padding:12px;break-inside:avoid}
.name{font-weight:700;font-size:18px;margin-bottom:6px}
.label{font-size:11px;color:#555;margin-top:6px;letter-spacing:.05em}
code{font:13px ui-monospace,monospace;word-break:break-all}
</style>
<div class="grid">
${cards}
</div>
`,
);

console.log(`Added ${created.length} key(s) to ${outFile} (hashes only).`);
console.log(`Plain keys: ${args.handout}.csv and ${args.handout}.html. Hand them out, then keep them private.`);
