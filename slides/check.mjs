// Layout check for slides.html: every slide renders, nothing is cut off.
//   node check.mjs
// Exit 0 = ok, 1 = problems found (listed), 77 = Playwright not installed (skip).
import { execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require('playwright'));
} catch {
  try {
    ({ chromium } = require(path.join(execSync('npm root -g').toString().trim(), 'playwright')));
  } catch {
    console.log('skipped: playwright not installed');
    process.exit(77);
  }
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const problems = [];
page.on('pageerror', (e) => problems.push(`page error: ${e.message}`));
page.on('requestfailed', (r) => problems.push(`failed to load: ${r.url()}`));
await page.goto(pathToFileURL(path.join(here, 'slides.html')).href, { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);

const result = await page.evaluate(() => {
  const out = { slides: 0, issues: [], fonts: [...document.fonts].filter((f) => f.status === 'loaded').length };
  const slides = [...document.querySelectorAll('.slide')];
  out.slides = slides.length;
  slides.forEach((slide, i) => {
    const n = i + 1;
    const title = (slide.querySelector('h1, h2')?.textContent || '').trim().slice(0, 40);
    const box = slide.getBoundingClientRect();
    if (Math.round(box.width) !== 1280 || Math.round(box.height) !== 720) out.issues.push(`slide ${n}: size ${box.width}x${box.height}`);
    // code blocks: nothing hidden on the right or bottom
    slide.querySelectorAll('pre.code').forEach((pre) => {
      if (pre.scrollWidth > pre.clientWidth + 1) out.issues.push(`slide ${n} "${title}": code cut off on the right`);
      if (pre.scrollHeight > pre.clientHeight + 1) out.issues.push(`slide ${n} "${title}": code cut off at the bottom`);
    });
    // content stays inside the slide (above the footer)
    const limit = box.bottom - 50;
    slide.querySelectorAll('.body > *, .body .card, .body table, .body img, .body pre').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.height && r.bottom > limit + 1) out.issues.push(`slide ${n} "${title}": ${el.tagName.toLowerCase()} runs into the footer`);
      if (r.width && r.right > box.right - 40) out.issues.push(`slide ${n} "${title}": ${el.tagName.toLowerCase()} runs off the right edge`);
    });
    slide.querySelectorAll('img').forEach((img) => {
      if (!img.complete || img.naturalWidth === 0) out.issues.push(`slide ${n}: image not loaded (${img.getAttribute('src')})`);
    });
    // page numbers are right
    const footer = slide.querySelector('.footer span:last-child');
    if (footer && !footer.textContent.startsWith(`${n} / `)) out.issues.push(`slide ${n}: footer says ${footer.textContent}`);
  });
  return out;
});
await browser.close();

problems.push(...result.issues);
if (result.fonts < 5) problems.push(`only ${result.fonts} of 5 fonts loaded`);
console.log(`${result.slides} slides, ${result.fonts} fonts loaded, ${problems.length} problem(s)`);
for (const p of problems) console.log(`  - ${p}`);
process.exit(problems.length ? 1 : 0);
