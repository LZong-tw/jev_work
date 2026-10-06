"""Deterministic Python port of the simulation in level5-junction/city.html (lines 157-704, 1171-1294,
plus the live-server flow of 1332-1417 and the server's history handling in city_server.py).

    run(policy, ticks=270, seed=7, pre_ticks=1) -> {"score", "states", "ticks"}

policy(history, current) -> {crossing_id: "A".."W"}, synchronous; history/current are shaped exactly like
what city_server.py passes to my_jev.decide (history = last 50 states, each with "lights_chosen").
pre_ticks: ticks the page runs in its built-in "smart" mode before /api/config answers (1 reproduces the
real browser runs). Float details follow V8: Math.hypot (Kahan), Math.pow(x,2) == x*x, Math.round.
"""
import json
import math

INF = math.inf
M32 = 0xFFFFFFFF


def _imul(a, b):
    return (a * b) & M32


def mulberry32(a):
    st = [a & M32]

    def r():
        a = st[0] = (st[0] + 0x6D2B79F5) & M32
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & M32) ^ t
        return ((t ^ (t >> 14)) & M32) / 4294967296
    return r


def hypot(a, b):   # V8's Math.hypot, bit-exact
    a, b = abs(a), abs(b)
    m = a if a > b else b
    if m == 0:
        return 0.0
    if m == INF:
        return INF
    s = c = 0.0
    for x in (a, b):
        n = x / m
        summand = n * n - c
        pre = s + summand
        c = (pre - s) - summand
        s = pre
    return math.sqrt(s) * m


def jsround(x):
    return math.floor(x + 0.5)


def fmt_clock(m):
    return f"{int(math.fmod(math.floor(m / 60), 24)):02d}:{int(math.floor(math.fmod(m, 60))):02d}"


W, H = 400, 300
XS, YS = [133, 267], [100, 200]
AVENUES, STREETS = ["Fuxing S. Rd", "Dunhua S. Rd"], ["Zhongxiao E. Rd", "Ren'ai Rd"]
LANE, MED, BIKE = 3.2, 0.3, 1.8
OFF = {"L": MED + LANE / 2, "S": MED + LANE * 1.5, "B": MED + LANE * 2 + BIKE / 2}
HW = MED + 2 * LANE + BIKE
ZEB = [HW + 0.8, HW + 3.8]
STOP = HW + 4.6
PO = (ZEB[0] + ZEB[1]) / 2
DIRS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
TURN = {"N": {"S": "N", "R": "E", "L": "W"}, "S": {"S": "S", "R": "W", "L": "E"},
        "E": {"S": "E", "R": "S", "L": "N"}, "W": {"S": "W", "R": "N", "L": "S"}}
PHASES = {"A": ("NS", "SR"), "B": ("NS", "L"), "C": ("EW", "SR"), "D": ("EW", "L"), "W": ("", "")}
ORDER = ["A", "B", "C", "D", "W"]
YELLOW, ALLRED, FLASH = 3, 1.5, 5
TYPES = {   # len, w, v0, a, b, bike, share
    "car": (4.5, 1.9, 13.9, 1.7, 2.6, False, 0.44), "taxi": (4.6, 1.9, 14.5, 1.9, 2.8, False, 0.11),
    "bus": (11.5, 2.5, 11.0, 1.0, 2.0, False, 0.05), "scooter": (1.9, 0.8, 12.0, 2.2, 3.0, True, 0.27),
    "bike": (1.8, 0.7, 5.0, 1.0, 2.0, True, 0.13)}
N_CAR_COLORS, N_SHIRTS = 10, 9
WAVES = {9: ("E", None), 10: ("N", None), 11: ("E", None), 12: (None, 4), 13: ("W", None), 14: ("S", None),
         15: ("N", 2.5), 16: ("E", None), 17: ("WS", None), 18: (None, 3), 19: ("N", None)}   # hour: (cars, people)
