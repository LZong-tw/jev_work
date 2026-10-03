// Headless check of a level simulator (Levels 1-4) served by its server.py (JEV_MOCK=1): the page runs,
// Jev is asked, the simulator fills, and the Jev editor checks and applies payloads.
//   node levels_web_check.mjs <level 1-4> <url>
// Prints a JSON report. Exit 0 = ok, 1 = page errors, 77 = Playwright not installed (skip).
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
const [level, url] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && !/status of 4\d\d/.test(m.text()) && errors.push(m.text()));   // 4xx: a refused input, on purpose
await page.goto(url, { timeout: 180000 });
const T = { timeout: 120000 };
const report = { level: +level };
// nothing on the page may show a leaked null / undefined / NaN, before or after it runs
const leaks = async () => (await page.evaluate(() => (document.querySelector('main') || document.querySelector('.sandbox')).innerText))
  .match(/\bnull\b|\bundefined\b|\bNaN\b/g) || [];
report.leaksBefore = await leaks();
const setText = (sel, value) => page.$eval(sel, (t, v) => { t.value = v; }, value);
const edErrors = () => page.$$eval('.ed-errors li', (l) => l.map((x) => x.textContent));
const editorRequest = async () => JSON.parse(await page.$eval('.editor textarea.req', (t) => t.value));

