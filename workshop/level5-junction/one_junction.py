"""
Level 5, the simple start: ONE junction, ONE officer. Cars drive on the right (like Taiwan).

THE ROADS. Four roads come in: top, right, bottom, left. Each road is 20 blocks long and has
4 lanes: [left-turn lane, straight lane, straight lane, right-turn lane].

    top: [[0,0,0,0], [1,0,0,0], ... , [0,2,1,0]]
          ^ block 1, far away           ^ block 20, at the stop line

Each number is how many cars are in that lane on that block. Every tick every car moves
1 block closer. A car that reaches the stop line on red waits there, and the cars behind it
add up: [3, 0, 0, 0, 1] becomes [0, 3, 0, 0, 1] and then 4 cars wait at the line.
On green, 1 car per lane crosses per tick. So the officer can SEE the cars coming.

PEOPLE wait at each road to walk across it. On walk: 3 cross per tick (2 in the rain);
in the rush hours the crossing is busier: 5 per tick (4 in the rain).

THE OFFICER decides, every tick, for every road:

    "left": {"light": [1, 0, 0, 0], "people": 0}   only the left-turn lane is green
    "left": {"light": [0, 1, 1, 0], "people": 0}   only straight is green
    "top":  {"light": [0, 0, 0, 0], "people": 1}   all lanes red, people walk across the top road

CRASHES. Nothing stops the officer from a bad plan, but cars that cross on conflicting lights
crash (-20 points), and a car that drives through people who are walking hits them (-50):
  - a left turn and the straight from the opposite road
  - straight or left turn, with straight or left turn from a road on the side
  - two moves that go into the same road
  - a car crossing a road where people walk (coming from that road, or turning into it)

THE TRAFFIC LIGHT runs a fixed cycle of safe phases:
    1 top/bottom straight + right -> 2 top/bottom left turns -> 3 right/left straight + right
    -> 4 right/left left turns -> 5 people walk -> 1 ...
JEV only decides the TIMING: every tick, one yes/no question "switch to the next phase now?".
A phase stays green at least 1 tick and at most 6 ticks (in code). Crashes cannot happen.
Compare: a fixed timer (every phase 3 ticks) and timing rules. The random officer sets every
road on its own (and crashes).

POINTS per tick: +1 per car that crosses, +1 per person that crosses,
                 -1 per car stuck at a stop line (it did not move this tick),
                 -2 per stuck car in the rush hours (people are late for work),
                 -0.1 per person waiting.

TRAFFIC follows the clock (1 tick = 10 minutes). The city centre is to the LEFT:
    07:00-09:00 morning peak: many cars from the right, driving into the city
    17:00-19:00 evening peak: many cars from the left, people go home
    22:00-06:00 night: few cars, few people
Rain comes and goes (decided by the seed). Same seed = same traffic.

    python level5-junction/one_junction.py --officer random          # 3 days from 00:00
    python level5-junction/one_junction.py --officer rules
    python level5-junction/one_junction.py --officer jev --show 1,10
Then open level5-junction/one_junction.html to watch the runs.
"""
import argparse
import itertools
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev import JevError, choice, decide, noul  # noqa: E402

SIDES = ["top", "right", "bottom", "left"]
LANE_MOVE = ["L", "S", "S", "R"]  # left turn, straight, straight, right turn
MOVE_NAME = {"L": "left turn", "S": "straight", "R": "right turn"}
BLOCKS = 20
CAR_SPEED = 1  # blocks per tick
MINUTES_PER_TICK = 10
TICKS_PER_DAY = 24 * 60 // MINUTES_PER_TICK  # 144
PEOPLE_PER_TICK = {"dry": 3, "rain": 2}  # +2 in the rush hours
RUSH_EXTRA_PEOPLE = 2
POINTS = {"car": 1, "person": 1, "stuck_car": -1, "stuck_car_rush": -2, "waiting_person": -0.1,
          "crash": -20, "hit_person": -50}
RUNS_DIR = Path(os.environ.get("JUNCTION_RUNS_DIR") or Path(__file__).resolve().parent / "runs")
KEEP_IN_VIEWER = 10