WAVE_CARS, WAVE_SIDE = 2, 6
DT, TICK = 0.05, 3
TICK_STEPS = jsround(TICK / DT)
AT_LINE = 12
FROM = {"S": "north", "N": "south", "W": "east", "E": "west"}
SIDES = ["north", "east", "south", "west"]
SIDE_HEAD = {v: k for k, v in FROM.items()}
TRUE_MOVE = {"L": "left", "S": "straight", "R": "right"}


def add(p, d, k):
    return (p[0] + d[0] * k, p[1] + d[1] * k)


def right_of(d):
    return (-d[1], d[0])


def busy(m):
    h = math.fmod(m / 60, 24)
    if 7 <= h < 9.5:
        return 1.0
    if 17 <= h < 19.5:
        return 1.05
    if h >= 23 or h < 6:
        return 0.18
    return 0.6


def wave_at(m):
    return WAVES.get(int(math.fmod(math.floor(m / 60), 24)))


class Seg:
    __slots__ = ("id", "head", "start", "len", "frm", "to", "lanes", "connQ", "backlog")


class Veh:
    __slots__ = ("id", "type", "len", "w", "v0", "a", "b", "bike", "v", "s", "seg", "lane", "move", "conn", "plan",
                 "wait", "waitHere", "acc", "boxJ", "gaveWay")


class Conn:
    __slots__ = ("path", "s", "s0", "D", "k", "vIn", "vc", "ta", "frm", "fromLane", "out", "outLane", "j")


class Person:
    __slots__ = ("legs", "i", "pos", "speed", "waitJ", "onZebra", "wait", "legWait", "k")


class Junction:
    __slots__ = ("id", "x", "y", "r", "c", "name", "mode", "phase", "stage", "t", "request", "box", "zebraPeds",
                 "corner", "inseg")


