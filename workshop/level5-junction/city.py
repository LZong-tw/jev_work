"""
The city: three junctions on Zhongxiao E. Rd, Da'an District, Taipei (map "three").

              Fuxing S. Rd       Dunhua S. Rd       Guangfu S. Rd
                   |                  |                  |
   Zhongxiao E. Rd-+------------------+------------------+-----
                   |                  |                  |

One run is ONE STREAM of ticks (200 by default), no days. The busy direction changes in
waves every 40 ticks, so situations come back and the past can teach the future.
Other maps: single (1 junction), corridor (2), grid (2 x 2).

This file is the WORLD. It owns all the rules. The officer only picks, for every
junction, which way the light is green.

ROADS
  Every road between two junctions (and every road into the city) is a lane of
  LENGTH cells, one lane per direction. Vehicles drive on the right.
  A full road blocks the junction before it (spillback): a jam can spread.

VEHICLES (dynamic speed, "Nagel-Schreckenberg" model, every tick):
  1. speed up       speed = min(speed + accel, max speed)
  2. keep distance  never drive into the vehicle ahead or through a red light
  3. dawdle         sometimes slow down by 1 for no reason (more often in rain)
  4. move           position += speed
  Turning vehicles slow down to 1 cell per tick when they cross the junction.
  Rain lowers the max speed by 1 (not for ambulances).
  Everybody makes way for an AMBULANCE: it passes other vehicles. Only a red light stops it.

            accel  max speed  points when it crosses a junction
  scooter     2       3         +1
  car         1       3         +1
  bus         1       2         +3  (many people inside)
  ambulance   2       4         +5

TRAFFIC LIGHT per junction (a state machine):
  NS / EW / WALK. Changing it costs one YELLOW tick where nothing crosses.
  After the yellow tick the new phase runs at least 1 tick (minimum green).
  One vehicle per approach crosses per tick (green only), and a road accepts
  one new vehicle per tick from the junction behind it.

ENERGY per junction per tick: one unit for every idling (stopped) vehicle, also the ones
  waiting to enter the city. It is reported next to the score: less is better.

POINTS per junction per tick (see POINTS below)
  + vehicles that cross (see table); pedestrians who cross give no points, but stop the waiting penalty
  - 0.05 per stopped vehicle on its approaches (also vehicles waiting to enter the city)
  - 0.1  per waiting pedestrian
  - 1    per vehicle stopped for more than 10 ticks (angry honking)
  - 10   if an ambulance is stopped on one of its approaches
"""
import math
import random

TICKS = 200  # one stream of ticks (no days): the default length of a run
LENGTH = 10
VISION = 6  # an officer sees this many cells down each road from the stop line (about 6 cars, ~45 m)
DIRS = ["north", "south", "east", "west"]
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
STEP = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
AXIS = {"north": "NS", "south": "NS", "east": "EW", "west": "EW"}
# heading after a turn (driving on the right)
RIGHT = {"south": "west", "west": "north", "north": "east", "east": "south"}
LEFT = {v: k for k, v in RIGHT.items()}

ACTIONS = {
    "north_south": "green for the north-south road: vehicles from north and south go",
    "east_west": "green for the east-west road: vehicles from east and west go",
    "walk": "all vehicles stop, pedestrians cross on all four sides",
}
PHASE = {"north_south": "NS", "east_west": "EW", "walk": "WALK"}
ACTION_OF = {v: k for k, v in PHASE.items()}

KINDS = {
    "scooter": {"accel": 2, "vmax": 3, "value": 1, "symbol": "s"},
    "car": {"accel": 1, "vmax": 3, "value": 1, "symbol": "c"},
    "bus": {"accel": 1, "vmax": 2, "value": 3, "symbol": "B"},
    "ambulance": {"accel": 2, "vmax": 4, "value": 5, "symbol": "A"},
}
SYMBOL = {k: v["symbol"] for k, v in KINDS.items()}
TURNS = {"straight": 0.6, "right": 0.25, "left": 0.15}

