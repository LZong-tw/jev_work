// Headless check of level5-junction/city.html: it runs, nothing collides, the state API works.
//   node city_check.mjs <path to city.html> [screenshot folder]
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

const [file, shots] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
await page.goto(pathToFileURL(file).href + '?paused');
await page.waitForTimeout(200);

const report = { errors };
// 1200 simulated seconds with the smart lights, then 600 with fixed timers (1 s = 1 clock minute)
await page.evaluate(() => window.city.step(1200));
await page.evaluate(() => { for (let i = 0; i < 4; i++) window.city.setMode(i, 'fixed'); window.city.step(600); });
// a controller of your own: drive crossing 0 by hand through every phase
report.manual = await page.evaluate(() => {
  const seen = [];
  for (const ph of ['C', 'D', 'W', 'A', 'B']) {
    window.city.setPhase(0, ph);
    for (let t = 0; t < 120; t++) { window.city.step(1); const j = window.city.state().junctions[0]; if (j.phase === ph && (j.stage === 'green' || j.stage === 'walk')) { seen.push(ph); break; } }
  }
  return seen;
});
// a schedule from code (what Jev will set): only A and C, then a day plan
report.schedule = await page.evaluate(() => {
  window.city.setSchedule(1, [{ phase: 'A', seconds: 12 }, { phase: 'C', seconds: 8 }]);
  const seen = new Set();
  for (let t = 0; t < 200; t++) { window.city.step(1); const j = window.city.state().junctions[1]; if (j.stage === 'green' || j.stage === 'walk') seen.add(j.phase); }
  let bad = null;
  try { window.city.setSchedule(1, [{ phase: 'X', seconds: 5 }]); } catch (e) { bad = e.message; }
  window.city.setClock(6 * 60 + 50);
  window.city.setSchedule(2, { '00:00': [{ phase: 'A', seconds: 10 }], '07:00': [{ phase: 'W', seconds: 10 }, { phase: 'B', seconds: 5 }] });
  const before = window.city.getSchedule(2).now.map(e => e.phase).join('');
  window.city.step(20);
  const after = window.city.getSchedule(2).now.map(e => e.phase).join('');
  return { seen: [...seen].sort(), bad, before, after };
});
// a vehicle that goes crosses its crossing in exactly 1 tick, and it goes when a tick starts
report.crossing = await page.evaluate(() => {
  const open = new Map(), took = new Set(), startedAt = new Set();
  const already = new Set([...vehicles].filter((v) => v.conn).concat([...people].filter((p) => p.onZebra !== null)));   // not measured
  const walking = new Map(), walkTook = new Set(), walkStartedAt = new Set();
  let onZebraAtTickStart = 0;
  for (let n = 1; n <= 40 * TICK_STEPS; n++) {   // imperative-ok: 40 ticks, one simulation step at a time
    const at = tickStep;
    if (at === 0) onZebraAtTickStart += JUNCTIONS.reduce((a, j) => a + j.zebraPeds, 0);
    window.city.step(DT);
    vehicles.forEach((v) => {
      if (already.has(v)) return;
      if (v.conn && !open.has(v)) { open.set(v, n - 1); startedAt.add(at); }
      else if (!v.conn && open.has(v)) { took.add(n - open.get(v)); open.delete(v); }
    });
    people.forEach((p) => {                      // people on a zebra: the same, exactly 1 tick
      if (already.has(p)) return;
      if (p.onZebra !== null && !walking.has(p)) { walking.set(p, n - 1); walkStartedAt.add(at); }
      else if (p.onZebra === null && walking.has(p)) { walkTook.add(n - walking.get(p)); walking.delete(p); }
    });
  }
  return { tick: window.city.TICK, steps: TICK_STEPS, took: [...took], startedAt: [...startedAt],
           walkTook: [...walkTook], walkStartedAt: [...walkStartedAt], onZebraAtTickStart };
});
// the screen plays a recorded tick: the end of one tick on screen is exactly the start of the next
report.playback = await page.evaluate(() => {
  runTick(); const end = new Map(showAt(1).vehicles.map((s) => [s.v, s]));
  runTick(); const gaps = showAt(0).vehicles.filter((s) => end.has(s.v)).map((s) => Math.hypot(s.x - end.get(s.v).x, s.y - end.get(s.v).y));
  const mid = showAt(0.5);
  return { frames: tape.frames.length, compared: gaps.length, maxGap: Math.max(...gaps), midVehicles: mid.vehicles.length };
});
report.history = await page.evaluate(() => { const h = window.city.history(4); return { buckets: h.length, start: h[0].start, j0: h[h.length - 1].junctions[0] }; });
report.ticks = await page.evaluate(() => { let n = 0; const off = window.city.onSecond(() => n++); window.city.step(10); off(); return n; });
const st = await page.evaluate(() => window.city.state());
report.totals = st.totals;
report.clock = st.clock;
report.junction0 = { phase: st.junctions[0].phase, stage: st.junctions[0].stage, demand: st.junctions[0].demand,
                     approaches: Object.keys(st.junctions[0].approaches), lanes: Object.keys(st.junctions[0].approaches.north.lanes),
                     zebras: Object.keys(st.junctions[0].zebras) };
report.types = (await page.evaluate(() => window.city.stats())).types;
// the lanes and turns the lights let go are tinted (and the zebras while people walk): the lights on screen
report.greens = await page.evaluate(async () => {
  const frames = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const onScreen = async (stepFirst) => {
    if (stepFirst) window.city.step(DT);          // a step: the screen shows the lights as they are now
    await frames();
    return { lit: window.city.greens(), view3d: window.VIEW3D && window.VIEW3D.on ? window.VIEW3D.greens() : null };
  };
  ['A', 'B', 'C', 'W'].forEach((ph, id) => window.city.setLights(id, ph));
  const go = await onScreen(true);
  window.city.allRed(0); window.city.setLights(1, 'D'); JUNCTIONS[1].stage = 'yellow'; JUNCTIONS[3].stage = 'flash';
  const ending = await onScreen(true);
  window.city.setLights(2, 'A');                  // no step: the tick on screen still has the old lights
  const notYet = await onScreen(false);
  return { go, ending, notYet };
});
if (shots) {
  await page.evaluate(() => { window.city.setClock(8 * 60); window.city.step(30); });
  await page.screenshot({ path: path.join(shots, 'city.png') });
}
await browser.close();
console.log(JSON.stringify(report));
process.exit(errors.length || report.totals.collisions ? 1 : 0);
