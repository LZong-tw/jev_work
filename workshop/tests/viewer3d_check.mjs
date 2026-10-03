// Headless check of level5-junction/viewer3d.html (Three.js, WebGL in software).
//   node viewer3d_check.mjs <folder with viewer3d.html, vendor/ and runs/runs.js>
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

const dir = process.argv[2];
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1300, height: 850 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(pathToFileURL(path.join(dir, 'viewer3d.html')).href);
await page.waitForTimeout(800);

const report = { errors };
report.empty = await page.locator('.empty').count() > 0;
if (!report.empty) {
  report.webgl = await page.locator('#scene canvas').count();
  report.runs = await page.locator('#run option').count();
  report.ticks = Number(await page.getAttribute('#tick', 'max')) + 1;
  report.junctions = await page.locator('#decisions .j').count();
  // junction labels are projected from 3D onto the screen
  report.labelsOnScreen = await page.evaluate(() => [...document.querySelectorAll('.label:not(.out)')].filter((el) => {
    const x = parseFloat(el.style.left), y = parseFloat(el.style.top);
    return el.style.display !== 'none' && x > 0 && x < innerWidth && y > 0 && y < innerHeight && el.textContent.trim();
  }).length);
  report.debug = await page.evaluate(() => window.cityDebug);
  await page.click('#decisions .j');           // fly to an officer
  await page.waitForTimeout(1100);
  await page.click('#overview');
  await page.waitForTimeout(300);
  await page.selectOption('#speed', '300');
  await page.click('#play');
  await page.waitForTimeout(1200);
  await page.click('#play');
  report.tickAfterPlay = Number(await page.inputValue('#tick'));
  report.texts = new Set();
  for (let r = 0; r < report.runs; r++) {
    await page.selectOption('#run', String(r));
    for (let t = 0; t < report.ticks; t += 3) {
      await page.fill('#tick', String(t));
      await page.dispatchEvent('#tick', 'input');
      await page.waitForTimeout(20);
      for (const txt of await page.locator('#decisions .muted').allTextContents()) report.texts.add(txt.split(' (')[0]);
    }
  }
  report.texts = [...report.texts];
}
await browser.close();
if (report.empty) report.errors = errors.filter((e) => !e.startsWith('Failed to load resource'));
console.log(JSON.stringify(report));
process.exit(report.errors.length ? 1 : 0);