# Light patterns for the 4 lanes of one road [left, straight, straight, right]
PATTERNS = {
    "red": [0, 0, 0, 0],
    "left": [1, 0, 0, 0],
    "straight": [0, 1, 1, 0],
    "right": [0, 0, 0, 1],
    "straight_right": [0, 1, 1, 1],
    "left_straight": [1, 1, 1, 0],
    "left_right": [1, 0, 0, 1],
    "all": [1, 1, 1, 1],
}


# ----- traffic rules ---------------------------------------------------------------------------

def exit_road(side, move):
    """Where a move goes. Driving on the right: from the top, a left turn goes to the right road."""
    i = SIDES.index(side)
    return SIDES[(i + {"L": 1, "S": 2, "R": 3}[move]) % 4]


def conflict(a, b):
    """Do two moves (side, move) crash when both have a car crossing in the same tick?"""
    (sa, ma), (sb, mb) = a, b
    if sa == sb:
        return False  # lanes of the same road never cross each other
    if exit_road(sa, ma) == exit_road(sb, mb):
        return True  # both go into the same road
    if (SIDES.index(sb) - SIDES.index(sa)) % 4 == 2:  # opposite roads
        return {ma, mb} == {"L", "S"}
    return "R" not in (ma, mb)  # side roads: straight and left turns cross each other


def crosses_walk(move, road):
    """Does a car on this move drive over the crosswalk of `road`?"""
    side, m = move
    return side == road or exit_road(side, m) == road


def safe(decision):
    """True when no two green moves can crash and no green move drives through open crosswalks."""
    moves = [(s, LANE_MOVE[k]) for s in SIDES for k in range(4) if decision[s]["light"][k]]
    if any(conflict(a, b) for a, b in itertools.combinations(set(moves), 2)):
        return False
    return not any(decision[r]["people"] and crosses_walk(m, r) for m in moves for r in SIDES)


# ----- traffic by the clock --------------------------------------------------------------------

