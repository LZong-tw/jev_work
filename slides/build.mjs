// Build the slide PDF (and optional PNG previews) from slides.html.
//   node build.mjs            -> jev-workshop-slides.pdf
//   node build.mjs --png      -> also preview/slide-XX.png
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require('playwright'));
} catch {
  // fall back to a global install
  const globalRoot = (await import('node:child_process')).execSync('npm root -g').toString().trim();
  ({ chromium } = require(path.join(globalRoot, 'playwright')));
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
page.on('pageerror', (e) => console.error('page error:', e.message));
await page.goto(pathToFileURL(path.join(here, 'slides.html')).href, { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);

const out = path.join(here, 'jev-workshop-slides.pdf');
await page.pdf({ path: out, width: '1280px', height: '720px', printBackground: true, preferCSSPageSize: true });
console.log('wrote', out);

if (process.argv.includes('--png')) {
  const dir = path.join(here, 'preview');
  fs.mkdirSync(dir, { recursive: true });
  const slides = await page.$$('.slide');
  await page.addStyleTag({ content: '.slide{margin:0!important;box-shadow:none!important}' });
  for (const [i, s] of slides.entries()) {
    await s.screenshot({ path: path.join(dir, `slide-${String(i + 1).padStart(2, '0')}.png`) });
  }
  console.log(`wrote ${slides.length} previews to ${dir}`);
}
await browser.close();
