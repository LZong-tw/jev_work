// Headless check of level5-junction/viewer.html.
//   node viewer_check.mjs <folder with viewer.html and runs/runs.js>
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
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1300, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(pathToFileURL(path.join(dir, 'viewer.html')).href);

const report = { errors };
report.empty = await page.locator('.empty').count() > 0;
if (!report.empty) {
  report.runs = await page.locator('#runSel option').count();
  report.ticks = Number(await page.getAttribute('#tick', 'max')) + 1;
  // the canvas is drawn (not a blank image)
  report.canvasColors = await page.evaluate(() => {
    const c = document.getElementById('cv').getContext('2d').getImageData(0, 0, 760, 760).data;
    const seen = new Set();
    for (let i = 0; i < c.length; i += 4 * 97) seen.add(`${c[i]},${c[i + 1]},${c[i + 2]}`);
    return seen.size;
  });
  // playing moves the slider forward
  await page.selectOption('#speed', '100');
  await page.click('#play');
  await page.waitForTimeout(450);
  await page.click('#play');
  report.tickAfterPlay = Number(await page.inputValue('#tick'));
  // scrub through every tick of every run: no errors, collect the tags shown
  report.tags = new Set();
  for (let r = 0; r < report.runs; r++) {
    await page.selectOption('#runSel', String(r));
    for (let t = 0; t < report.ticks; t++) {
      await page.fill('#tick', String(t));
      await page.dispatchEvent('#tick', 'input');
      for (const tag of await page.locator('#decisions .tag').allTextContents()) report.tags.add(tag.split(' (')[0].split(':')[0]);
    }
  }
  report.tags = [...report.tags];
  report.junctions = await page.locator('#decisions .junction').count();
  report.bars = await page.locator('#decisions .bar').count();
  report.curveBars = await page.locator('#curve rect').count();
  report.parts = await page.locator('#parts span').count();
  report.weather = await page.textContent('#sWeather');
  report.score = await page.textContent('#sScore');
}
await browser.close();
// With no runs yet, the missing runs/runs.js is expected: that is how the page knows it is empty.
if (report.empty) report.errors = errors.filter((e) => !e.startsWith('Failed to load resource'));
console.log(JSON.stringify(report));
process.exit(report.errors.length ? 1 : 0);
