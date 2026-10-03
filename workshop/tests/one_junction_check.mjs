// Headless check of level5-junction/one_junction.html.
//   node one_junction_check.mjs <folder with one_junction.html and runs/one_runs.js> [screenshot folder]
// Prints a JSON report. Exit 0 = ok, 1 = problem, 77 = Playwright not installed (skip).
import { execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require('playwright'));
} catch {
  try {
    ({ chromium } = require(path.join(execSync('npm root -g').toString().trim(), 'playwright')));
  } catch {
    console.log(JSON.stringify({ skipped: 'playwright not installed' }));
    process.exit(77);
  }
}

const [dir, shots] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(pathToFileURL(path.join(dir, 'one_junction.html')).href);
await page.waitForTimeout(200);

const report = { errors };
report.empty = await page.locator('.empty').count() > 0;
if (!report.empty) {
  report.runs = await page.locator('#run option').count();
  // keep a copy of the canvas inside the page; compare copies there (no big transfers)
  const pixels = (name) => page.evaluate((name) => {
    const c = document.getElementById('c');
    (window.__shots ||= {})[name] = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    return name;
  }, name);
  const diff = (a, b) => page.evaluate(([a, b]) => {
    const x = window.__shots[a], y = window.__shots[b];
    let d = 0;
    for (let i = 0; i < x.length; i += 4) d += Math.abs(x[i] - y[i]) + Math.abs(x[i + 1] - y[i + 1]) + Math.abs(x[i + 2] - y[i + 2]);
    return d / (x.length / 4);
  }, [a, b]);
  const at = async (t, u) => {
    await page.evaluate(([t, u]) => { window.viewer.go(t); window.viewer.setU(u); }, [t, u]);
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  };
  // no jump at the end of a tick: the last moment of tick t looks like the first moment of tick t+1
  report.boundary = []; report.within = [];
  for (let r = 0; r < report.runs; r++) {
    await page.selectOption('#run', String(r));
    const ticks = Number(await page.getAttribute('#scrub', 'max'));
    for (let t = 0; t < Math.min(ticks, 6); t++) {
      await at(t, 0.5); await pixels('mid');
      await at(t, 0.999); await pixels('end');
      await at(t + 1, 0); await pixels('start');
      report.boundary.push(+(await diff('end', 'start')).toFixed(2));
      report.within.push(+(await diff('mid', 'end')).toFixed(2));
    }
    for (let t = 0; t <= ticks; t++) await at(t, 0.6);  // every tick draws without errors
  }
  if (shots) {
    await page.selectOption('#run', String(report.runs - 1));
    for (const [t, u] of [[0, 0], [3, 0.3], [3, 0.6], [8, 0.5]]) {
      await at(t, u);
      await page.screenshot({ path: path.join(shots, `one-t${t}-u${u}.png`) });
    }
    await page.selectOption('#run', '0');
    for (let t = 0; t < 10; t++) {   // a tick with a crash, mid-animation
      await at(t, 0.55);
      if ((await page.locator('#log .crash').count()) > 0) { await page.screenshot({ path: path.join(shots, `one-crash.png`) }); break; }
    }
  }
  report.maxBoundary = Math.max(...report.boundary);
  report.meanWithin = +(report.within.reduce((a, b) => a + b, 0) / report.within.length).toFixed(2);
}
await browser.close();
// With no runs yet, the missing runs/one_runs.js is expected: that is how the page knows it is empty.
if (report.empty) report.errors = errors.filter((e) => !e.startsWith('Failed to load resource'));
console.log(JSON.stringify(report));
process.exit(report.errors.length ? 1 : 0);