if (level === '1') {
  await page.click('.item:nth-child(1)');          // one card answered by hand, the others not yet: the line shows one dot
  await setText('.editor textarea.res', JSON.stringify({ answers: { happy: { noul: 0.98 } } }));
  await page.click('text=Apply response');
  report.oneDot = await page.$$eval('.strip .dot', (d) => d.length);
  report.leaksOneAnswered = await leaks();
  await page.click('#runAll');
  await page.waitForFunction(() => !document.querySelector('#runAll').disabled && document.querySelectorAll('.item .tag').length === 6, null, T);
  report.tags = await page.$$eval('.item .tag', (t) => t.map((x) => x.textContent));
  report.dots = await page.$$eval('.strip .dot', (d) => d.length);
  await page.$eval('#threshold', (e) => { e.value = 1; e.dispatchEvent(new Event('input')); });   // the line moves: no new call
  report.tagsAtThreshold1 = await page.$$eval('.item .tag', (t) => t.map((x) => x.textContent));
  await page.click('.item:nth-child(2)');
  const req = await editorRequest();
  report.request = req;
  await setText('.editor textarea.req', JSON.stringify({ ...req, questions: { happy: { type: 'choice', instructions: 'x', criteria: { a: null, b: null } } } }));
  await page.click('text=Send to Jev');
  report.wrongType = await edErrors();
  await setText('.editor textarea.req', JSON.stringify(req));
  await setText('.editor textarea.res', JSON.stringify({ answers: { happy: { type: 'noul', noul: 0.97 } } }));
  await page.$eval('#threshold', (e) => { e.value = 0.5; e.dispatchEvent(new Event('input')); });
  await page.click('text=Apply response');
  report.applied = await page.$eval('.item:nth-child(2)', (c) => [c.querySelector('.p').textContent, c.querySelector('.tag').textContent]);
  await setText('.editor textarea.res', '{"answers": {"happy": {"noul": 1.7}}}');
  await page.click('text=Apply response');
  report.outOfRange = await edErrors();
  await page.click('#tabs button[data-tab=spam]');
  await page.click('#runAll');
  await page.waitForFunction(() => !document.querySelector('#runAll').disabled && document.querySelectorAll('.item .tag').length === 6, null, T);
  report.spamScore = await page.$eval('#summary .big', (b) => b.textContent);
}
if (level === '2') {
  await page.click('#runAll');
  await page.waitForFunction(() => !document.querySelector('#runAll').disabled && document.querySelectorAll('.column .msg').length === 7, null, T);
  report.columns = await page.$$eval('.column', (cs) => cs.map((c) => c.querySelector('.col-h').firstChild.textContent));
  await page.$eval('#minConf', (e) => { e.value = 0; e.dispatchEvent(new Event('input')); });
  report.humanAt0 = await page.$eval('.column.human', (c) => c.querySelectorAll('.msg').length);
  await page.$eval('#minConf', (e) => { e.value = 1; e.dispatchEvent(new Event('input')); });
  report.humanAt1 = await page.$eval('.column.human', (c) => c.querySelectorAll('.msg').length);
  await page.$eval('#minConf', (e) => { e.value = 0.7; e.dispatchEvent(new Event('input')); });
  await page.click('.column .msg');
  // a hand-written answer moves the message into that box
  await setText('.editor textarea.res', JSON.stringify({ answers: { box: { choice: 'job', confidence: 0.95, probabilities: { job: 0.95, order: 0.05 } }, urgency: { score: 3 } } }));
  await page.click('text=Apply response');
  report.applied = await page.$$eval('.column', (cs) => Object.fromEntries(cs.map((c) => [c.querySelector('.col-h').firstChild.textContent, c.querySelectorAll('.msg').length])));
  report.detail = await page.$eval('#detail .col-h', (d) => d.firstChild.textContent);
  await setText('.editor textarea.res', JSON.stringify({ answers: { box: { choice: 'nope', confidence: 0.9 }, urgency: { score: 9 } } }));
  await page.click('text=Apply response');
  report.badAnswer = await edErrors();
  const req = await editorRequest();
  delete req.questions.urgency;
  await setText('.editor textarea.req', JSON.stringify(req));
  await page.click('text=Send to Jev');
  report.missingQuestion = await edErrors();
  // the portfolio tab: add a company, sort them all, move one by hand; the added one stays after a reload
  await page.click('#tabs button[data-tab=portfolio]');
  const p = {};
  p.todos = await page.$eval('#pSource', (s) => s.textContent.match(/TODO \d/g));
  await page.fill('#pName', 'Bubble Cloud');
  await page.fill('#pNotes', 'Rents cloud servers to tea shops.');
  await page.click('#pAdd button');
  p.count = await page.$eval('#pN', (n) => n.textContent);
  await page.click('#pRunAll');
  await page.waitForFunction(() => !document.querySelector('#pRunAll').disabled && document.querySelectorAll('#pBoard .msg').length === 6, null, T);
  p.sorted = await page.$$eval('#pBoard .msg', (m) => m.length);
  p.columns = await page.$$eval('#pBoard .column', (cs) => cs.map((c) => c.querySelector('.col-h').firstChild.textContent));
  await page.click('.stock:last-child');
  await setText('.editor textarea.res', JSON.stringify({ answers: { bucket: { choice: 'rocket', confidence: 0.95 } } }));
  await page.click('text=Apply response');
  p.applied = await page.$$eval('#pBoard .column', (cs) => cs.find((c) => c.querySelector('.col-h').firstChild.textContent === 'rocket').querySelector('.msg .text').textContent);
  p.leaks = (await page.$eval('main', (m) => m.innerText)).match(/\bnull\b|\bundefined\b|\bNaN\b/g) || [];
  await page.reload({ timeout: 180000 });
  await page.click('#tabs button[data-tab=portfolio]');
  p.afterReload = await page.$eval('#pN', (n) => n.textContent);
  report.portfolio = p;
}
if (level === '3') {
  await page.click('#runAll');
  await page.waitForFunction(() => !document.querySelector('#runAll').disabled && document.querySelectorAll('.lane .card').length === 5, null, T);
  report.lanes = await page.$$eval('.lane', (ls) => Object.fromEntries(ls.map((l) => [l.classList[1], l.querySelectorAll('.card').length])));
  // red team: hand-written answers go through YOUR gate()
  await page.click('.call:nth-child(1)');
  await setText('.editor textarea.res', JSON.stringify({ answers: { risk: { score: 0.2 }, kind: { choice: 'read_only', confidence: 0.9 }, on_goal: { noul: 0.9 }, tricked: { noul: 0.95 } } }));
  await page.click('text=Apply response');
  await page.waitForFunction(() => document.querySelector('.verdict') && document.querySelector('.verdict').textContent === 'BLOCK', null, T);
  report.redTeam = await page.$eval('.verdict', (v) => v.parentElement.textContent);
  await setText('.editor textarea.res', JSON.stringify({ answers: { risk: { score: 0.2 }, kind: { choice: 'read_only', confidence: 0.9 }, on_goal: { noul: 0.9 }, tricked: { noul: 0.02 } } }));
  await page.click('text=Apply response');
  await page.waitForFunction(() => document.querySelector('.verdict') && document.querySelector('.verdict').textContent === 'ALLOW', null, T);
  report.allowed = await page.$eval('.verdict', (v) => v.textContent);
  // the console tab: any command, YOUR guard; a hand-written answer blocks; a broken file is not saved
  await page.click('#tabs button[data-tab=console]');
  const c = {};
  c.highlighted = await page.$$eval('#cCode .ce-hl span', (s) => s.length);
  await page.fill('#cCmd', 'cat menu.txt'); await page.press('#cCmd', 'Enter');
  await page.waitForFunction(() => document.querySelector('.entry .verdict-chip'), null, T);
  c.first = await page.$eval('.entry', (e) => e.innerText.replace(/\s+/g, ' '));
  await page.click('.entry');
  await setText('.editor textarea.res', JSON.stringify({ answers: { dangerous: { noul: 0.97 } } }));
  await page.click('text=Apply response');
  await page.waitForFunction(() => document.querySelector('.entry .v-BLOCK'), null, T);
  c.blocked = await page.$eval('.entry', (e) => e.innerText.replace(/\s+/g, ' '));
  await setText('.editor textarea.res', JSON.stringify({ answers: { dangerous: { noul: 0.02 } } }));
  await page.click('text=Apply response');
  await page.waitForFunction(() => document.querySelector('.entry .v-RUN'), null, T);
  c.ran = await page.$eval('.entry', (e) => e.innerText.replace(/\s+/g, ' '));
  await page.$eval('#cCode textarea', (t) => { t.value = t.value + '\ndef broken(:\n'; t.dispatchEvent(new Event('input')); });
  await page.click('#cCode button.primary');
  await page.waitForFunction(() => /not saved: line/.test(document.querySelector('#cCode .cp-head span').textContent), null, T);
  c.syntaxError = await page.$eval('#cCode .cp-head span', (s) => s.textContent);
  c.errorLineMarked = await page.$$eval('#cCode .ce-gutter .bad', (b) => b.length);
  await page.click('#cWave');                    // the exam: ten commands, a score
  await page.waitForFunction(() => !document.querySelector('#cWave').disabled && document.querySelectorAll('#cScreen .entry .want').length === 10, null, T);
  c.exam = await page.$eval('#cHud .score .big', (b) => b.textContent);
  report.console = c;
}
if (level === '4') {
  report.start = await page.$eval('#tiles', (t) => t.textContent);
  await page.selectOption('#speed', '500');
  await page.selectOption('#manager', 'rules');
  await page.click('#newDay');
  await page.waitForFunction(() => /Round 1/.test(document.querySelector('#decTitle').textContent), null, T);
  await page.click('#play');
  await page.waitForFunction(() => /End of day/.test(document.querySelector('#decTitle').textContent), null, T);
  report.rulesDay = await page.$$eval('#days tr', (r) => r.slice(1).map((x) => [...x.children].map((c) => c.textContent)));
  report.rows = await page.$$eval('#log tr', (r) => r.length - 1);
  await page.selectOption('#manager', 'jev');
  await page.click('#newDay');
  await page.waitForFunction(() => /Round 1/.test(document.querySelector('#decTitle').textContent), null, T);
  await page.click('#next');
  await page.waitForFunction(() => document.querySelectorAll('#log tr').length === 2, null, T);
  report.jevRow = await page.$eval('#log tr:nth-child(2)', (r) => [...r.children].map((c) => c.textContent));
  // your own answer decides the round
  await setText('.editor textarea.res', JSON.stringify({ answers: { action: { choice: 'rest', confidence: 1, probabilities: { rest: 1 } } } }));
  await page.click('text=Apply response');
  await page.click('#next');
  await page.waitForFunction(() => document.querySelectorAll('#log tr').length === 3, null, T);
  report.appliedRow = await page.$eval('#log tr:nth-child(2)', (r) => [...r.children].map((c) => c.textContent));
  const req = await editorRequest();
  req.questions.action.criteria.dance = 'dance for the customers';
  await setText('.editor textarea.req', JSON.stringify(req));
  await page.click('text=Send to Jev');
  report.unknownAction = await edErrors();
  await page.selectOption('#manager', 'you');
  await page.click('#newDay');
  await page.waitForSelector('.you button', T);
  await page.click('.you button:nth-child(2)');
  await page.waitForFunction(() => document.querySelectorAll('#log tr').length === 2, null, T);
  report.youRow = await page.$eval('#log tr:nth-child(2)', (r) => [...r.children].map((c) => c.textContent));
  report.fsmNodes = await page.$$eval('.fsm .node', (n) => n.length);
}
if (level === '5') {   // the sandbox
  await page.click('#send5');
  await page.waitForFunction(() => document.querySelectorAll('#answers .ans').length === 3 && !document.querySelector('#send5').disabled, null, T);
  report.widgets = await page.$$eval('#answers .ans', (a) => a.map((x) => [x.querySelector('.gauge') ? 'noul' : x.querySelector('.bars') ? 'choice' : 'score', x.querySelectorAll('.spread span').length]));
  await page.selectOption('#tpl', '2');
  report.tree = await page.$$eval('#tree details', (d) => d.length);
  await page.selectOption('#tpl', '3');
  await page.click('#addChoice');
  report.problems = await page.$$eval('#errs li', (l) => l.map((x) => x.textContent));
  await page.fill('#state', 'Our new tea tastes like grass.');
  await page.$eval('.q textarea', (t) => { t.value = 'Is this feedback about the taste?'; t.dispatchEvent(new Event('input')); });
  const inputs = await page.$$('.q .item input');
  await inputs[0].fill('taste'); await inputs[2].fill('price');
  report.problemsAfter = await page.$$eval('#errs li', (l) => l.map((x) => x.textContent));
  await page.click('#send');
  await page.waitForFunction(() => document.querySelectorAll('#answers .ans').length === 1, null, T);
  report.req = JSON.parse(await page.$eval('#reqJson', (t) => t.value));
  await setText('#reqJson', JSON.stringify({ state: { order: 8812 }, questions: { late: { type: 'noul', instructions: 'Is it late?' }, mood: { type: 'score', instructions: 'Mood?', criteria: ['bad', 'ok', 'great'] } } }));
  await page.click('#load');
  report.loaded = await page.$$eval('.q .kind', (k) => k.map((x) => x.textContent));
  report.history = await page.$$eval('#history button', (b) => b.length);
}
report.meter = await page.$eval('#meter', (m) => m.textContent);
report.leaksAfter = await leaks();
report.errors = errors;
await browser.close();
console.log(JSON.stringify(report));
process.exit(errors.length ? 1 : 0);