def period(minute):
    hour = (minute // 60) % 24
    if 7 <= hour < 9:
        return "morning peak"
    if 17 <= hour < 19:
        return "evening peak"
    if hour >= 22 or hour < 6:
        return "night"
    return "day"


PERIOD_HINT = {"morning peak": "many cars from the right, driving into the city",
               "evening peak": "many cars from the left, people go home",
               "day": "normal traffic", "night": "few cars, few people"}
# new cars per tick, on average, per road [top, right, bottom, left]
CARS = {"morning peak": [0.45, 1.26, 0.45, 0.36], "evening peak": [0.45, 0.36, 0.45, 1.26],
        "day": [0.45, 0.45, 0.45, 0.45], "night": [0.09, 0.09, 0.09, 0.09]}
PEOPLE = {"morning peak": 0.6, "evening peak": 0.6, "day": 0.3, "night": 0.05}  # per road per tick
LANE_SHARE = [0.2, 0.3, 0.3, 0.2]  # left turn, straight, straight, right turn


def poisson(rng, mean):
    n, p, limit = 0, 1.0, 2.718281828 ** -mean
    while True:
        p *= rng.random()
        if p < limit:
            return n
        n += 1


class Junction:
    def __init__(self, seed, start="07:00"):
        self.rng = random.Random(seed)
        h, m = map(int, start.split(":"))
        self.minute = h * 60 + m
        self.rain = self.rng.random() < 0.3
        self.lanes = {s: [[] for _ in range(4)] for s in SIDES}  # cars: {"id", "pos"}; pos 0..19
        self.people = {s: 0 for s in SIDES}
        self.decision = {s: {"light": [0, 0, 0, 0], "people": 0} for s in SIDES}
        self.next_id = 1
        self.t = 0
        self.score = 0.0
        self.history = []
        for pos in range(BLOCKS - 1):  # the roads are not empty when we start
            self.spawn(pos)

    def clock(self):
        return f"{(self.minute // 60) % 24:02d}:{self.minute % 60:02d}"

    def weather(self):
        return "rain" if self.rain else "dry"

    def rush(self):
        return period(self.minute) in ("morning peak", "evening peak")

    def people_per_tick(self):
        return PEOPLE_PER_TICK[self.weather()] + (RUSH_EXTRA_PEOPLE if self.rush() else 0)

    def spawn(self, pos=0):
        p = period(self.minute)
        for i, side in enumerate(SIDES):
            for _ in range(poisson(self.rng, CARS[p][i])):
                lane = self.rng.choices(range(4), LANE_SHARE)[0]
                self.lanes[side][lane].append({"id": self.next_id, "pos": pos})
                self.next_id += 1
            if pos == 0:
                self.people[side] += poisson(self.rng, PEOPLE[p])

    def cars(self, side):
        """The road as the officer sees it: 20 blocks, each [left, straight, straight, right]."""
        road = [[0, 0, 0, 0] for _ in range(BLOCKS)]
        for k, lane in enumerate(self.lanes[side]):
            for car in lane:
                road[car["pos"]][k] += 1
        return road

    def waiting_cars(self, side=None):
        sides = [side] if side else SIDES
        return sum(1 for s in sides for lane in self.lanes[s] for c in lane if c["pos"] == BLOCKS - 1)

    def queues(self):
        """Cars waiting at the stop line, per road, per lane."""
        return {s: [sum(1 for c in lane if c["pos"] == BLOCKS - 1) for lane in self.lanes[s]] for s in SIDES}

    def snapshot(self):
        return {"t": self.t + 1, "time": self.clock(), "weather": self.weather(), "period": period(self.minute),
                "cars": [[c["id"], i, k, c["pos"]] for i, s in enumerate(SIDES)
                         for k, lane in enumerate(self.lanes[s]) for c in lane],
                "people": [self.people[s] for s in SIDES], "score": self.score}

    def step(self, decision):
        decision = normalize(decision)
        crossed = []  # (car id, side, lane)
        for side in SIDES:
            for k, lane in enumerate(self.lanes[side]):
                front = [c for c in lane if c["pos"] == BLOCKS - 1]
                if decision[side]["light"][k] and front:
                    lane.remove(front[0])  # the first car in the queue crosses
                    crossed.append((front[0]["id"], side, k))
        walked = {}
        for side in SIDES:
            if decision[side]["people"] and self.people[side]:
                walked[side] = min(self.people[side], self.people_per_tick())
                self.people[side] -= walked[side]

        moving = sorted({(s, LANE_MOVE[k]) for _, s, k in crossed})
        crashes = []
        for a, b in itertools.combinations(moving, 2):
            if conflict(a, b):
                crashes.append({"kind": "cars", "moves": [list(a), list(b)], "points": POINTS["crash"]})
        for m in moving:
            for road in walked:
                if crosses_walk(m, road):
                    crashes.append({"kind": "person", "moves": [list(m)], "road": road, "points": POINTS["hit_person"]})
        crashed = {tuple(m) for c in crashes for m in c["moves"]}
        hit_roads = {c["road"] for c in crashes if c["kind"] == "person"}

        cars_ok = sum(1 for _, s, k in crossed if (s, LANE_MOVE[k]) not in crashed)
        stuck = self.waiting_cars()  # still at the stop line after the green ones left: they did not move
        stuck_by_road = {s: self.waiting_cars(s) for s in SIDES}
        people_ok = sum(n for road, n in walked.items() if road not in hit_roads)
        for lane in (lane for s in SIDES for lane in self.lanes[s]):
            for car in lane:
                car["pos"] = min(BLOCKS - 1, car["pos"] + CAR_SPEED)  # the queue at the stop line adds up
        self.spawn()
        stuck_points = POINTS["stuck_car_rush" if self.rush() else "stuck_car"]
        waiting_people = sum(self.people.values())
        points = round(cars_ok * POINTS["car"] + people_ok * POINTS["person"] + stuck * stuck_points
                       + waiting_people * POINTS["waiting_person"] + sum(c["points"] for c in crashes), 2)
        self.score = round(self.score + points, 2)
        self.history.append({"t": self.t + 1, "time": self.clock(), "weather": self.weather(), "decision": decision,
                             "crossed": [list(c) for c in crossed], "walked": walked, "crashes": crashes,
                             "cars_crossed": cars_ok, "people_crossed": people_ok, "stuck_cars": stuck, "stuck_by_road": stuck_by_road,
                             "waiting_people": waiting_people,
                             "points": points, "score": self.score})
        self.decision = decision
        self.t += 1
        self.minute += MINUTES_PER_TICK
        if self.minute % 60 == 0 and self.rng.random() < 0.3:  # the weather can change every hour
            self.rain = not self.rain
        return points


def normalize(decision):
    """Every road gets a light [l, s, s, r] of 0/1 and people 0/1 (missing = red / no walk)."""
    out = {}
    for s in SIDES:
        d = decision.get(s) or {}
        light = [1 if x else 0 for x in (d.get("light") or [0, 0, 0, 0])]
        if len(light) != 4:
            raise ValueError(f"{s}: a light needs 4 lanes [left, straight, straight, right], got {light}")
        out[s] = {"light": light, "people": 1 if d.get("people") else 0}
    return out


# ----- officers --------------------------------------------------------------------------------

class RandomOfficer:
    name = "random"

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def act(self, j):
        return {s: {"light": self.rng.choice(list(PATTERNS.values())), "people": self.rng.random() < 0.3}
                for s in SIDES}, None


def _plan(lights, walk=()):
    return {s: {"light": lights.get(s, [0, 0, 0, 0]), "people": int(s in walk)} for s in SIDES}


# The whole junction at once. All of them are safe: no two moves can crash (see safe()).
PLANS = {
    "top_bottom_go": (_plan({"top": [0, 1, 1, 1], "bottom": [0, 1, 1, 1]}),
                      "top and bottom: straight and right turn green; everything else red"),
    "top_bottom_straight_people_walk": (
        _plan({"top": [0, 1, 1, 0], "bottom": [0, 1, 1, 0]}, walk=("right", "left")),
        "top and bottom: straight green; people walk across the right and left roads"),
    "top_bottom_left_turns": (_plan({"top": [1, 0, 0, 0], "bottom": [1, 0, 0, 0], "right": [0, 0, 0, 1],
                                     "left": [0, 0, 0, 1]}),
                              "top and bottom: left turn green; right and left: right turn green"),
    "right_left_go": (_plan({"right": [0, 1, 1, 1], "left": [0, 1, 1, 1]}),
                      "right and left: straight and right turn green; everything else red"),
    "right_left_straight_people_walk": (
        _plan({"right": [0, 1, 1, 0], "left": [0, 1, 1, 0]}, walk=("top", "bottom")),
        "right and left: straight green; people walk across the top and bottom roads"),
    "right_left_left_turns": (_plan({"right": [1, 0, 0, 0], "left": [1, 0, 0, 0], "top": [0, 0, 0, 1],
                                     "bottom": [0, 0, 0, 1]}),
                              "right and left: left turn green; top and bottom: right turn green"),
    "everyone_walks": (_plan({}, walk=SIDES), "all cars red; people walk across all four roads"),
    "all_red": (_plan({}), "all cars red, nobody walks"),
}


def plans():
    return [p for p, _ in PLANS.values()]


class RulesOfficer:
    """Simple rules: the safe plan that gives green to the longest queues (and to waiting people)."""
    name = "rules"

    def act(self, j):
        def pressure(plan):
            cars = sum(1 for s in SIDES for k in range(4) if plan[s]["light"][k]
                       for c in j.lanes[s][k] if c["pos"] == BLOCKS - 1)
            people = sum(j.people[s] for s in SIDES if plan[s]["people"])
            return cars + people / 2
        return max(plans(), key=pressure), None


def road_text(road):
    return json.dumps(road, separators=(",", ":"))


def decision_text(decision):
    return " ".join(f"{s} {road_text(decision[s]['light'])}{' walk' if decision[s]['people'] else ''}" for s in SIDES)


HISTORY_KEY = ("one line per past tick: t = tick | lights of top right bottom left, each 4 digits "
               "[left, straight, straight, right], 1 = green, w = people walk | cars crossed c, people crossed p "
               "| stuck cars per road (top right bottom left) | people waiting | crashes: L/S/R = left turn, "
               "straight, right turn | points")


def history_line(h):
    """One past tick in about 40 tokens (see HISTORY_KEY): Jev reads up to 400 of them in one call."""
    d = h["decision"]
    lights = " ".join("".join(map(str, d[s]["light"])) + ("w" if d[s]["people"] else "") for s in SIDES)
    crash = " ".join(f"CRASH {' x '.join(f'{m[0]} {m[1]}' for m in c['moves'])} {c['points']}" if c["kind"] == "cars"
                     else f"HIT PEOPLE {c['road']} by {c['moves'][0][0]} {c['moves'][0][1]} {c['points']}"
                     for c in h["crashes"])
    stuck = " ".join(str(n) for n in h["stuck_by_road"].values())
    return (f"t{h['t']} | {lights} | {h['cars_crossed']}c {h['people_crossed']}p | stuck {stuck} | "
            f"wait {h['waiting_people']}{' | ' + crash if crash else ''} | {h['points']:+.1f}")


# ----- the traffic light: a fixed cycle, the officer only decides when to switch ------------------

CYCLE = [("top_bottom_go", "top/bottom straight + right turn"),
         ("top_bottom_left_turns", "top/bottom left turns (+ right/left right turns)"),
         ("right_left_go", "right/left straight + right turn"),
         ("right_left_left_turns", "right/left left turns (+ top/bottom right turns)"),
         ("everyone_walks", "people walk across all four roads")]
MIN_GREEN, MAX_GREEN = 1, 6


def phase_load(j, n):
    """Phase n right now: cars waiting at its green stop lines, cars arriving there in the next 3 blocks,
    and (for the walk phase) people waiting."""
    plan = PLANS[CYCLE[n][0]][0]
    q = j.queues()
    waiting = sum(q[s][k] for s in SIDES for k in range(4) if plan[s]["light"][k])
    coming = sum(j.cars(s)[p][k] for s in SIDES for k in range(4) if plan[s]["light"][k]
                 for p in range(BLOCKS - 4, BLOCKS - 1))
    people = sum(j.people[s] for s in SIDES if plan[s]["people"])
    return waiting, coming, people


class TimingOfficer:
    """The cycle and the min / max green are in code. Subclasses only answer: switch now?"""
    name = "timing"

    def __init__(self):
        self.phase, self.green_for = 0, 0

    def switch(self, j):
        raise NotImplementedError

    def act(self, j):
        info = None
        if self.green_for >= MAX_GREEN:
            go = True
        elif self.green_for < MIN_GREEN:
            go = False
        else:
            go, info = self.switch(j)
        if go:
            self.phase, self.green_for = (self.phase + 1) % len(CYCLE), 0
        self.green_for += 1
        return PLANS[CYCLE[self.phase][0]][0], info


class FixedTimer(TimingOfficer):
    """Every phase 3 ticks, whatever the traffic."""
    name = "fixed timer"

    def switch(self, j):
        return self.green_for >= 3, None


class TimingRules(TimingOfficer):
    """Switch when the green phase has nothing left, or much more waits at red."""
    name = "timing rules"

    def switch(self, j):
        waiting, coming, people = phase_load(j, self.phase)
        green = waiting + people
        red = sum(sum(phase_load(j, n)[::2]) for n in range(len(CYCLE)) if n != self.phase)
        return green == 0 or red > 3 * green, None


class JevOfficer(TimingOfficer):
    """Jev decides the timing: one yes/no question per tick."""
    name = "jev"

    def __init__(self, history=10, memory=False):
        super().__init__()
        self.history = history  # past ticks in the request
        self.past, self.pending = [], None
        self.memory = memory  # add a summary of Jev's own past decisions and what followed
        self.decisions = []  # (tick index, cars waiting on green, switched?)
        if memory:
            self.name = "jev + memory"

    @staticmethod
    def bucket(cars):
        return "0 cars" if cars == 0 else "1-4 cars" if cars < 5 else "5+ cars"

    def memory_lines(self, j, waiting_now):
        """Jev's own past decisions, grouped by how many cars still waited on green, with the points
        of the 3 ticks that followed (the decision tick and the 2 after it)."""
        done = [(i, w, sw) for i, w, sw in self.decisions if i + 3 <= len(j.history)]
        if not done:
            return []
        lines = ["", f"YOUR PAST DECISIONS ({len(done)} so far) and the points of the 3 ticks that followed:"]
        for b in ("0 cars", "1-4 cars", "5+ cars"):
            for sw in (True, False):
                outcomes = [sum(h["points"] for h in j.history[i:i + 3]) for i, w, s_ in done
                            if self.bucket(w) == b and s_ == sw]
                if outcomes:
                    lines.append(f"  {b} still waiting on green, you {'switched' if sw else 'kept green'}: "
                                 f"{len(outcomes)} times, average {sum(outcomes) / len(outcomes):+.1f} points")
        lines.append(f"Now: {self.bucket(waiting_now)} still waiting on green.")
        return lines

    def state(self, j):
        w, c, p = phase_load(j, self.phase)
        nxt = (self.phase + 1) % len(CYCLE)
        nw, nc, np_ = phase_load(j, nxt)
        others = [phase_load(j, n) for n in range(len(CYCLE)) if n not in (self.phase, nxt)]
        stuck = POINTS["stuck_car_rush" if j.rush() else "stuck_car"]
        lines = [
            "A TRAFFIC LIGHT at one junction. It runs a fixed cycle of phases: "
            + " -> ".join(f"{i + 1} {text}" for i, (_, text) in enumerate(CYCLE)) + " -> 1 ...",
            f"Switching always goes to the next phase. A phase stays green at most {MAX_GREEN} ticks.",
            f"Time {j.clock()} ({period(j.minute)}: {PERIOD_HINT[period(j.minute)]}). Weather: {j.weather()}. "
            f"One tick is {MINUTES_PER_TICK} minutes.",
            f"POINTS per tick: +1 per car or person that crosses; {stuck} per car waiting at a red light "
            "(it does not move); -0.1 per person waiting. On green, 1 car per lane crosses per tick.",
            "",
            f"NOW: phase {self.phase + 1} ({CYCLE[self.phase][1]}), green for {self.green_for} ticks.",
            f"  green now: {w} cars waiting at its lights, {c} more arriving in the next 3 blocks"
            + (f", {p} people waiting to walk" if self.phase == 4 else "") + ".",
            f"  next phase {nxt + 1} ({CYCLE[nxt][1]}): {nw} cars waiting, {nc} arriving"
            + (f", {np_} people waiting" if nxt == 4 else "") + ".",
            f"  the other phases: {sum(o[0] for o in others)} cars waiting"
            + (f", {sum(o[2] for o in others)} people waiting" if 4 not in (self.phase, nxt) else "") + ".",
            f"Score so far: {j.score}.",
        ]
        if self.past:
            lines += ["", f"LAST {len(self.past)} TICKS (what the light did, the points of that tick):"]
            lines += self.past
        if self.memory:
            lines += self.memory_lines(j, w)
        return "\n".join(lines)

    QUESTION = ("Switch the light to the next phase now? Yes when the green phase has few cars left and more "
                "cars wait at red, above all in the next phase. No while the green phase still moves many cars.")

    def switch(self, j):
        state = self.state(j)
        questions = {"switch": noul(self.QUESTION, yes="switch to the next phase now",
                                    no="keep the green phase one more tick")}
        result = decide(state=state, questions=questions)
        p = result["answers"]["switch"]["noul"]
        self.decisions.append((j.t, phase_load(j, self.phase)[0], p > 0.5))
        return p > 0.5, {"calls": [{"road": "junction", "state": state, "questions": questions, "result": result}],
                         "tokens": result["usage"]["input_tokens"], "p": p}

    def act(self, j):
        if self.pending and j.history:  # what the last decision earned
            self.past.append(f"{self.pending}, points {j.history[-1]['points']:+.1f}")
            self.past = self.past[-self.history:]
        before = self.phase
        decision, info = super().act(j)
        self.pending = (f"t{j.t + 1}: switched {before + 1} -> {self.phase + 1}" if self.phase != before
                        else f"t{j.t + 1}: kept phase {self.phase + 1}")
        return decision, info


OFFICERS = {"random": RandomOfficer, "rules": RulesOfficer, "fixed": FixedTimer, "timing": TimingRules,
            "jev": JevOfficer}


# ----- the game loop ---------------------------------------------------------------------------

def play(officer, seed=2026, ticks=10, start="07:00", show=(), out=print):
    j = Junction(seed, start)
    frames, tokens = [], 0
    for _ in range(ticks):
        frame = j.snapshot()
        decision, info = officer.act(j)
        if info:
            tokens += info["tokens"]
            if j.t + 1 in show:
                for c in info["calls"]:
                    out(f"\n--- tick {j.t + 1}: what we send to Jev ---\nSTATE:\n{c['state']}\n"
                        f"QUESTIONS:\n{json.dumps(c['questions'], indent=1)}\n"
                        f"JEV ANSWERS:\n{json.dumps(c['result']['answers'], indent=1)}")
        j.step(decision)
        h = j.history[-1]
        frames.append({**frame, "decision": h["decision"], "crossed": h["crossed"], "walked": h["walked"],
                       "crashes": h["crashes"], "points": h["points"], "score_after": h["score"]})
        out(f"t{h['t']:<3} {frame['time']} {frame['weather']:<4} waiting cars {j.waiting_cars():>2} "
            f"people {sum(frame['people']):>2} | {decision_text(h['decision'])} | "
            f"{h['cars_crossed']} cars {h['people_crossed']} people"
            f"{' | ' + str(len(h['crashes'])) + ' CRASH' if h['crashes'] else ''}  {h['points']:+.1f}  score {j.score}")
    frames.append(j.snapshot())  # where everything ends up
    return j, frames, tokens


def per_day(j):
    """Points per day (144 ticks): if the officer learns, later days should score better."""
    return [round(sum(h["points"] for h in j.history[d:d + TICKS_PER_DAY]), 1)
            for d in range(0, len(j.history), TICKS_PER_DAY)]


def save_run(officer_name, seed, start, j, frames, tokens):
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    n = len(list(RUNS_DIR.glob("one-*.json"))) + 1
    run = {"run": n, "officer": officer_name, "seed": seed, "start": start, "ticks": j.t, "score": j.score,
           "crashes": sum(len(h["crashes"]) for h in j.history), "tokens": tokens, "blocks": BLOCKS,
           "sides": SIDES, "frames": frames}
    (RUNS_DIR / f"one-{n:03d}.json").write_text(json.dumps(run, separators=(",", ":")))
    runs = [json.loads(f.read_text()) for f in sorted(RUNS_DIR.glob("one-*.json"))[-KEEP_IN_VIEWER:]]
    (RUNS_DIR / "one_runs.js").write_text("window.ONE_JUNCTION_RUNS = " + json.dumps(runs, separators=(",", ":")) + ";\n")
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--officer", default="random", choices=sorted(OFFICERS))
    ap.add_argument("--ticks", type=int, default=TICKS_PER_DAY * 3, help="1 tick = 10 minutes (default: 3 days)")
    ap.add_argument("--history", type=int, default=10, help="past ticks in Jev's request (default 10)")
    ap.add_argument("--memory", action="store_true", help="Jev also reads a summary of its own past decisions")
    ap.add_argument("--start", default="00:00", help="clock time of the first tick, HH:MM")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--show", default="1", help="ticks whose Jev requests to print, e.g. 1,10")
    args = ap.parse_args()
    show = {int(x) for x in args.show.split(",") if x}
    officer = (JevOfficer(args.history, memory=args.memory) if args.officer == "jev"
               else OFFICERS[args.officer]())
    print(f"=== one junction, officer {officer.name}, {args.ticks} ticks from {args.start}, seed {args.seed} ===")
    j, frames, tokens = play(officer, args.seed, args.ticks, args.start, show)
    n = save_run(officer.name, args.seed, args.start, j, frames, tokens)
    crashes = sum(len(h["crashes"]) for h in j.history)
    print(f"\nScore: {j.score}   crashes: {crashes}" + (f"   Jev input tokens: {tokens}" if tokens else ""))
    print("Per day: " + "   ".join(f"day {d + 1}: {points:+.1f}" for d, points in enumerate(per_day(j))))
    for name, other in (("fixed timer", FixedTimer()), ("timing rules", TimingRules()), ("rules", RulesOfficer()),
                        ("random", RandomOfficer())):
        if name != officer.name:
            o, _, _ = play(other, args.seed, args.ticks, args.start, out=lambda *_: None)
            print(f"  {name} officer on the same traffic: score {o.score}, "
                  f"crashes {sum(len(h['crashes']) for h in o.history)}, per day {per_day(o)}")
    print(f"Saved as run {n}. Watch it: open level5-junction/one_junction.html")


if __name__ == "__main__":
    main()