# Points per junction per tick. "crossed" is already weighted by vehicle type (bus = 3 ...).
POINTS = {
    "crossed": 1.0,
    "walked": 0.0,
    "stopped": -0.05,
    "pedestrians_waiting": -0.1,
    "angry": -1.0,
    "ambulance_stopped": -10.0,
}
ANGRY_AFTER = 10

MAPS = {
    "three": {"cols": ["Fuxing S. Rd", "Dunhua S. Rd", "Guangfu S. Rd"], "rows": ["Zhongxiao E. Rd"]},
    "single": {"cols": ["Fuxing S. Rd"], "rows": ["Zhongxiao E. Rd"]},
    "corridor": {"cols": ["Fuxing S. Rd", "Dunhua S. Rd"], "rows": ["Zhongxiao E. Rd"]},
    "grid": {"cols": ["Fuxing S. Rd", "Dunhua S. Rd"], "rows": ["Zhongxiao E. Rd", "Ren'ai Rd"]},
}
DEFAULT_MAP = "three"
WAVE = 40  # the busy direction changes every 40 ticks: side streets, then Zhongxiao, then both
RAIN_LENGTH = 40


def slug(road):
    return "".join(ch for ch in road.split()[0].lower() if ch.isalpha())


def poisson(rng, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


class Junction:
    def __init__(self, jid, x, y, ns_road, ew_road):
        self.id, self.x, self.y = jid, x, y
        self.ns_road, self.ew_road = ns_road, ew_road
        self.name = f"{ns_road} x {ew_road}"
        self.light = "NS"
        self.yellow = False
        self.locked = 0
        self.green_for = 0
        self.pedestrians = []  # wait times

    def allows(self, side):
        return not self.yellow and self.light == AXIS[side]


class Segment:
    """A one-lane road that ends at junction `to`. Vehicles enter at cell 0, the stop line is cell LENGTH-1."""

    def __init__(self, to, side, source):
        self.id = f"{to}<{side}"
        self.to, self.side, self.source = to, side, source  # source: junction id, or None = city edge
        self.cars = []  # front (closest to the stop line) first
        self.received = False  # a road accepts one vehicle per tick from the junction behind it

    def room(self):
        """Free cells at the start of the road (ambulances do not count: others make way for them)."""
        return min((v["pos"] for v in self.cars if v["kind"] != "ambulance"), default=LENGTH)


class City:
    def __init__(self, seed, map_name=DEFAULT_MAP, ticks=TICKS, ambulances=True, pedestrians=True):
        if map_name not in MAPS:
            raise ValueError(f"unknown map {map_name!r}, choose from {sorted(MAPS)}")
        self.seed, self.map, self.ticks = seed, map_name, ticks
        self.with_ambulances, self.with_pedestrians = ambulances, pedestrians  # off = a simpler game
        # Two random streams: the WORLD (who arrives, when, rain) and DRIVING (dawdling, turns).
        # Arrivals never depend on the officer's choices, so a replay with another move
        # sees exactly the same traffic arriving. That makes fair "what if" comparisons.
        self.rng = random.Random(seed)
        self.drive = random.Random(seed * 7919 + 1)
        layout = MAPS[map_name]
        self.junctions = {}
        for y, ew_road in enumerate(layout["rows"]):
            for x, ns_road in enumerate(layout["cols"]):
                jid = f"{slug(ns_road)}_{slug(ew_road)}"
                self.junctions[jid] = Junction(jid, x, y, ns_road, ew_road)
        self.at = {(j.x, j.y): j.id for j in self.junctions.values()}
        self.segments = {}
        for j in self.junctions.values():
            for side in DIRS:
                dx, dy = STEP[side]
                seg = Segment(j.id, side, self.at.get((j.x + dx, j.y + dy)))
                self.segments[seg.id] = seg
        self.entries = [s for s in self.segments.values() if s.source is None]
        self.backlog = {s.id: [] for s in self.entries}  # vehicles waiting to enter the city
        self.t = 0
        self.score = 0.0
        self.energy = 0  # idling: one unit per stopped vehicle per tick (fuel burned while waiting)
        self.next_id = 1
        self.trips = []  # ticks each finished trip took
        # weather: dry, or one rain shower of RAIN_LENGTH ticks that starts at some point
        self.rain_from = self.rng.choice([None, self.rng.randint(10, max(11, int(ticks * 0.6)))])
        self.last = {}

    # ----- small helpers ---------------------------------------------------------
    def raining(self):
        return self.rain_from is not None and self.rain_from <= self.t < self.rain_from + RAIN_LENGTH

    def vmax(self, kind):
        v = KINDS[kind]["vmax"]
        return v if kind == "ambulance" or not self.raining() else max(1, v - 1)

    def incoming(self, jid):
        return [self.segments[f"{jid}<{side}"] for side in DIRS]

    def target(self, seg, turn):
        """Where a vehicle goes after crossing: (next road or None = leaves the city, new heading)."""
        heading = OPPOSITE[seg.side]
        if turn == "right":
            heading = RIGHT[heading]
        elif turn == "left":
            heading = LEFT[heading]
        j = self.junctions[seg.to]
        dx, dy = STEP[heading]
        nxt = self.at.get((j.x + dx, j.y + dy))
        return (self.segments[f"{nxt}<{OPPOSITE[heading]}"] if nxt else None), heading

    def new_vehicle(self, kind):
        v = {"id": self.next_id, "kind": kind, "pos": 0, "speed": 1, "wait": 0, "age": 0, "moved": -1}
        self.next_id += 1
        return v

    def choose_turn(self, v):
        if v["kind"] == "ambulance":
            return "straight"
        if v["kind"] == "bus" and self.drive.random() < 0.7:
            return "straight"
        return self.drive.choices(list(TURNS), weights=list(TURNS.values()))[0]

    def demand(self, seg):
        """Vehicles per tick wanting to enter on this edge road. The busy direction changes in waves:
        side streets busy, then Zhongxiao busy, then both normal, and again. Patterns come back."""
        main = AXIS[seg.side]
        wave = (self.t // WAVE) % 3
        if wave == 0:
            return 0.38 if main == "NS" else 0.16
        if wave == 1:
            return 0.38 if main == "EW" else 0.16
        return 0.26

    # ----- the world moves -------------------------------------------------------
    def arrive(self):
        """New vehicles and people arrive. Called at the start of every tick, BEFORE the decision."""
        for seg in self.entries:
            spawn, pick = self.rng.random(), self.rng.random()  # always 2 draws: arrivals never depend on the officer
            if spawn < self.demand(seg):
                kind = "scooter" if pick < 0.5 else "car" if pick < 0.88 else "bus"
                self.backlog[seg.id].append(self.new_vehicle(kind))
        siren, where = self.rng.random(), self.rng.randrange(len(self.entries))
        if self.with_ambulances and self.t < self.ticks - 8 and not self.ambulances() and siren < 0.04:
            self.backlog[self.entries[where].id].insert(0, self.new_vehicle("ambulance"))
        for seg in self.entries:
            queue = self.backlog[seg.id]
            if queue and seg.room() > 0:
                v = queue.pop(0)
                v["turn"] = self.choose_turn(v)
                seg.cars.append(v)
        for j in self.junctions.values():
            arriving = poisson(self.rng, 0.5)  # always drawn: the cars stay the same with people off
            if self.with_pedestrians:
                j.pedestrians += [0] * arriving

    def forced_actions(self):
        """Junctions whose light is locked this tick (minimum green): {junction: action}."""
        return {jid: ACTION_OF[j.light] for jid, j in self.junctions.items() if j.locked}

    def step(self, actions):
        """Apply one action per junction ({junction id: action}). Returns the total points for this tick."""
        crossed = {jid: [] for jid in self.junctions}
        walked = {jid: 0 for jid in self.junctions}

        # 1. traffic lights
        for jid, j in self.junctions.items():
            target = PHASE[actions.get(jid, ACTION_OF[j.light])]
            if j.locked:
                target = j.light
            if target != j.light:
                j.light, j.green_for, j.yellow, j.locked = target, 0, True, 1
            else:
                j.locked = max(0, j.locked - 1)
                j.yellow = False
                j.green_for += 1
                if target == "WALK":
                    walked[jid], j.pedestrians = len(j.pedestrians), []

        # 2. vehicles move (dynamic speeds)
        p_slow = 0.25 if self.raining() else 0.1
        for seg in self.segments.values():
            seg.received = False
        exited = []
        for seg in self.segments.values():
            junction = self.junctions[seg.to]
            ahead = None  # position of the vehicle in front (after its move)
            crossed_here = False
            for v in list(seg.cars):
                ambulance = v["kind"] == "ambulance"
                if v["moved"] == self.t:
                    if not ambulance:
                        ahead = v["pos"]
                    continue
                v["moved"] = self.t
                v["age"] += 1
                v["speed"] = min(v["speed"] + KINDS[v["kind"]]["accel"], self.vmax(v["kind"]))
                to_line = LENGTH - 1 - v["pos"]
                nxt = None
                if ambulance:
                    # everybody makes way: only a red light (or yellow) stops an ambulance
                    gap = to_line
                    if junction.allows(seg.side):
                        nxt, _ = self.target(seg, v["turn"])
                        gap = to_line + 3
                elif ahead is not None:
                    gap = ahead - v["pos"] - 1
                else:
                    gap = to_line  # stop at the line
                    if junction.allows(seg.side) and not crossed_here:
                        nxt, _ = self.target(seg, v["turn"])
                        room = 3 if nxt is None else (0 if nxt.received else nxt.room())
                        if room > 0:
                            gap = to_line + room
                            if v["turn"] != "straight":
                                gap = min(gap, to_line + 1)  # slow down to turn
                v["speed"] = min(v["speed"], gap)
                if v["speed"] > 0 and not ambulance and self.drive.random() < p_slow:
                    v["speed"] -= 1
                new = v["pos"] + v["speed"]
                v["wait"] = v["wait"] + 1 if v["speed"] == 0 else 0
                if new <= LENGTH - 1:
                    v["pos"] = new
                    if not ambulance:
                        ahead = new
                    continue
                # crosses the junction
                seg.cars.remove(v)
                crossed[seg.to].append(v["kind"])
                if not ambulance:
                    crossed_here = True
                    ahead = None
                if nxt is None:
                    exited.append(v)
                    self.trips.append(v["age"])
                else:
                    v["pos"] = min(new - LENGTH, LENGTH - 1)
                    v["turn"] = self.choose_turn(v)
                    nxt.cars.append(v)
                    if not ambulance:
                        nxt.received = True
        for seg in self.segments.values():
            seg.cars.sort(key=lambda v: -v["pos"])  # keep "front first" after ambulances passed others

        # 3. waiting and points
        for v in (v for q in self.backlog.values() for v in q):
            v["age"] += 1
        rewards, parts, energy = {}, {k: 0.0 for k in POINTS}, {}
        for jid, j in self.junctions.items():
            j.pedestrians = [w + 1 for w in j.pedestrians]
            cars = [v for seg in self.incoming(jid) for v in seg.cars]
            counts = {
                "crossed": sum(KINDS[k]["value"] for k in crossed[jid]),
                "walked": walked[jid],
                "stopped": sum(1 for v in cars if v["speed"] == 0)
                + sum(len(self.backlog.get(seg.id, [])) for seg in self.incoming(jid)),
                "pedestrians_waiting": len(j.pedestrians),
                "angry": sum(1 for v in cars if v["wait"] > ANGRY_AFTER),
                "ambulance_stopped": int(any(v["kind"] == "ambulance" and v["speed"] == 0 for v in cars)),
            }
            r = 0.0
            for k, n in counts.items():
                r += POINTS[k] * n
                parts[k] += POINTS[k] * n
            rewards[jid] = round(r, 2)
            energy[jid] = counts["stopped"]  # idling vehicles burn fuel
        total = round(sum(rewards.values()), 2)
        self.score = round(self.score + total, 2)
        self.energy += sum(energy.values())
        self.last = {"rewards": rewards, "crossed": crossed, "walked": walked, "exited": len(exited), "reward": total,
                     "parts": {k: round(v, 2) for k, v in parts.items()}, "energy": energy,
                     "energy_total": sum(energy.values())}
        self.t += 1
        return total

    def done(self):
        return self.t >= self.ticks

    def ambulances(self):
        return [v for seg in self.segments.values() for v in seg.cars if v["kind"] == "ambulance"] + [
            v for q in self.backlog.values() for v in q if v["kind"] == "ambulance"]

    # ----- reading the state -----------------------------------------------------
    def approach(self, seg, vision=None):
        """Numbers about one road into a junction. vision=N: only the N cells before the stop line
        (what an officer can see). An ambulance is always known: you hear the siren."""
        cars = [v for v in seg.cars if v["pos"] >= LENGTH - vision] if vision else seg.cars
        return {
            "from": seg.source or "city edge",
            "vehicles": len(cars),
            "stopped": sum(1 for v in cars if v["speed"] == 0),
            "mean_speed": round(sum(v["speed"] for v in cars) / len(cars), 2) if cars else 0.0,
            "longest_wait": max((v["wait"] for v in cars), default=0),
            "buses": sum(1 for v in cars if v["kind"] == "bus"),
            "ambulance": any(v["kind"] == "ambulance" for v in seg.cars),
            "waiting_outside_city": 0 if vision else len(self.backlog.get(seg.id, [])),
            "turning": {t: sum(1 for v in cars if v.get("turn") == t) for t in TURNS},
        }

    def exit_room(self, jid, axis, vision=None):
        """Free cells on the roads that LEAVE this junction along an axis (small = traffic will block).
        vision=N: an officer can only see N cells, so it is at most N."""
        j = self.junctions[jid]
        rooms = []
        for heading in DIRS:
            if AXIS[heading] != axis:
                continue
            dx, dy = STEP[heading]
            nxt = self.at.get((j.x + dx, j.y + dy))
            rooms.append(self.segments[f"{nxt}<{OPPOSITE[heading]}"].room() if nxt else LENGTH)
        return min(min(rooms), vision) if vision else min(rooms)

    def state(self, vehicles=False, vision=None):
        """The full state as a pure map (JSON-ready dict). vehicles=True adds every vehicle.
        vision=N: what officers can see, N cells down each road (see VISION)."""
        out = {
            "tick": self.t, "ticks": self.ticks, "map": self.map, "road_length": LENGTH,
            "weather": "rain" if self.raining() else "dry", "score": self.score, "energy": self.energy,
            "trips_finished": len(self.trips),
            "junctions": {},
        }
        for jid, j in self.junctions.items():
            approaches = {}
            for seg in self.incoming(jid):
                a = self.approach(seg, vision)
                if vehicles:
                    a["cars"] = [{"id": v["id"], "kind": v["kind"], "pos": v["pos"], "speed": v["speed"],
                                  "wait": v["wait"], "turn": v.get("turn")} for v in seg.cars]
                approaches[seg.side] = a
            out["junctions"][jid] = {
                "name": j.name, "x": j.x, "y": j.y,
                "light": j.light, "yellow": j.yellow, "locked": j.locked, "green_for": j.green_for,
                "pedestrians": len(j.pedestrians), "pedestrians_longest_wait": max(j.pedestrians, default=0),
                "exit_room": {"NS": self.exit_room(jid, "NS", vision), "EW": self.exit_room(jid, "EW", vision)},
                "approaches": approaches,
            }
        return out

    def state_array(self, only=None, vision=None):
        """The state as a flat list of numbers. Use array_fields() for the name of each number.
        only=[junction ids]: just those junctions (what one officer can see)."""
        s = self.state(vision=vision)
        values = [s["tick"] / self.ticks, 1.0 if s["weather"] == "rain" else 0.0]
        for jid, j in s["junctions"].items():
            if only is not None and jid not in only:
                continue
            values += [1.0 if j["light"] == p else 0.0 for p in ("NS", "EW", "WALK")]
            values += [float(j["yellow"]), float(j["locked"]), float(j["green_for"]),
                       float(j["pedestrians"]), float(j["pedestrians_longest_wait"]),
                       float(j["exit_room"]["NS"]), float(j["exit_room"]["EW"])]
            for side in DIRS:
                a = j["approaches"][side]
                values += [float(a["vehicles"]), float(a["stopped"]), a["mean_speed"], float(a["longest_wait"]),
                           float(a["buses"]), float(a["ambulance"]), float(a["waiting_outside_city"])]
        return values

    def array_fields(self, only=None):
        names = ["time_fraction", "raining"]
        for jid in self.junctions:
            if only is not None and jid not in only:
                continue
            names += [f"{jid}.light_{p}" for p in ("NS", "EW", "WALK")]
            names += [f"{jid}.{n}" for n in ("yellow", "locked", "green_for", "pedestrians",
                                             "pedestrians_longest_wait", "exit_room_NS", "exit_room_EW")]
            for side in DIRS:
                names += [f"{jid}.{side}.{n}" for n in ("vehicles", "stopped", "mean_speed", "longest_wait",
                                                        "buses", "ambulance", "waiting_outside_city")]
        return names

    def describe(self, only=None, vision=None):
        """The state as plain English for Jev. Clear facts -> better decisions.
        only=[junction ids]: just what an officer standing there can see (no other junctions, no city score).
        vision=N: only the first N cells of each road (see VISION)."""
        s = self.state(vision=vision)
        if only is None:
            head = (f"Taipei, Zhongxiao E. Rd ({self.map}), tick {self.t + 1} of {self.ticks}. Weather: {s['weather']}. "
                    f"Score so far: {self.score}. Energy used so far: {self.energy}.")
        else:
            head = f"What you see from your junction. Tick {self.t + 1} of {self.ticks}. Weather: {s['weather']}."
            if vision:
                head += f" You can see {vision} cells down each road (about {vision} cars)."
        lines = [head, "Vehicles: s=scooter c=car B=bus A=ambulance. Speeds are in cells per tick (0 = stopped)."]
        for jid, j in s["junctions"].items():
            if only is not None and jid not in only:
                continue
            light = "YELLOW" if j["yellow"] else ("WALK" if j["light"] == "WALK" else f"GREEN {ACTION_OF[j['light']]}")
            lines.append(f"\nJUNCTION {jid} ({j['name']}): light {light} for {j['green_for']} tick(s).")
            for side in DIRS:
                a = j["approaches"][side]
                seg = self.segments[f"{jid}<{side}"]
                cars = "".join(SYMBOL[v["kind"]] for v in seg.cars if not vision or v["pos"] >= LENGTH - vision)
                outside = f", {a['waiting_outside_city']} waiting to enter the city" if a["waiting_outside_city"] else ""
                lines.append(f"  from {side:<5} ({a['from']}): {a['vehicles']} vehicles [{cars}], {a['stopped']} stopped, "
                             f"average speed {a['mean_speed']}, longest wait {a['longest_wait']}{outside}")
            ns = sum(j["approaches"][d]["vehicles"] for d in ("north", "south"))
            ew = sum(j["approaches"][d]["vehicles"] for d in ("east", "west"))
            busier = "north_south" if ns > ew else "east_west" if ew > ns else "equal"
            lines.append(f"  Total north_south: {ns}. Total east_west: {ew}. Busier: {busier}.")
            room = j["exit_room"]
            lines.append(f"  Free space on the roads after the junction: north_south {room['NS']} cells, "
                         f"east_west {room['EW']} cells (0 = blocked, green is useless there).")
            lines.append(f"  Pedestrians waiting: {j['pedestrians']} (longest wait {j['pedestrians_longest_wait']}).")
            amb = [side for side in DIRS if j["approaches"][side]["ambulance"]]
            if amb:
                lines.append(f"  AMBULANCE coming from the {amb[0]} (you hear the siren)! Give green to {ACTION_OF[AXIS[amb[0]]]}.")
        lines.append("\nRule: changing a light costs one YELLOW tick, then the new phase runs at least 1 tick.")
        return "\n".join(lines)

    def snapshot(self):
        """Compact picture of this tick for the replay viewer."""
        return {
            "t": self.t,
            "weather": "rain" if self.raining() else "dry",
            "lights": {jid: [j.light, j.yellow, j.locked] for jid, j in self.junctions.items()},
            "peds": {jid: len(j.pedestrians) for jid, j in self.junctions.items()},
            "roads": {sid: [[v["pos"], SYMBOL[v["kind"]], v["speed"]] for v in seg.cars]
                      for sid, seg in self.segments.items() if seg.cars},
            "outside": {sid: len(q) for sid, q in self.backlog.items() if q},
            "score": self.score,
        }

    def layout(self):
        """The map for the viewer."""
        return {
            "map": self.map, "length": LENGTH, "vision": VISION,
            "junctions": {jid: {"x": j.x, "y": j.y, "name": j.name} for jid, j in self.junctions.items()},
            "roads": {sid: {"to": s.to, "side": s.side, "from": s.source} for sid, s in self.segments.items()},
        }

    def render(self):
        """ASCII picture for the terminal. Junction boxes: | NS green, - EW green, * walk, y yellow."""
        cols = max(j.x for j in self.junctions.values()) + 1
        rows = max(j.y for j in self.junctions.values()) + 1
        width, height = 2 * LENGTH + cols * 2 + (cols - 1) * LENGTH, 2 * LENGTH + rows * 2 + (rows - 1) * LENGTH
        grid = [[" "] * width for _ in range(height)]
        for j in self.junctions.values():
            c0, r0 = LENGTH + j.x * (LENGTH + 2), LENGTH + j.y * (LENGTH + 2)
            mark = "y" if j.yellow else {"NS": "|", "EW": "-", "WALK": "*"}[j.light]
            for dr in (0, 1):
                for dc in (0, 1):
                    grid[r0 + dr][c0 + dc] = mark
            for side in DIRS:
                seg = self.segments[f"{j.id}<{side}"]
                cells = {v["pos"]: SYMBOL[v["kind"]] for v in seg.cars}
                for p in range(LENGTH):
                    if side == "west":
                        r, c = r0 + 1, c0 - LENGTH + p
                    elif side == "east":
                        r, c = r0, c0 + 2 + LENGTH - 1 - p
                    elif side == "north":
                        r, c = r0 - LENGTH + p, c0
                    else:
                        r, c = r0 + 2 + LENGTH - 1 - p, c0 + 1
                    grid[r][c] = cells.get(p, ".")
        lines = ["".join(row).rstrip() for row in grid]
        peds = "  ".join(f"{jid}: {len(j.pedestrians)}" for jid, j in self.junctions.items())
        lines.append(f"Pedestrians waiting  {peds}")
        amb = self.ambulances()
        if amb:
            lines.append("!!! AMBULANCE in the city !!!")
        return "\n".join(lines)
