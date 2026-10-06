const location={search:process.env.SEEDQ||""};
"use strict";
// =============================================================================================
// Four Crossings: a small city with 4 signalised crossings, zebras, cars, taxis, buses,
// scooters, bikes and people. Traffic drives on the right (like Taipei).
// The lights are controlled per crossing: Fixed timer, Smart (reacts to queues) or Manual.
// Safety is in code: yellow, all-red, and a crossing only turns green when it is empty.
// =============================================================================================
function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const params = new URLSearchParams(location.search);
const SEED = +(params.get("seed") || 7);
const rnd = mulberry32(SEED);          // traffic and people
const lrnd = mulberry32(SEED * 31 + 5); // buildings and trees
const pick = (arr, r = rnd) => arr[Math.floor(r() * arr.length)];

// ----- the map, in metres -----------------------------------------------------------------
const W = 400, H = 300;
const XS = [133, 267], YS = [100, 200];
const AVENUES = ["Fuxing S. Rd", "Dunhua S. Rd"], STREETS = ["Zhongxiao E. Rd", "Ren'ai Rd"];
const LANE = 3.2, MED = 0.3, BIKE = 1.8, WALK = 3.2;
const OFF = { L: MED + LANE / 2, S: MED + LANE * 1.5, B: MED + LANE * 2 + BIKE / 2 }; // right of the centre line
const HW = MED + 2 * LANE + BIKE;      // half road width, 8.5 m
const ZEB = [HW + 0.8, HW + 3.8];      // the zebra band, from the junction centre
const STOP = HW + 4.6;                 // stop line = edge of the crossing box
const PO = (ZEB[0] + ZEB[1]) / 2;      // where people stand / walk across
const DIRS = { N: [0, -1], S: [0, 1], E: [1, 0], W: [-1, 0] };
const rightOf = d => [-d[1], d[0]];
const TURN = { N: { S: "N", R: "E", L: "W" }, S: { S: "S", R: "W", L: "E" }, E: { S: "E", R: "S", L: "N" }, W: { S: "W", R: "N", L: "S" } };
const add = (p, d, k) => [p[0] + d[0] * k, p[1] + d[1] * k];
const fmtClock = m => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(Math.floor(m % 60)).padStart(2, "0")}`;

// ----- crossings and their lights ----------------------------------------------------------
const PHASES = {
  A: { heads: "NS", moves: "SR", label: "N–S straight + right" },
  B: { heads: "NS", moves: "L", label: "N–S left turn" },
  C: { heads: "EW", moves: "SR", label: "E–W straight + right" },
  D: { heads: "EW", moves: "L", label: "E–W left turn" },
  W: { heads: "", moves: "", label: "everyone walks" },
};
const ORDER = ["A", "B", "C", "D", "W"];
const FIXED = { A: 18, B: 7, C: 18, D: 7, W: 12 };
const YELLOW = 3, ALLRED = 1.5, FLASH = 5;
const JUNCTIONS = [];
YS.forEach((y, r) => XS.forEach((x, c) => JUNCTIONS.push({
  id: JUNCTIONS.length, x, y, r, c, name: `${AVENUES[c].split(" ")[0]} × ${STREETS[r].split(" ")[0]}`,
  mode: "smart", phase: "A", stage: "green", t: 0, serial: 1, request: null,
  box: new Set(), zebraPeds: 0,
})));
const J_AT = (x, y) => JUNCTIONS.find(j => j.x === x && j.y === y).id;

// ----- road segments: one per direction between two crossings (or the map edge) -------------
const SEGS = [];
function addLine(horizontal, c, stops) {
  const lo = -25, hi = (horizontal ? W : H) + 25;
  for (const head of horizontal ? ["E", "W"] : ["S", "N"]) {
    const sg = head === "E" || head === "S" ? 1 : -1;
    const pts = sg > 0 ? [lo, ...stops, hi] : [hi, ...[...stops].reverse(), lo];
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1];
      const from = i > 0 ? (horizontal ? J_AT(a, c) : J_AT(c, a)) : null;
      const to = i < pts.length - 2 ? (horizontal ? J_AT(b, c) : J_AT(c, b)) : null;
      const s0 = a + (from !== null ? sg * STOP : 0), s1 = b - (to !== null ? sg * STOP : 0);
      SEGS.push({ id: SEGS.length, head, start: horizontal ? [s0, c] : [c, s0], len: Math.abs(s1 - s0), from, to,
                  lanes: { L: [], S: [], B: [] }, connQ: { L: [], S: [], B: [] }, backlog: [] });
    }
  }
}
YS.forEach(y => addLine(true, y, XS));
XS.forEach(x => addLine(false, x, YS));
const outSeg = (j, head) => SEGS.find(s => s.from === j && s.head === head);
const inSeg = (j, head) => SEGS.find(s => s.to === j && s.head === head);
const ENTRIES = SEGS.filter(s => s.from === null);
function lanePoint(seg, s, lane) { const d = DIRS[seg.head]; return add(add(seg.start, d, s), rightOf(d), OFF[lane]); }

// paths through a crossing (cubic curves for turns), cached
const PATHS = new Map();
function pathFor(a, laneA, b, laneB) {
  const key = `${a.id}${laneA}>${b.id}${laneB}`;
  if (PATHS.has(key)) return PATHS.get(key);
  const p0 = lanePoint(a, a.len, laneA), p3 = lanePoint(b, 0, laneB), d0 = DIRS[a.head], d3 = DIRS[b.head];
  let pts;
  if (a.head === b.head) pts = [p0, p3];
  else {
    // a quarter ellipse: it bulges away from the corner, so opposite left turns pass each other
    const dx = p3[0] - p0[0], dy = p3[1] - p0[1];
    const k0 = 0.552 * Math.abs(dx * d0[0] + dy * d0[1]), k3 = 0.552 * Math.abs(dx * d3[0] + dy * d3[1]);
    const p1 = add(p0, d0, k0), p2 = add(p3, d3, -k3);
    pts = [];
    for (let i = 0; i <= 20; i++) {
      const t = i / 20, u = 1 - t;
      pts.push([u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]]);
    }
  }
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const path = { pts, cum, len: cum[cum.length - 1] };
  PATHS.set(key, path);
  return path;
}
function along(path, s) {
  s = Math.max(0, Math.min(path.len, s));
  let i = 1;
  while (i < path.cum.length - 1 && path.cum[i] < s) i++;
  const a = path.pts[i - 1], b = path.pts[i], f = (s - path.cum[i - 1]) / ((path.cum[i] - path.cum[i - 1]) || 1);
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, Math.atan2(b[1] - a[1], b[0] - a[0])];
}

// ----- vehicles ------------------------------------------------------------------------------
const TYPES = {
  car:     { len: 4.5, w: 1.9, v0: 13.9, a: 1.7, b: 2.6, bike: false, share: 0.44 },
  taxi:    { len: 4.6, w: 1.9, v0: 14.5, a: 1.9, b: 2.8, bike: false, share: 0.11 },
  bus:     { len: 11.5, w: 2.5, v0: 11.0, a: 1.0, b: 2.0, bike: false, share: 0.05 },
  scooter: { len: 1.9, w: 0.8, v0: 12.0, a: 2.2, b: 3.0, bike: true, share: 0.27 },
  bike:    { len: 1.8, w: 0.7, v0: 5.0, a: 1.0, b: 2.0, bike: true, share: 0.13 },
};
const CAR_COLORS = ["#d8dee6", "#e9ecef", "#1f2329", "#9aa4af", "#b3262e", "#2d5fa8", "#5b6770", "#e1e5ea", "#7a1f2b", "#3f6f50"];
const SHIRTS = ["#f4a6c1", "#6ec1e4", "#ffd166", "#ef476f", "#06d6a0", "#ffffff", "#c3a6ff", "#ff9f68", "#8ecae6"];
let nextId = 1;
const vehicles = new Set();
function randomType() {
  let r = rnd();
  for (const [k, t] of Object.entries(TYPES)) { if ((r -= t.share) < 0) return k; }
  return "car";
}
function randomMove(bike) { const r = rnd(); return bike ? (r < 0.78 ? "S" : "R") : (r < 0.2 ? "L" : r < 0.8 ? "S" : "R"); }
function laneFor(v, seg) { return v.spec.bike ? "B" : seg.to === null ? (v.id % 2 ? "L" : "S") : (v.move === "L" ? "L" : "S"); }

function makeVehicle(type) {
  const spec = TYPES[type];
  return { id: nextId++, type, spec, len: spec.len, v: 0, s: 0, seg: null, lane: null, move: null, conn: null,
           plan: null, wait: 0, acc: 0, color: type === "car" ? pick(CAR_COLORS) : null, rider: pick(SHIRTS),
           bus: 200 + Math.floor(rnd() * 99), boxJ: null, waitHere: 0 };
}
function placeOn(v, seg, s) {
  v.seg = seg; v.s = s;
  v.move = seg.to === null ? null : randomMove(v.spec.bike);
  v.lane = laneFor(v, seg);
  const lane = seg.lanes[v.lane];
  let i = lane.length;
  while (i > 0 && lane[i - 1].s < s) i--;
  lane.splice(i, 0, v);
}

// ----- signals ---------------------------------------------------------------------------------
function signalFor(j, head, move) {
  const p = PHASES[j.phase];
  if (!p.heads.includes(head) || !p.moves.includes(move)) return "R";
  return j.stage === "green" ? "G" : j.stage === "yellow" ? "Y" : "R";
}
// The room at the start of a lane when a vehicle that goes now gets there: at the end of the tick. By then the
// last vehicle in it has driven on at its speed, but not into the vehicle ahead of it (nor past the stop line).
function tailRoom(seg, lane) {
  const l = seg.lanes[lane], tail = l[l.length - 1], lead = l[l.length - 2];
  const ahead = !tail ? 0 : lead ? lead.s - lead.len - 2 - tail.s : seg.to === null ? Infinity : seg.len - tail.s;
  const onward = tail ? Math.max(0, Math.min(tail.v * TICK, ahead)) : 0;
  const coming = [...vehicles].filter(v => v.conn && v.conn.out === seg && v.conn.outLane === lane);
  return (tail ? tail.s - tail.len + onward : seg.len) - coming.reduce((a, v) => a + v.len + 2.5, 0);
}
function planFor(v) {
  if (v.plan) return v.plan;
  const j = v.seg.to, out = outSeg(j, TURN[v.seg.head][v.move]);
  const nextMove = out.to === null ? null : randomMove(v.spec.bike);
  const outLane = v.spec.bike ? "B" : out.to === null ? (v.id % 2 ? "L" : "S") : (nextMove === "L" ? "L" : "S");
  return (v.plan = { out, outLane, nextMove, path: pathFor(v.seg, v.lane, out, outLane) });
}
function mayGo(v) {
  const j = JUNCTIONS[v.seg.to];
  if (signalFor(j, v.seg.head, v.move) !== "G") return false;        // a tick across starts only on green
  // room for it after the crossing, and to stop there (braking hard, 9 m/s²) from the speed it comes out at
  const plan = planFor(v), out = crossProfile(v.v, plan.path.len + v.len + 0.5 - (v.s - v.seg.len), cruiseOf(v)).vc;
  const fits = lane => tailRoom(plan.out, lane) >= v.len + 2.5 + out * out / 18;
  if (!fits(plan.outLane)) {                                           // never block the crossing, but: a car going straight
    const other = v.spec.bike || v.move !== "S" ? null : plan.outLane === "L" ? "S" : plan.out.to === null ? "L" : null;
    if (!other || !fits(other)) return false;                          // whose lane ahead is full takes the other lane (and
    Object.assign(plan, { outLane: other, nextMove: plan.out.to === null ? null : "S", path: pathFor(v.seg, v.lane, plan.out, other) });
  }                                                                    // goes straight on there, not left)
  // drivers wait while cross traffic or people are still in the crossing (after the lights changed)
  if (j.zebraPeds > 0) return false;
  for (const o of j.box) if (o.conn && o !== v && signalFor(j, o.conn.from.head, o.move) !== "G") return false;
  const seg = v.seg;
  if (!v.spec.bike && v.move === "R") {   // right turns give way to bikes, once: the next tick the bikes wait for it
    const crossing = seg.connQ.B.some(b => b.conn.path.len - b.conn.s > 3), waiting = seg.lanes.B.some(b => b.s > seg.len - 14);
    if (crossing || (waiting && !v.gaveWay)) { v.gaveWay = v.gaveWay || waiting || crossing; return false; }
  }
  if (v.spec.bike && seg.connQ.S.some(c => c.move === "R")) return false;   // a car turning right is crossing the bike lane
  return true;
}

// ----- the light controllers ----------------------------------------------------------------
function demand(j, phase) {
  if (phase === "W") return peopleWaiting(j);
  const p = PHASES[phase];
  let n = 0;
  for (const h of p.heads) {
    const seg = inSeg(j.id, h);
    for (const lane of ["L", "S", "B"]) for (const v of seg.lanes[lane])
      if (p.moves.includes(v.move) && seg.len - v.s < 70) n++;
  }
  return n;
}
function greenNear(j) {
  const p = PHASES[j.phase];
  let n = 0;
  for (const h of p.heads) {
    const seg = inSeg(j.id, h);
    for (const lane of ["L", "S", "B"]) for (const v of seg.lanes[lane])
      if (p.moves.includes(v.move) && seg.len - v.s < 30) n++;
  }
  return n;
}
function peopleWaiting(j) { let n = 0; for (const p of people) if (p.waitJ === j.id) n++; return n; }
// A schedule is a list of {phase, seconds}, run as a cycle. A day plan picks a list by the clock:
// {"00:00": [...], "07:00": [...], "09:30": [...]}. Phases left out are skipped.
function currentPlan(j) {
  const sch = j.schedule;
  if (!sch) return ORDER.map(phase => ({ phase, seconds: FIXED[phase] }));
  if (Array.isArray(sch)) return sch;
  const starts = Object.keys(sch).sort(), now = fmtClock(clock);
  let key = starts[starts.length - 1];
  for (const k of starts) if (k <= now) key = k;
  return sch[key];
}
function nextPhase(j) {
  if (j.mode === "manual") return j.request;
  if (j.mode === "schedule" || j.mode === "fixed") {
    const plan = currentPlan(j), i = plan.findIndex(e => e.phase === j.phase);
    return plan[(i + 1) % plan.length].phase;
  }
  const start = ORDER.indexOf(j.phase);
  for (let k = 1; k <= ORDER.length; k++) {
    const ph = ORDER[(start + k) % ORDER.length];
    if (j.mode === "fixed") return ph;
    const d = demand(j, ph);
    if (ph === "W" ? d >= 3 || maxPersonWait(j) > 35 : d > 0) return ph;
  }
  return null;
}
function maxPersonWait(j) { let m = 0; for (const p of people) if (p.waitJ === j.id) m = Math.max(m, p.legWait); return m; }
function wantsToEnd(j) {
  if (j.mode === "manual") return j.request && j.request !== j.phase;
  if (j.mode === "fixed") return j.t >= FIXED[j.phase];
  if (j.mode === "schedule") { const e = currentPlan(j).find(e => e.phase === j.phase); return !e || j.t >= e.seconds; }
  const others = ORDER.some(ph => ph !== j.phase && (ph === "W" ? peopleWaiting(j) >= 3 || maxPersonWait(j) > 35 : demand(j, ph) > 0));
  if (j.phase === "W") return j.t >= 9;
  if (!others) return false;
  return j.t >= 30 || (j.t >= 6 && greenNear(j) === 0);
}
function stepLight(j, dt) {
  j.t += dt;
  if (j.mode === "direct") return;          // lights set from outside (your decide()): nothing changes them here
  if (j.stage === "green") { if (wantsToEnd(j)) { j.stage = "yellow"; j.t = 0; } }
  else if (j.stage === "walk") { if (wantsToEnd(j)) { j.stage = "flash"; j.t = 0; } }
  else if (j.stage === "yellow") { if (j.t >= YELLOW) { j.stage = "allred"; j.t = 0; } }
  else if (j.stage === "flash") { if (j.t >= FLASH) { j.stage = "allred"; j.t = 0; } }
  else if (j.stage === "allred") {
    if (j.t >= ALLRED && j.box.size === 0 && j.zebraPeds === 0) {   // the crossing must be empty
      const ph = nextPhase(j);
      if (ph) { j.phase = ph; j.stage = ph === "W" ? "walk" : "green"; j.t = 0; j.serial++; if (j.request === ph) j.request = null; }
    }
  }
}

// ----- people: they walk on the sidewalks and cross on the zebras ----------------------------
const NODES = [], EDGES = [];
const node = p => { NODES.push({ p, e: [] }); return NODES.length - 1; };
function edge(a, b, zebra = null, arm = null) {
  const len = Math.hypot(NODES[a].p[0] - NODES[b].p[0], NODES[a].p[1] - NODES[b].p[1]);
  const e = { a, b, len, zebra, arm, id: EDGES.length };
  EDGES.push(e); NODES[a].e.push(e); NODES[b].e.push(e);
}
for (const j of JUNCTIONS) {
  j.corner = { NW: node([j.x - PO, j.y - PO]), NE: node([j.x + PO, j.y - PO]), SE: node([j.x + PO, j.y + PO]), SW: node([j.x - PO, j.y + PO]) };
  edge(j.corner.NW, j.corner.NE, j.id, "north"); edge(j.corner.NE, j.corner.SE, j.id, "east");
  edge(j.corner.SE, j.corner.SW, j.id, "south"); edge(j.corner.SW, j.corner.NW, j.id, "west");
}
for (const j of JUNCTIONS) {
  const right = JUNCTIONS.find(k => k.r === j.r && k.c === j.c + 1), below = JUNCTIONS.find(k => k.c === j.c && k.r === j.r + 1);
  if (right) { edge(j.corner.NE, right.corner.NW); edge(j.corner.SE, right.corner.SW); }
  if (below) { edge(j.corner.SW, below.corner.NW); edge(j.corner.SE, below.corner.NE); }
  if (j.r === 0) { edge(j.corner.NW, node([j.x - PO, -6])); edge(j.corner.NE, node([j.x + PO, -6])); }
  if (j.r === 1) { edge(j.corner.SW, node([j.x - PO, H + 6])); edge(j.corner.SE, node([j.x + PO, H + 6])); }
  if (j.c === 0) { edge(j.corner.NW, node([-6, j.y - PO])); edge(j.corner.SW, node([-6, j.y + PO])); }
  if (j.c === 1) { edge(j.corner.NE, node([W + 6, j.y - PO])); edge(j.corner.SE, node([W + 6, j.y + PO])); }
}
// shortest paths between all nodes (crossing a zebra costs a little extra: people prefer not to)
const N = NODES.length, DIST = [], NEXT = [];
for (let i = 0; i < N; i++) { DIST.push(new Array(N).fill(Infinity)); NEXT.push(new Array(N).fill(-1)); DIST[i][i] = 0; NEXT[i][i] = i; }
for (const e of EDGES) { const w = e.len + (e.zebra !== null ? 12 : 0); DIST[e.a][e.b] = DIST[e.b][e.a] = w; NEXT[e.a][e.b] = e.b; NEXT[e.b][e.a] = e.a; }
for (let k = 0; k < N; k++) for (let i = 0; i < N; i++) for (let jj = 0; jj < N; jj++)
  if (DIST[i][k] + DIST[k][jj] < DIST[i][jj]) { DIST[i][jj] = DIST[i][k] + DIST[k][jj]; NEXT[i][jj] = NEXT[i][k]; }
const SIDEWALKS = EDGES.filter(e => e.zebra === null);
const edgeBetween = (a, b) => NODES[a].e.find(e => e.a === b || e.b === b);

const people = new Set();
function spawnPerson() {
  const e1 = pick(SIDEWALKS), e2 = pick(SIDEWALKS);
  const t1 = 0.1 + rnd() * 0.8, t2 = 0.1 + rnd() * 0.8;
  const pt = (e, t) => [NODES[e.a].p[0] + (NODES[e.b].p[0] - NODES[e.a].p[0]) * t, NODES[e.a].p[1] + (NODES[e.b].p[1] - NODES[e.a].p[1]) * t];
  const from = pt(e1, t1), to = pt(e2, t2);
  let best = null;
  for (const a of [e1.a, e1.b]) for (const b of [e2.a, e2.b]) {
    const d = Math.hypot(from[0] - NODES[a].p[0], from[1] - NODES[a].p[1]) + DIST[a][b] + Math.hypot(to[0] - NODES[b].p[0], to[1] - NODES[b].p[1]);
    if (!best || d < best.d) best = { a, b, d };
  }
  const route = [best.a];
  while (route[route.length - 1] !== best.b) route.push(NEXT[route[route.length - 1]][best.b]);
  const pts = [from, ...route.map(n => NODES[n].p), to];
  const legs = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const e = i >= 1 && i < route.length ? edgeBetween(route[i - 1], route[i]) : null;
    legs.push({ a: pts[i], b: pts[i + 1], len: Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]),
                zebra: e ? e.zebra : null, arm: e ? e.arm : null });
  }
  if (e1 === e2) legs.splice(0, legs.length, { a: from, b: to, len: Math.hypot(to[0] - from[0], to[1] - from[1]), zebra: null });
  people.add({ legs, i: 0, pos: 0, speed: 1.1 + rnd() * 0.5, side: (rnd() - 0.5) * 1.6, shirt: pick(SHIRTS),
               jx: (rnd() - 0.5) * 2.2, jy: (rnd() - 0.5) * 2.2, waitJ: null, onZebra: null, wait: 0, legWait: 0, phase: rnd() * 6, k: 0, jf: 0 });
}

// ----- the clock and how busy the city is ---------------------------------------------------
let clock = 7.5 * 60;           // minutes since midnight; 1 simulated second = 1 clock minute
const CLOCK_RATE = 1;
function busy(min) {
  const h = (min / 60) % 24;
  if (h >= 7 && h < 9.5) return 1.0;
  if (h >= 17 && h < 19.5) return 1.05;
  if (h >= 23 || h < 6) return 0.18;
  return 0.6;
}
// Rush hours: for one clock hour, many more cars come from one side of the map (cars: the way they drive,
// E = from the left to the right of the map, N = from the bottom to the top), or a crowd of people walks.
const WAVES = [
  { hour: 9, cars: "E", label: "rush: cars from left to right" },
  { hour: 10, cars: "N", label: "rush: cars from bottom to top" },
  { hour: 11, cars: "E", label: "rush: cars from left to right" },
  { hour: 12, people: 4, label: "lunch: a huge crowd walks" },
  { hour: 13, cars: "W", label: "rush: cars from right to left" },
  { hour: 14, cars: "S", label: "rush: cars from top to bottom" },
  { hour: 15, people: 2.5, cars: "N", label: "school is out: people, and cars to the top" },
  { hour: 16, cars: "E", label: "rush: cars from left to right" },
  { hour: 17, cars: "WS", label: "home time: cars to the left and to the bottom" },
  { hour: 18, people: 3, label: "after work: a crowd walks" },
  { hour: 19, cars: "N", label: "rush: cars from bottom to top" },
];
const WAVE_CARS = 2, WAVE_SIDE = 6;   // in a car rush: twice the cars, and their side is 6 times as likely
const waveAt = min => WAVES.find(w => w.hour === Math.floor(min / 60) % 24) || null;

// ----- the simulation step ----------------------------------------------------------------------
const DT = 0.05;
// The tick is the city's beat: at the start of a tick, per lane, the first vehicle at the stop line
// goes (if it may), and it is fully across the crossing at the end of that tick: exactly 1 tick.
const TICK = 3;                                  // simulated seconds per tick (3 clock minutes)
const TICK_STEPS = Math.round(TICK / DT);        // simulation steps per tick
const AT_LINE = 12;                              // metres: this close to the stop line counts as "at the line"
let tickStep = 0;                                // steps done in the current tick (0 = a tick starts)
const stats = { tripsV: 0, tripsP: 0, waitV: 0, waitP: 0, collisions: 0, events: [], cameFrom: { N: 0, S: 0, E: 0, W: 0 }, peopleCame: 0,
                crossed: 0 };   // vehicles and people that went across a crossing (the live score counts them)
let spawnV = 0, spawnP = 0;

function idm(v, gap, dv, v0) {
  const sp = v.spec, s0 = sp.bike ? 1.0 : 2.0;
  const sStar = s0 + Math.max(0, v.v * 1.2 + v.v * dv / (2 * Math.sqrt(sp.a * sp.b)));
  return sp.a * (1 - Math.pow(v.v / v0, 4) - Math.pow(sStar / Math.max(gap, 0.05), 2));
}
function freeSpeed(v) {
  const dist = v.seg.to === null ? 1e9 : v.seg.len - v.s;
  if (v.move && v.move !== "S" && dist < 35) return Math.min(v.spec.v0, (v.move === "L" ? 7 : 5.5) + dist * 0.2);
  return v.spec.v0;
}

function stepVehicles(dt) {
  // 1) accelerations
  for (const seg of SEGS) for (const lane of ["L", "S", "B"]) {
    const list = seg.lanes[lane];
    for (let i = 0; i < list.length; i++) {
      const v = list[i];
      let a = idm(v, 1e9, 0, freeSpeed(v));
      if (i > 0) { const l = list[i - 1]; a = Math.min(a, idm(v, l.s - l.len - v.s, v.v - l.v, freeSpeed(v))); }
      else if (seg.to !== null) {
        const q = seg.connQ[lane], dist = seg.len - v.s;
        if (q.length) { const l = q[q.length - 1]; a = Math.min(a, idm(v, dist + l.conn.s - l.len, v.v - l.v, freeSpeed(v))); }
        if (dist < 60) a = Math.min(a, idm(v, dist - 0.3, v.v, freeSpeed(v)));   // it goes at a tick: until then, the line
      }
      v.acc = Math.max(-9, a);
    }
  }
  // 2) move
  for (const v of [...vehicles]) {
    if (v.conn) { crossStep(v); continue; }
    v.v = Math.max(0, v.v + v.acc * dt);
    if (v.v < 0.3) { v.wait += dt; v.waitHere += dt; }
    const seg = v.seg;
    let ns = v.s + v.v * dt;
    if (seg.to !== null && ns >= seg.len) { ns = seg.len; v.v = 0; }   // at the stop line: it goes at a tick (startTick)
    v.s = ns;
    if (seg.to === null && v.s - v.len > seg.len) {      // left the map
      seg.lanes[v.lane].splice(seg.lanes[v.lane].indexOf(v), 1);
      vehicles.delete(v); stats.tripsV++; stats.waitV += v.wait;
    }
  }
}

// A tick starts: per lane, the first vehicle at the stop line goes if it may. Bikes first: right turns give way to them.
// People at a zebra with the walk light go too: they are across in exactly this tick.
function startTick() {
  SEGS.filter(seg => seg.to !== null).forEach(seg => {   // bikes first, unless a right turn already gave way to them
    (seg.lanes.S[0] && seg.lanes.S[0].gaveWay ? ["S", "B", "L"] : ["B", "S", "L"]).forEach(lane => {
      const v = seg.lanes[lane][0];
      if (v && seg.len - v.s <= AT_LINE && mayGo(v)) enter(v);
    });
  });
  people.forEach(p => {
    const j = p.waitJ !== null && JUNCTIONS[p.waitJ];
    if (!j || j.stage !== "walk" || j.box.size > 0) return;           // walk, once cars have left
    countPerson(j, p.legs[p.i].arm, p.legWait); stats.crossed++;
    p.jf = Math.min(1, p.legWait);                                     // how far it stepped aside while it waited
    p.waitJ = null; p.legWait = 0; p.onZebra = j.id; p.k = 0; j.zebraPeds++;
  });
}
function enter(v) {
  const seg = v.seg, j = JUNCTIONS[seg.to], plan = planFor(v);
  seg.lanes[v.lane].shift();
  const s0 = v.s - seg.len, D = plan.path.len + v.len + 0.5 - s0;   // from where it stands until its rear is out of the crossing
  v.conn = { path: plan.path, s: s0, s0, D, k: 0, ...crossProfile(v.v, D, cruiseOf(v)),
             from: seg, fromLane: v.lane, out: plan.out, outLane: plan.outLane, j: j.id };
  seg.connQ[v.lane].push(v);
  j.box.add(v); v.boxJ = j;
  countVehicle(j, seg.head, v); stats.crossed++;
}
const cruiseOf = v => Math.min(v.spec.v0, { S: Infinity, L: 7, R: 5.5 }[v.move]);   // the speed it wants across
// The speed across a crossing: from the speed it has, smoothly to a cruise speed (as near the speed it
// wants as fits), then steady, so that it covers exactly D in exactly 1 tick. Never a jump in speed.
function crossProfile(vIn, D, want) {
  const avg = D / TICK, far = Math.max(0, 2 * avg - vIn);         // cruise at far: the speed changes over the whole tick
  const near = avg + 0.3 * (far - avg);                           // at avg it would have to change at once: keep away
  const vc = Math.min(Math.max(near, far), Math.max(Math.min(near, far), want));
  const ta = Math.abs(vc - vIn) < 1e-6 ? 0 : 2 * (vc * TICK - D) / (vc - vIn);   // seconds until it cruises
  return { vIn, vc, ta };
}
function crossStep(v) {
  const c = v.conn, t = TICK * ++c.k / TICK_STEPS;
  const done = t < c.ta ? c.vIn * t + (c.vc - c.vIn) * t * t / (2 * c.ta) : (c.vIn + c.vc) * c.ta / 2 + c.vc * (t - c.ta);
  c.s = c.k < TICK_STEPS ? c.s0 + done : c.s0 + c.D;
  v.v = t < c.ta ? c.vIn + (c.vc - c.vIn) * t / c.ta : c.vc; v.acc = t < c.ta ? (c.vc - c.vIn) / c.ta : 0;
  if (c.k < TICK_STEPS) return;                                   // after exactly 1 tick it is on the next road
  const q = c.from.connQ[c.fromLane]; q.splice(q.indexOf(v), 1);
  const plan = v.plan;
  v.conn = null; v.plan = null;
  v.seg = plan.out; v.lane = plan.outLane; v.s = c.s - c.path.len; v.move = plan.nextMove; v.waitHere = 0;
  const lane = v.seg.lanes[v.lane], i = lane.findIndex(o => o.s < v.s);   // a lane is ordered front first
  lane.splice(i < 0 ? lane.length : i, 0, v);
  v.boxJ.box.delete(v); v.boxJ = null;                                    // its rear has left the crossing
}

function stepPeople(dt) {
  for (const p of [...people]) {
    const leg = p.legs[p.i];
    if (leg.zebra !== null && p.pos === 0 && p.onZebra === null) {   // at a zebra: it goes when a tick starts (startTick)
      p.waitJ = leg.zebra; p.wait += dt; p.legWait += dt; continue;
    }
    const zebra = p.onZebra !== null, speed = zebra ? leg.len / TICK : p.speed;   // a zebra: across in exactly 1 tick
    p.phase += dt * speed * 3;
    p.pos = zebra ? leg.len * ++p.k / TICK_STEPS : p.pos + speed * dt;
    if (zebra ? p.k >= TICK_STEPS : p.pos >= leg.len) {
      if (p.onZebra !== null) { JUNCTIONS[p.onZebra].zebraPeds--; p.onZebra = null; }
      p.i++; p.pos = 0;
      if (p.i >= p.legs.length) { people.delete(p); stats.tripsP++; stats.waitP += p.wait; }
    }
  }
}

function entryFor(wave) {   // where a new vehicle comes in: in a car rush, mostly on the rush's side
  const weights = ENTRIES.map(s => wave && wave.cars && wave.cars.includes(s.head) ? WAVE_SIDE : 1);
  let r = rnd() * weights.reduce((a, w) => a + w, 0);
  return ENTRIES.find((s, i) => (r -= weights[i]) < 0) || ENTRIES[ENTRIES.length - 1];
}
function spawn(dt) {
  const b = busy(clock), wave = waveAt(clock);
  spawnV += dt * b * 0.95 * (wave && wave.cars ? WAVE_CARS : 1);   // vehicles per second over the whole map
  while (spawnV >= 1) {
    spawnV -= 1;
    const seg = entryFor(wave), v = makeVehicle(randomType());
    seg.backlog.push(v); stats.cameFrom[seg.head]++;
  }
  for (const seg of ENTRIES) {
    if (!seg.backlog.length) continue;
    const v = seg.backlog[0];
    const lane = seg.lanes[v.spec.bike ? "B" : "S"], tail = lane.length ? lane[lane.length - 1] : null;
    const laneL = seg.lanes.L, tailL = laneL.length ? laneL[laneL.length - 1] : null;
    v.seg = seg;
    v.move = randomMove(v.spec.bike);
    const want = laneFor(v, seg), t = want === "L" ? tailL : tail;
    if (t && t.s - t.len < v.len + 3) continue;          // no room yet: it waits at the edge of the map
    seg.backlog.shift();
    v.lane = want; v.s = 0; v.v = Math.min(v.spec.v0, t ? Math.max(0, t.v) : v.spec.v0) * 0.8;
    seg.lanes[want].push(v); vehicles.add(v);
  }
  const crowd = wave && wave.people ? wave.people : 1;
  spawnP += dt * b * 0.8 * crowd;
  while (spawnP >= 1) { spawnP -= 1; if (people.size < 260 * crowd) { spawnPerson(); stats.peopleCame++; } }
}

// ----- safety check: nothing may overlap, and no car may be on a zebra while people walk ----------
function shape(v) {
  let x, y, a;
  if (v.conn) {
    const c = v.conn, back = c.s - v.len / 2;
    if (back > c.path.len) { const p = lanePoint(c.out, back - c.path.len, c.outLane); x = p[0]; y = p[1]; const d = DIRS[c.out.head]; a = Math.atan2(d[1], d[0]); }
    else if (back >= 0) [x, y, a] = along(c.path, back);
    else { const p = lanePoint(c.from, c.from.len + back, c.fromLane); x = p[0]; y = p[1]; const d = DIRS[c.from.head]; a = Math.atan2(d[1], d[0]); }
  } else {
    const p = lanePoint(v.seg, v.s - v.len / 2, v.lane), d = DIRS[v.seg.head];
    x = p[0]; y = p[1]; a = Math.atan2(d[1], d[0]);
  }
  return { x, y, a };
}
function circles(v, sh) {
  const n = Math.max(1, Math.round(v.len / v.spec.w)), out = [];
  for (let i = 0; i < n; i++) {
    const k = (i + 0.5) / n - 0.5;
    out.push([sh.x + Math.cos(sh.a) * k * v.len, sh.y + Math.sin(sh.a) * k * v.len, v.spec.w / 2]);
  }
  return out;
}
function checkSafety() {
  for (const j of JUNCTIONS) {
    const list = [...j.box].map(v => ({ v, c: circles(v, shape(v)) }));
    for (let i = 0; i < list.length; i++) for (let k = i + 1; k < list.length; k++) {
      let hit = false;
      for (const p of list[i].c) for (const q of list[k].c) if (Math.hypot(p[0] - q[0], p[1] - q[1]) < p[2] + q[2] - 0.35) hit = true;
      if (hit) { stats.collisions++; if (stats.events.length < 20) stats.events.push({ j: j.id, a: list[i].v.type + list[i].v.move + "@" + (list[i].v.conn ? list[i].v.conn.from.head + (list[i].v.conn.s).toFixed(1) : "out" + list[i].v.seg.head + list[i].v.s.toFixed(1)), b: list[k].v.type + list[k].v.move + "@" + (list[k].v.conn ? list[k].v.conn.from.head + (list[k].v.conn.s).toFixed(1) : "out" + list[k].v.seg.head + list[k].v.s.toFixed(1)), clock }); }
    }
    if (j.zebraPeds > 0 && j.box.size > 0) { stats.collisions++; if (stats.events.length < 20) stats.events.push({ j: j.id, a: "people on zebra", b: "vehicle in crossing", clock }); }
  }
}

let simSteps = 0;     // steps the simulation has run
let step = function (dt) {
  simSteps++;
  clock = (clock + dt * CLOCK_RATE) % (24 * 60);
  spawn(dt);
  for (const j of JUNCTIONS) stepLight(j, dt);
  if (tickStep === 0) startTick();
  tickStep = (tickStep + 1) % TICK_STEPS;
  stepVehicles(dt);
  stepPeople(dt);
  checkSafety();
};
function darkness() {
  const h = (clock / 60) % 24;
  if (h >= 6.5 && h <= 17.5) return 0;
  if (h > 17.5 && h < 19.5) return (h - 17.5) / 2 * 0.55;
  if (h >= 5 && h < 6.5) return (6.5 - h) / 1.5 * 0.55;
  return 0.55;
}
const FROM = { S: "north", N: "south", W: "east", E: "west" };   // heading -> the side the traffic comes from
const LANE_NAME = { L: "left_turn", S: "straight_right", B: "bike" };
function laneState(seg, lane) {
  const out = { queue: 0, approaching: 0, max_wait_s: 0, types: {}, moves: { left: 0, straight: 0, right: 0 } };
  for (const v of seg.lanes[lane]) {
    const dist = seg.len - v.s;
    if (dist > 80) continue;
    if (v.v < 0.3) out.queue++; else out.approaching++;
    out.max_wait_s = Math.max(out.max_wait_s, Math.round(v.waitHere));
    out.types[v.type] = (out.types[v.type] || 0) + 1;
    out.moves[{ L: "left", S: "straight", R: "right" }[v.move]]++;
  }
  return out;
}
function junctionState(j) {
  const approaches = {};
  for (const head of ["S", "W", "N", "E"]) {
    const seg = inSeg(j.id, head), lanes = {};
    for (const l of ["L", "S", "B"]) lanes[LANE_NAME[l]] = laneState(seg, l);
    approaches[FROM[head]] = { lanes, queue: Object.values(lanes).reduce((n, x) => n + x.queue, 0),
                               light: { left_turn: signalFor(j, head, "L"), straight_right: signalFor(j, head, "S") } };
  }
  const zebras = {};
  for (const arm of ["north", "east", "south", "west"]) zebras[arm] = { waiting: 0, max_wait_s: 0 };
  for (const p of people) if (p.waitJ === j.id) {
    const z = zebras[p.legs[p.i].arm]; z.waiting++; z.max_wait_s = Math.max(z.max_wait_s, Math.round(p.legWait));
  }
  return {
    id: j.id, name: j.name, mode: j.mode, phase: j.phase, phase_label: PHASES[j.phase].label, stage: j.stage,
    seconds_in_stage: +j.t.toFixed(1), requested: j.request,
    demand: Object.fromEntries(ORDER.map(ph => [ph, demand(j, ph)])),   // vehicles (or people for W) each phase would serve
    approaches, zebras,
    people_waiting: Object.values(zebras).reduce((n, z) => n + z.waiting, 0),
    vehicles_in_crossing: j.box.size, people_on_zebras: j.zebraPeds,
  };
}
// ----- history: what each crossing served, per 15 minutes of the clock ---------------------------
const BUCKET = 15, history = [];
function bucket() {
  const start = Math.floor(clock / BUCKET) * BUCKET;
  let b = history[history.length - 1];
  if (!b || b.minute !== start) {
    const approaches = () => Object.fromEntries(["north", "east", "south", "west"].map(a => [a,
      { left: 0, straight: 0, right: 0, vehicles: 0, wait_sum: 0, max_queue: 0 }]));
    b = { minute: start, start: fmtClock(start), junctions: JUNCTIONS.map(j => ({
      id: j.id, vehicles: approaches(), people: Object.fromEntries(["north", "east", "south", "west"].map(a => [a, { people: 0, wait_sum: 0 }])),
      green_seconds: Object.fromEntries(ORDER.map(p => [p, 0])) })) };
    history.push(b);
    if (history.length > 24 * 60 / BUCKET * 3) history.shift();   // keep 3 days
  }
  return b;
}
function countVehicle(j, head, v) {
  const a = bucket().junctions[j.id].vehicles[FROM[head]];
  a[{ L: "left", S: "straight", R: "right" }[v.move]]++; a.vehicles++; a.wait_sum += v.waitHere;
}
function countPerson(j, arm, wait) { const z = bucket().junctions[j.id].people[arm]; z.people++; z.wait_sum += wait; }
function sampleHistory() {
  const b = bucket();
  for (const j of JUNCTIONS) {
    const h = b.junctions[j.id];
    if (j.stage === "green" || j.stage === "walk") h.green_seconds[j.phase]++;
    for (const head of ["S", "W", "N", "E"]) {
      const seg = inSeg(j.id, head);
      let q = 0; for (const l of ["L", "S", "B"]) for (const v of seg.lanes[l]) if (v.v < 0.3 && seg.len - v.s < 80) q++;
      const a = h.vehicles[FROM[head]]; a.max_queue = Math.max(a.max_queue, q);
    }
  }
}
function historyOut(last) {
  return history.slice(-(last || history.length)).map(b => ({ start: b.start, junctions: b.junctions.map(h => ({
    id: h.id, green_seconds: h.green_seconds,
    vehicles: Object.fromEntries(Object.entries(h.vehicles).map(([k, a]) => [k, { left: a.left, straight: a.straight, right: a.right,
      avg_wait_s: a.vehicles ? +(a.wait_sum / a.vehicles).toFixed(1) : 0, max_queue: a.max_queue }])),
    people: Object.fromEntries(Object.entries(h.people).map(([k, z]) => [k, { crossed: z.people, avg_wait_s: z.people ? +(z.wait_sum / z.people).toFixed(1) : 0 }])),
  })) }));
}
function checkSchedule(plan) {
  const lists = Array.isArray(plan) ? [plan] : Object.entries(plan).map(([k, v]) => { if (!/^\d\d:\d\d$/.test(k)) throw new Error(`day plan keys are "HH:MM", got ${k}`); return v; });
  for (const list of lists) {
    if (!Array.isArray(list) || !list.length) throw new Error("a schedule is a list of {phase, seconds}");
    for (const e of list) {
      if (!PHASES[e.phase]) throw new Error(`phase must be one of ${ORDER.join(", ")}, got ${e.phase}`);
      if (!(e.seconds >= 3 && e.seconds <= 180)) throw new Error(`seconds must be 3..180, got ${e.seconds}`);
    }
  }
}

const secondListeners = [];
let secondAcc = 0;
const _step = step;
step = function (dt) { _step(dt); secondAcc += dt; if (secondAcc >= 1) { secondAcc -= 1; sampleHistory(); if (secondListeners.length) { const st = cityState(); secondListeners.forEach(f => f(st)); } } };
function cityState() {
  let wv = 0; for (const v of vehicles) if (v.v < 0.3) wv++;
  let wp = 0; for (const p of people) if (p.waitJ !== null) wp++;
  return {
    clock: fmtClock(clock), minute_of_day: Math.floor(clock), rush_hour: busy(clock) >= 1, night: darkness() > 0.25,
    wave: waveAt(clock) ? waveAt(clock).label : null,
    totals: { vehicles: vehicles.size, people: people.size, vehicles_waiting: wv, people_waiting: wp,
              trips_vehicles: stats.tripsV, trips_people: stats.tripsP,
              avg_wait_vehicle_s: stats.tripsV ? +(stats.waitV / stats.tripsV).toFixed(1) : 0,
              avg_wait_person_s: stats.tripsP ? +(stats.waitP / stats.tripsP).toFixed(1) : 0,
              collisions: stats.collisions },
    phases: Object.fromEntries(ORDER.map(p => [p, PHASES[p].label])),
    junctions: JUNCTIONS.map(junctionState),
  };
}

// what decide() gets: per crossing its lights and who waits; city.state() has everything else
const SIDES = ["north", "east", "south", "west"];
function decideState(tick) {
  return { tick, clock: fmtClock(clock), crossings: JUNCTIONS.map(j => {
    const s = junctionState(j);
    return {
      id: j.id, name: j.name, lights: j.stage === "allred" ? null : j.phase, ticks: Math.round(j.t / TICK),
      cars: Object.fromEntries(SIDES.map(side => { const l = s.approaches[side].lanes;
        return [side, { left: l.left_turn.queue, straight_right: l.straight_right.queue, bikes: l.bike.queue }]; })),
      people: Object.fromEntries(SIDES.map(side => [side, s.zebras[side].waiting])),
    };
  }) };
}
for (let i = 0; i < 90 / DT; i++) step(DT);
// driver: bridge to python policy over stdin/stdout lines
const readline = require("readline");
const rl = readline.createInterface({ input: process.stdin });
const it = rl[Symbol.asyncIterator]();
const PRE = +(process.env.PRE || 0), TICKS = +(process.env.TICKS || 270);
function runTick() { do { step(DT); } while (tickStep !== 0); }
for (let i = 0; i < PRE; i++) runTick();   // smart-mode ticks before /api/config arrives
for (const j of JUNCTIONS) { j.mode = "direct"; j.request = null; j.stage = "allred"; j.t = 0; j.serial++; }
function setLights(id, phase) { const j = JUNCTIONS[id];
  if (j.mode === "direct" && j.phase === phase && j.stage !== "allred") return;
  j.mode = "direct"; j.request = null; j.phase = phase; j.stage = phase === "W" ? "walk" : "green"; j.t = 0; j.serial++; }
(async () => {
  let score = 0, lastCrossed = stats.crossed;
  for (let n = 1; n <= TICKS; n++) {
    process.stdout.write(JSON.stringify({ state: decideState(n) }) + "\n");
    const lights = JSON.parse((await it.next()).value);
    for (const [id, ph] of Object.entries(lights)) setLights(+id, ph);
    runTick();
    const st = cityState(), across = stats.crossed - lastCrossed; lastCrossed = stats.crossed;
    const pts = Math.round((across - 0.2 * (st.totals.vehicles_waiting + st.totals.people_waiting)) * 10) / 10;
    score = Math.round((score + pts) * 10) / 10;
    process.stdout.write(JSON.stringify({ tick: n, pts, score, across, wv: st.totals.vehicles_waiting, wp: st.totals.people_waiting }) + "\n");
  }
  process.stdout.write(JSON.stringify({ done: true, score }) + "\n");
  rl.close();
})();