class City:
    def __init__(self, seed=7):
        self.rnd = mulberry32(seed)
        self.J = []
        for r, y in enumerate(YS):
            for c, x in enumerate(XS):
                j = Junction()
                j.id, j.x, j.y, j.r, j.c = len(self.J), x, y, r, c
                j.name = f"{AVENUES[c].split(' ')[0]} × {STREETS[r].split(' ')[0]}"
                j.mode, j.phase, j.stage, j.t, j.request = "smart", "A", "green", 0.0, None
                j.box, j.zebraPeds = {}, 0
                self.J.append(j)
        self.SEGS = []
        for y in YS:
            self._add_line(True, y, XS)
        for x in XS:
            self._add_line(False, x, YS)
        self.ENTRIES = [s for s in self.SEGS if s.frm is None]
        for j in self.J:
            j.inseg = {h: next(s for s in self.SEGS if s.to == j.id and s.head == h) for h in "NSEW"}
        self.outseg = {(s.frm, s.head): s for s in self.SEGS if s.frm is not None}
        self.PATHS = {}
        self._build_walks()
        self.next_id = 1
        self.vehicles = {}   # insertion-ordered set (JS Set)
        self.people = {}
        self.clock = 7.5 * 60
        self.tick_step = 0
        self.crossed = 0
        self.spawnV = self.spawnP = 0.0

    def _jat(self, x, y):
        return next(j for j in self.J if j.x == x and j.y == y).id

    def _add_line(self, horizontal, c, stops):
        lo, hi = -25, (W if horizontal else H) + 25
        for head in (["E", "W"] if horizontal else ["S", "N"]):
            sg = 1 if head in "ES" else -1
            pts = [lo, *stops, hi] if sg > 0 else [hi, *reversed(stops), lo]
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                frm = (self._jat(a, c) if horizontal else self._jat(c, a)) if i > 0 else None
                to = (self._jat(b, c) if horizontal else self._jat(c, b)) if i < len(pts) - 2 else None
                s0 = a + (sg * STOP if frm is not None else 0)
                s1 = b - (sg * STOP if to is not None else 0)
                s = Seg()
                s.id, s.head, s.len, s.frm, s.to = len(self.SEGS), head, abs(s1 - s0), frm, to
                s.start = (s0, c) if horizontal else (c, s0)
                s.lanes, s.connQ, s.backlog = {"L": [], "S": [], "B": []}, {"L": [], "S": [], "B": []}, []
                self.SEGS.append(s)

    def lane_point(self, seg, s, lane):
        d = DIRS[seg.head]
        return add(add(seg.start, d, s), right_of(d), OFF[lane])

    def path_for(self, a, la, b, lb):
        key = (a.id, la, b.id, lb)
        p = self.PATHS.get(key)
        if p:
            return p
        p0, p3, d0, d3 = self.lane_point(a, a.len, la), self.lane_point(b, 0, lb), DIRS[a.head], DIRS[b.head]
        if a.head == b.head:
            pts = [p0, p3]
        else:
            dx, dy = p3[0] - p0[0], p3[1] - p0[1]
            k0, k3 = 0.552 * abs(dx * d0[0] + dy * d0[1]), 0.552 * abs(dx * d3[0] + dy * d3[1])
            p1, p2 = add(p0, d0, k0), add(p3, d3, -k3)
            pts = []
            for i in range(21):
                t = i / 20
                u = 1 - t
                pts.append((u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
        cum = 0.0
        for i in range(1, len(pts)):
            cum = cum + hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        self.PATHS[key] = cum   # only the length matters to the simulation
        return cum

    # ----- people graph
    def _build_walks(self):
        NODES, EDGES = [], []   # node: [p, edges]; edge: (a, b, len, zebra, arm)

        def node(p):
            NODES.append((p, []))
            return len(NODES) - 1

        def edge(a, b, zebra=None, arm=None):
            pa, pb = NODES[a][0], NODES[b][0]
            e = (a, b, hypot(pa[0] - pb[0], pa[1] - pb[1]), zebra, arm, len(EDGES))
            EDGES.append(e)
            NODES[a][1].append(e)
            NODES[b][1].append(e)
        for j in self.J:
            j.corner = {"NW": node((j.x - PO, j.y - PO)), "NE": node((j.x + PO, j.y - PO)),
                        "SE": node((j.x + PO, j.y + PO)), "SW": node((j.x - PO, j.y + PO))}
            edge(j.corner["NW"], j.corner["NE"], j.id, "north"); edge(j.corner["NE"], j.corner["SE"], j.id, "east")
            edge(j.corner["SE"], j.corner["SW"], j.id, "south"); edge(j.corner["SW"], j.corner["NW"], j.id, "west")
        for j in self.J:
            right = next((k for k in self.J if k.r == j.r and k.c == j.c + 1), None)
            below = next((k for k in self.J if k.c == j.c and k.r == j.r + 1), None)
            if right:
                edge(j.corner["NE"], right.corner["NW"]); edge(j.corner["SE"], right.corner["SW"])
            if below:
                edge(j.corner["SW"], below.corner["NW"]); edge(j.corner["SE"], below.corner["NE"])
            if j.r == 0:
                edge(j.corner["NW"], node((j.x - PO, -6))); edge(j.corner["NE"], node((j.x + PO, -6)))
            if j.r == 1:
                edge(j.corner["SW"], node((j.x - PO, H + 6))); edge(j.corner["SE"], node((j.x + PO, H + 6)))
            if j.c == 0:
                edge(j.corner["NW"], node((-6, j.y - PO))); edge(j.corner["SW"], node((-6, j.y + PO)))
            if j.c == 1:
                edge(j.corner["NE"], node((W + 6, j.y - PO))); edge(j.corner["SE"], node((W + 6, j.y + PO)))
        n = len(NODES)
        D = [[INF] * n for _ in range(n)]
        NX = [[-1] * n for _ in range(n)]
        for i in range(n):
            D[i][i] = 0; NX[i][i] = i
        for a, b, ln, zebra, _, _ in EDGES:
            w = ln + (12 if zebra is not None else 0)
            D[a][b] = D[b][a] = w
            NX[a][b] = b; NX[b][a] = a
        for k in range(n):
            Dk = D[k]
            for i in range(n):
                Di, dik = D[i], D[i][k]
                for jj in range(n):
                    if dik + Dk[jj] < Di[jj]:
                        Di[jj] = dik + Dk[jj]; NX[i][jj] = NX[i][k]
        self.NODES, self.EDGES, self.DIST, self.NEXT = NODES, EDGES, D, NX
        self.SIDEWALKS = [e for e in EDGES if e[3] is None]

    def spawn_person(self):
        rnd, NODES = self.rnd, self.NODES
        e1 = self.SIDEWALKS[math.floor(rnd() * len(self.SIDEWALKS))]
        e2 = self.SIDEWALKS[math.floor(rnd() * len(self.SIDEWALKS))]
        t1, t2 = 0.1 + rnd() * 0.8, 0.1 + rnd() * 0.8

        def pt(e, t):
            a, b = NODES[e[0]][0], NODES[e[1]][0]
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        frm, to = pt(e1, t1), pt(e2, t2)
        best = None
        for a in (e1[0], e1[1]):
            for b in (e2[0], e2[1]):
                pa, pb = NODES[a][0], NODES[b][0]
                d = hypot(frm[0] - pa[0], frm[1] - pa[1]) + self.DIST[a][b] + hypot(to[0] - pb[0], to[1] - pb[1])
                if best is None or d < best[2]:
                    best = (a, b, d)
        route = [best[0]]
        while route[-1] != best[1]:
            route.append(self.NEXT[route[-1]][best[1]])
        pts = [frm, *(NODES[n][0] for n in route), to]
        legs = []
        for i in range(len(pts) - 1):
            e = None
            if 1 <= i < len(route):
                e = next(x for x in NODES[route[i - 1]][1] if x[0] == route[i] or x[1] == route[i])
            legs.append((hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]),
                         e[3] if e else None, e[4] if e else None))   # len, zebra, arm
        if e1 is e2:
            legs = [(hypot(to[0] - frm[0], to[1] - frm[1]), None, None)]
        p = Person()
        p.legs, p.i, p.pos, p.k = legs, 0, 0.0, 0
        p.speed = 1.1 + rnd() * 0.5
        rnd(); rnd(); rnd(); rnd(); rnd()          # side, shirt, jx, jy, phase: drawing only, but they use rnd
        p.waitJ = p.onZebra = None
        p.wait = p.legWait = 0.0
        self.people[p] = None

    # ----- vehicles
    def random_type(self):
        r = self.rnd()
        for k, t in TYPES.items():
            r -= t[6]
            if r < 0:
                return k
        return "car"

    def random_move(self, bike):
        r = self.rnd()
        return ("S" if r < 0.78 else "R") if bike else ("L" if r < 0.2 else "S" if r < 0.8 else "R")

    def make_vehicle(self, typ):
        v = Veh()
        v.id = self.next_id; self.next_id += 1
        v.type = typ
        v.len, v.w, v.v0, v.a, v.b, v.bike, _ = TYPES[typ]
        v.v = v.s = 0.0
        v.seg = v.lane = v.move = v.conn = v.plan = v.boxJ = None
        v.wait = v.waitHere = v.acc = 0.0
        v.gaveWay = False
        if typ == "car":
            self.rnd()     # colour
        self.rnd()         # rider shirt
        self.rnd()         # bus number
        return v

    @staticmethod
    def lane_for(v, seg):
        if v.bike:
            return "B"
        if seg.to is None:
            return "L" if v.id % 2 else "S"
        return "L" if v.move == "L" else "S"

    def signal(self, j, head, move):
        heads, moves = PHASES[j.phase]
        if head not in heads or move not in moves:
            return "R"
        return "G" if j.stage == "green" else "Y" if j.stage == "yellow" else "R"

    def tail_room(self, seg, lane):
        l = seg.lanes[lane]
        tail = l[-1] if l else None
        lead = l[-2] if len(l) >= 2 else None
        if not tail:
            ahead = 0
        elif lead:
            ahead = lead.s - lead.len - 2 - tail.s
        else:
            ahead = INF if seg.to is None else seg.len - tail.s
        onward = max(0, min(tail.v * TICK, ahead)) if tail else 0
        acc = 0
        for v in self.vehicles:
            c = v.conn
            if c and c.out is seg and c.outLane == lane:
                acc = acc + v.len + 2.5
        return (tail.s - tail.len + onward if tail else seg.len) - acc

    def plan_for(self, v):
        if v.plan:
            return v.plan
        out = self.outseg[(v.seg.to, TURN[v.seg.head][v.move])]
        nxt = None if out.to is None else self.random_move(v.bike)
        ol = "B" if v.bike else ("L" if v.id % 2 else "S") if out.to is None else ("L" if nxt == "L" else "S")
        v.plan = [out, ol, nxt, self.path_for(v.seg, v.lane, out, ol)]
        return v.plan

    def may_go(self, v):
        j = self.J[v.seg.to]
        if self.signal(j, v.seg.head, v.move) != "G":
            return False
        plan = self.plan_for(v)
        out = cross_profile(v.v, plan[3] + v.len + 0.5 - (v.s - v.seg.len), cruise_of(v))[1]
        need = v.len + 2.5 + out * out / 18
        if not self.tail_room(plan[0], plan[1]) >= need:
            other = None
            if not (v.bike or v.move != "S"):
                other = "S" if plan[1] == "L" else "L" if plan[0].to is None else None
            if not other or not self.tail_room(plan[0], other) >= need:
                return False
            plan[1] = other
            plan[2] = None if plan[0].to is None else "S"
            plan[3] = self.path_for(v.seg, v.lane, plan[0], other)
        if j.zebraPeds > 0:
            return False
        for o in j.box:
            if o.conn and o is not v and self.signal(j, o.conn.frm.head, o.move) != "G":
                return False
        seg = v.seg
        if not v.bike and v.move == "R":
            crossing = any(b.conn.path - b.conn.s > 3 for b in seg.connQ["B"])
            waiting = any(b.s > seg.len - 14 for b in seg.lanes["B"])
            if crossing or (waiting and not v.gaveWay):
                v.gaveWay = v.gaveWay or waiting or crossing
                return False
        if v.bike and any(c.move == "R" for c in seg.connQ["S"]):
            return False
        return True

    def enter(self, v):
        seg, j, plan = v.seg, self.J[v.seg.to], self.plan_for(v)
        seg.lanes[v.lane].pop(0)
        s0 = v.s - seg.len
        D = plan[3] + v.len + 0.5 - s0
        c = Conn()
        c.path, c.s, c.s0, c.D, c.k = plan[3], s0, s0, D, 0
        c.vIn, c.vc, c.ta = cross_profile(v.v, D, cruise_of(v))
        c.frm, c.fromLane, c.out, c.outLane, c.j = seg, v.lane, plan[0], plan[1], j.id
        v.conn = c
        seg.connQ[v.lane].append(v)
        j.box[v] = None
        v.boxJ = j
        self.crossed += 1

    def cross_step(self, v):
        c = v.conn
        c.k += 1
        t = TICK * c.k / TICK_STEPS
        if t < c.ta:
            done = c.vIn * t + (c.vc - c.vIn) * t * t / (2 * c.ta)
        else:
            done = (c.vIn + c.vc) * c.ta / 2 + c.vc * (t - c.ta)
        c.s = c.s0 + done if c.k < TICK_STEPS else c.s0 + c.D
        if t < c.ta:
            v.v = c.vIn + (c.vc - c.vIn) * t / c.ta; v.acc = (c.vc - c.vIn) / c.ta
        else:
            v.v = c.vc; v.acc = 0
        if c.k < TICK_STEPS:
            return
        c.frm.connQ[c.fromLane].remove(v)
        plan = v.plan
        v.conn = v.plan = None
        v.seg, v.lane, v.s, v.move, v.waitHere = plan[0], plan[1], c.s - c.path, plan[2], 0.0
        lane = v.seg.lanes[v.lane]
        i = next((k for k, o in enumerate(lane) if o.s < v.s), len(lane))
        lane.insert(i, v)
        del v.boxJ.box[v]
        v.boxJ = None

    def step_vehicles(self, dt):
        for seg in self.SEGS:
            for lane in ("L", "S", "B"):
                lst = seg.lanes[lane]
                for i, v in enumerate(lst):
                    fs = free_speed(v)
                    a = idm(v, 1e9, 0, fs)
                    if i > 0:
                        l = lst[i - 1]
                        a = min(a, idm(v, l.s - l.len - v.s, v.v - l.v, fs))
                    elif seg.to is not None:
                        q, dist = seg.connQ[lane], seg.len - v.s
                        if q:
                            l = q[-1]
                            a = min(a, idm(v, dist + l.conn.s - l.len, v.v - l.v, fs))
                        if dist < 60:
                            a = min(a, idm(v, dist - 0.3, v.v, fs))
                    v.acc = max(-9, a)
        for v in list(self.vehicles):
            if v.conn:
                self.cross_step(v)
                continue
            v.v = max(0, v.v + v.acc * dt)
            if v.v < 0.3:
                v.wait += dt; v.waitHere += dt
            seg = v.seg
            ns = v.s + v.v * dt
            if seg.to is not None and ns >= seg.len:
                ns = seg.len; v.v = 0
            v.s = ns
            if seg.to is None and v.s - v.len > seg.len:
                seg.lanes[v.lane].remove(v)
                del self.vehicles[v]

    def start_tick(self):
        for seg in self.SEGS:
            if seg.to is None:
                continue
            S0 = seg.lanes["S"][0] if seg.lanes["S"] else None
            for lane in (("S", "B", "L") if S0 and S0.gaveWay else ("B", "S", "L")):
                l = seg.lanes[lane]
                if l:
                    v = l[0]
                    if seg.len - v.s <= AT_LINE and self.may_go(v):
                        self.enter(v)
        for p in self.people:
            if p.waitJ is None:
                continue
            j = self.J[p.waitJ]
            if j.stage != "walk" or j.box:
                continue
            self.crossed += 1
            p.waitJ = None; p.legWait = 0.0; p.onZebra = j.id; p.k = 0; j.zebraPeds += 1

    def step_people(self, dt):
        for p in list(self.people):
            ln, zebra_id, _ = p.legs[p.i]
            if zebra_id is not None and p.pos == 0 and p.onZebra is None:
                p.waitJ = zebra_id; p.wait += dt; p.legWait += dt
                continue
            if p.onZebra is not None:
                p.k += 1
                p.pos = ln * p.k / TICK_STEPS
                fin = p.k >= TICK_STEPS
            else:
                p.pos = p.pos + p.speed * dt
                fin = p.pos >= ln
            if fin:
                if p.onZebra is not None:
                    self.J[p.onZebra].zebraPeds -= 1; p.onZebra = None
                p.i += 1; p.pos = 0.0
                if p.i >= len(p.legs):
                    del self.people[p]

    def entry_for(self, wave):
        weights = [WAVE_SIDE if wave and wave[0] and s.head in wave[0] else 1 for s in self.ENTRIES]
        tot = 0
        for w in weights:
            tot = tot + w
        r = self.rnd() * tot
        for s, w in zip(self.ENTRIES, weights):
            r -= w
            if r < 0:
                return s
        return self.ENTRIES[-1]

    def spawn(self, dt):
        b, wave = busy(self.clock), wave_at(self.clock)
        self.spawnV += dt * b * 0.95 * (WAVE_CARS if wave and wave[0] else 1)
        while self.spawnV >= 1:
            self.spawnV -= 1
            seg = self.entry_for(wave)
            v = self.make_vehicle(self.random_type())
            seg.backlog.append(v)
        for seg in self.ENTRIES:
            if not seg.backlog:
                continue
            v = seg.backlog[0]
            lane = seg.lanes["B" if v.bike else "S"]
            tail = lane[-1] if lane else None
            tailL = seg.lanes["L"][-1] if seg.lanes["L"] else None
            v.seg = seg
            v.move = self.random_move(v.bike)
            want = self.lane_for(v, seg)
            t = tailL if want == "L" else tail
            if t and t.s - t.len < v.len + 3:
                continue
            seg.backlog.pop(0)
            v.lane, v.s = want, 0.0
            v.v = min(v.v0, max(0, t.v) if t else v.v0) * 0.8
            seg.lanes[want].append(v)
            self.vehicles[v] = None
        crowd = wave[1] if wave and wave[1] else 1
        self.spawnP += dt * b * 0.8 * crowd
        while self.spawnP >= 1:
            self.spawnP -= 1
            if len(self.people) < 260 * crowd:
                self.spawn_person()

    # ----- built-in "smart" controller (only used before the server connects)
    def demand(self, j, phase):
        if phase == "W":
            return self.people_waiting(j)
        heads, moves = PHASES[phase]
        n = 0
        for h in heads:
            seg = j.inseg[h]
            for lane in ("L", "S", "B"):
                for v in seg.lanes[lane]:
                    if v.move in moves and seg.len - v.s < 70:
                        n += 1
        return n

    def green_near(self, j):
        heads, moves = PHASES[j.phase]
        n = 0
        for h in heads:
            seg = j.inseg[h]
            for lane in ("L", "S", "B"):
                for v in seg.lanes[lane]:
                    if v.move in moves and seg.len - v.s < 30:
                        n += 1
        return n

    def people_waiting(self, j):
        return sum(1 for p in self.people if p.waitJ == j.id)

    def max_person_wait(self, j):
        m = 0
        for p in self.people:
            if p.waitJ == j.id:
                m = max(m, p.legWait)
        return m

    def _walk_wanted(self, j):
        return self.people_waiting(j) >= 3 or self.max_person_wait(j) > 35

    def next_phase(self, j):
        start = ORDER.index(j.phase)
        for k in range(1, 6):
            ph = ORDER[(start + k) % 5]
            if (self._walk_wanted(j) if ph == "W" else self.demand(j, ph) > 0):
                return ph
        return None

    def wants_to_end(self, j):
        others = any(ph != j.phase and (self._walk_wanted(j) if ph == "W" else self.demand(j, ph) > 0) for ph in ORDER)
        if j.phase == "W":
            return j.t >= 9
        if not others:
            return False
        return j.t >= 30 or (j.t >= 6 and self.green_near(j) == 0)

    def step_light(self, j, dt):
        j.t += dt
        if j.mode == "direct":
            return
        if j.stage == "green":
            if self.wants_to_end(j):
                j.stage, j.t = "yellow", 0.0
        elif j.stage == "walk":
            if self.wants_to_end(j):
                j.stage, j.t = "flash", 0.0
        elif j.stage == "yellow":
            if j.t >= YELLOW:
                j.stage, j.t = "allred", 0.0
        elif j.stage == "flash":
            if j.t >= FLASH:
                j.stage, j.t = "allred", 0.0
        elif j.stage == "allred":
            if j.t >= ALLRED and not j.box and j.zebraPeds == 0:
                ph = self.next_phase(j)
                if ph:
                    j.phase, j.stage, j.t = ph, ("walk" if ph == "W" else "green"), 0.0

    # ----- the step and the tick
    def step(self, dt):
        self.clock = math.fmod(self.clock + dt * 1, 24 * 60)
        self.spawn(dt)
        for j in self.J:
            self.step_light(j, dt)
        if self.tick_step == 0:
            self.start_tick()
        self.tick_step = (self.tick_step + 1) % TICK_STEPS
        self.step_vehicles(dt)
        self.step_people(dt)

    def run_tick(self):
        while True:
            self.step(DT)
            if self.tick_step == 0:
                break

    def set_lights(self, cid, phase):
        j = self.J[cid]
        if j.mode == "direct" and j.phase == phase and j.stage != "allred":
            return
        j.mode, j.request, j.phase, j.stage, j.t = "direct", None, phase, ("walk" if phase == "W" else "green"), 0.0

    def all_red(self, cid):
        j = self.J[cid]
        j.mode, j.request, j.stage, j.t = "direct", None, "allred", 0.0

    def waiting(self):
        return (sum(1 for v in self.vehicles if v.v < 0.3), sum(1 for p in self.people if p.waitJ is not None))

    def decide_state(self, tick):
        crossings = []
        for j in self.J:
            cars = {}
            for side in SIDES:
                seg = j.inseg[SIDE_HEAD[side]]
                q = {}
                for lane in ("L", "S", "B"):
                    n = 0
                    for v in seg.lanes[lane]:
                        if seg.len - v.s <= 80 and v.v < 0.3:
                            n += 1
                    q[lane] = n
                cars[side] = {"left": q["L"], "straight_right": q["S"], "bikes": q["B"]}
            ppl = {s: 0 for s in SIDES}
            for p in self.people:
                if p.waitJ == j.id:
                    ppl[p.legs[p.i][2]] += 1
            crossings.append({"id": j.id, "name": j.name, "lights": None if j.stage == "allred" else j.phase,
                              "ticks": jsround(j.t / TICK), "cars": cars, "people": ppl})
        return {"tick": tick, "clock": fmt_clock(self.clock), "crossings": crossings}


