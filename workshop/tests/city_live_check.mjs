// Headless check of the live page served by city_server.py (JEV_MOCK=1): Jev is called, schedules
// are applied, the dashboard fills, the 3D view renders.   node city_live_check.mjs <url>
import { execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); } catch {
  try { ({ chromium } = require(path.join(execSync('npm root -g').toString().trim(), 'playwright'))); } catch {
    console.log(JSON.stringify({ skipped: 'playwright not installed' })); process.exit(77);
  }
}
const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(process.argv[2]);
await page.waitForFunction(() => +document.getElementById('jevCalls').textContent >= 2, null, { timeout: 60000 }).catch(() => {});
const report = await page.evaluate(() => ({
  view3d: !!(window.VIEW3D && window.VIEW3D.on),
  calls: +document.getElementById('jevCalls').textContent,
  cost: document.getElementById('jevCost').textContent,
  status: document.getElementById('jevStatus').textContent,
  modes: window.city.stats().junctions.map((j) => j.mode),
  costPath: document.querySelectorAll('#chCost path').length,
  latBars: document.querySelectorAll('#chLat path').length,
  picks: document.querySelectorAll('#chPicks .bar').length,
  decideState: window.city.decideState(7),
  tickN: +document.getElementById('tickN').textContent,
  decisions: [...document.querySelectorAll('#decisions li')].map((li) => ({
    tick: +li.querySelector('.n').textContent.slice(1), phases: li.querySelectorAll('.ph').length, error: !!li.querySelector('.err'),
    points: li.querySelector('.pts') ? +li.querySelector('.pts').textContent : null })),
  score: document.getElementById('jevScore').textContent,
}));
report.errors = errors;
await browser.close();
console.log(JSON.stringify(report));
process.exit(errors.length ? 1 : 0);