def idm(v, gap, dv, v0):
    s0 = 1.0 if v.bike else 2.0
    s_star = s0 + max(0, v.v * 1.2 + v.v * dv / (2 * math.sqrt(v.a * v.b)))
    x = s_star / max(gap, 0.05)
    return v.a * (1 - (v.v / v0) ** 4 - x * x)


def free_speed(v):
    dist = 1e9 if v.seg.to is None else v.seg.len - v.s
    if v.move and v.move != "S" and dist < 35:
        return min(v.v0, (7 if v.move == "L" else 5.5) + dist * 0.2)
    return v.v0


def cruise_of(v):
    return min(v.v0, {"S": INF, "L": 7, "R": 5.5}[v.move])


def cross_profile(vIn, D, want):
    avg = D / TICK
    far = max(0, 2 * avg - vIn)
    near = avg + 0.3 * (far - avg)
    vc = min(max(near, far), max(min(near, far), want))
    ta = 0 if abs(vc - vIn) < 1e-6 else 2 * (vc * TICK - D) / (vc - vIn)
    return vIn, vc, ta


def run(policy, ticks=270, seed=7, pre_ticks=1, history_len=50, keep_states=True):
    """Warm-up (07:30 -> 09:00), pre_ticks in smart mode, all red, then one policy call per tick (like
    city_server.py + the page's ask()/onTick). Score = the page's live score after `ticks` ticks."""
    city = City(seed)
    i = 0
    while i < 90 / DT:
        city.step(DT)
        i += 1
    for _ in range(pre_ticks):
        city.run_tick()
    for j in city.J:
        city.all_red(j.id)
    hist, states, per_tick = [], [], []
    score, last = 0.0, city.crossed
    for n in range(1, ticks + 1):
        cur = city.decide_state(n)
        lights = {str(k): v for k, v in (policy(hist[-history_len:], cur) or {}).items()}
        if keep_states:
            states.append(json.loads(json.dumps(cur)))
        cur["lights_chosen"] = lights
        hist.append(cur)
        del hist[:-500]
        for k, ph in lights.items():
            city.set_lights(int(k), ph)
        city.run_tick()
        wv, wp = city.waiting()
        across = city.crossed - last
        last = city.crossed
        pts = jsround((across - 0.2 * (wv + wp)) * 10) / 10
        score = jsround((score + pts) * 10) / 10
        per_tick.append({"tick": n, "pts": pts, "score": score, "across": across, "wv": wv, "wp": wp})
    return {"score": score, "states": states, "ticks": per_tick}
