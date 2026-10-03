"""
The officers. Each tick, an officer chooses the light for every junction it is asked about.

    fixed           a timer per junction: 6 ticks north_south, 6 ticks east_west, 1 tick walk.
    greedy          simple rules: ambulance first, then pedestrians, then whoever waited too
                    long, then the busier road.
    jev             Jev as a smart state machine for all three junctions: ONE call per tick.
                    It reads the whole story so far: for every past tick what each junction
                    could see, what was decided, the points and the energy, and the running
                    totals. So it can see which decisions worked, and adapt during the stream.
    jev-no-history  Jev with only the current tick (to measure what the history is worth).

Every officer that looks at traffic sees only VISION cells (about 6 cars) down each road
from its stop line. An ambulance is the exception: you can hear the siren from further away.

The Jev officer keeps two SAFETY RULES in code (like Levels 3 and 4: easy rules that must
never fail belong in code, not in a prompt). Junctions handled by a rule are not sent to Jev.
    1. An ambulance is waiting: green for its road.
    2. The walk phase lasts one tick (everybody crosses at once): then green for the busier road.
Without them, our tests saw a junction stay on "walk" for 25 ticks with an ambulance waiting.
Try it: run.py --no-safety

The game loop calls, every tick:
    officer.act(city, ask)          -> {"actions": {junction: action}, "junctions": {...}, ...}
    officer.remember(city, actions) just before the city moves (what was seen and decided)
    officer.observe(city)           just after (the points and the energy of that tick)
"""
import copy
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev import choice, decide  # noqa: E402

import coach  # noqa: E402
from city import ACTION_OF, ACTIONS, AXIS, DIRS, VISION  # noqa: E402
from memory import Lessons, action_of, situation  # noqa: E402

STATE_FORMATS = ("text", "map", "array")


class FixedOfficer:
    name = "fixed"
    CYCLE = ["north_south"] * 6 + ["east_west"] * 6 + ["walk"]

    def act(self, city, ask):
        order = list(city.junctions)
        actions = {jid: self.CYCLE[(city.t + 3 * order.index(jid)) % len(self.CYCLE)] for jid in ask}
        return {"actions": actions, "junctions": {}}


class GreedyOfficer:
    name = "greedy"
    WALK_AT = 8
    PATIENCE = 6
    SWITCH_MARGIN = 3

    def decide_one(self, j):
        a = j["approaches"]
        for side in DIRS:
            if a[side]["ambulance"]:
                return ACTION_OF[AXIS[side]]
        if j["pedestrians"] >= self.WALK_AT:
            return "walk"
        ns = a["north"]["vehicles"] + a["south"]["vehicles"]
        ew = a["east"]["vehicles"] + a["west"]["vehicles"]
        wait_ns = max(a["north"]["longest_wait"], a["south"]["longest_wait"])
        wait_ew = max(a["east"]["longest_wait"], a["west"]["longest_wait"])
        current = ACTION_OF[j["light"]] if j["light"] != "WALK" else None
        if current == "north_south" and wait_ew > self.PATIENCE:
            return "east_west"
        if current == "east_west" and wait_ns > self.PATIENCE:
            return "north_south"
        # switching costs a yellow tick: only switch when the other road is clearly busier
        if current == "north_south" and ew <= ns + self.SWITCH_MARGIN:
            return "north_south"
        if current == "east_west" and ns <= ew + self.SWITCH_MARGIN:
            return "east_west"
        return "north_south" if ns >= ew else "east_west"

    def act(self, city, ask):
        state = city.state(vision=VISION)  # the rules officer has the same limited vision
        return {"actions": {jid: self.decide_one(state["junctions"][jid]) for jid in ask}, "junctions": {}}


def short_name(city, jid):
    """FZ = Fuxing x Zhongxiao: short names keep the history small."""
    j = city.junctions[jid]
    return (j.ns_road[0] + j.ew_road[0]).upper()


def light_code(j):
    return "Y" if j["yellow"] else {"NS": "NS", "EW": "EW", "WALK": "WK"}[j["light"]]


def compact(j):
    """One junction as the officer sees it, in a few characters: light, ticks on it,
    then per road N/S/E/W vehicles/stopped (within VISION cells), then waiting pedestrians."""
    roads = " ".join(f"{d[0].upper()}{j['approaches'][d]['vehicles']}/{j['approaches'][d]['stopped']}" for d in DIRS)
    amb = "".join(f" AMB-{d[0].upper()}" for d in DIRS if j["approaches"][d]["ambulance"])
    return f"{light_code(j)}{j['green_for']} {roads} p{j['pedestrians']}{amb}"


ACTION_CODE = {"north_south": "NS", "east_west": "EW", "walk": "WK"}


class JevOfficer:
    QUESTION = (
        "You control the traffic light at junction {short} ({name}) for tick {tick}. "
        "Read the HISTORY: what happened to the points and the energy after decisions like this, in moments "
        "like now? Choose the light that gives the most points and uses the least energy over the next ticks."
    )
    RULES = (
        "GOAL: the highest total score and the lowest total energy at the end of the stream.\n"
        "POINTS per junction per tick: +1 per car or scooter that crosses, +3 per bus, +5 per ambulance; "
        "-0.05 per stopped vehicle; -0.1 per waiting pedestrian (only 'walk' clears them); "
        "-1 per vehicle stopped more than 10 ticks; -10 while an ambulance waits.\n"
        "ENERGY per junction per tick: 1 per idling (stopped) vehicle.\n"
        "LIGHTS: changing the light costs one yellow tick (Y) where nothing crosses, then it stays at least "
        "1 tick. Actions: north_south (NS), east_west (EW), walk (WK: all cars stop, people cross)."
    )
    KEY = ("How to read a junction: light and ticks on it (NS3 = north-south green for 3 ticks), then each road "
           "N/S/E/W as vehicles/stopped within {vision} cells, then p = waiting pedestrians.")

    def __init__(self, history=True, lessons=False, state_format="text", safety=True, seed=0, limit=None):
        if state_format not in STATE_FORMATS:
            raise ValueError(f"state_format must be one of {STATE_FORMATS}")
        self.use_history = history
        self.lessons = Lessons() if lessons else None
        self.state_format = state_format
        self.safety = safety
        self.limit = limit  # show only the last N ticks of history (None = all)
        self.rng = random.Random(seed + 99)
        self.name = "jev" if history else "jev-no-history"
        self.history = []   # one entry per tick: what was seen, decided, and what it gave
        self.pending = None
        self.moments = []   # snapshots for the coach (only with lessons)

    # ----- the story so far ---------------------------------------------------------
    def remember(self, city, actions, forced=()):
        """Just before the city moves: what each junction saw, and what was decided."""
        state = city.state(vision=VISION)
        self.pending = {"t": city.t, "views": {jid: compact(state["junctions"][jid]) for jid in city.junctions},
                        "actions": dict(actions), "forced": sorted(forced)}
        if self.lessons is not None:
            self.moments.append((copy.deepcopy(city), dict(actions), set(forced)))

    def observe(self, city):
        """Just after the city moved: the points and the energy of that tick."""
        if self.pending is None:
            return
        entry = dict(self.pending, points=city.last["rewards"], energy=city.last["energy"],
                     tick_points=city.last["reward"], tick_energy=city.last["energy_total"],
                     score=city.score, energy_total=city.energy)
        self.history.append(entry)
        self.pending = None
        if self.lessons is not None:
            self.review(city.t)

    def review(self, now):
        """The coach replays decisions that are at least HORIZON ticks old: their future is now past."""
        ready = [m for m in self.moments if m[0].t + coach.HORIZON <= now]
        self.moments = [m for m in self.moments if m[0].t + coach.HORIZON > now]
        for moment in ready:
            past, actions, forced = moment
            seen = past.state(vision=VISION)
            for (_, jid), points in coach.review([moment]).items():
                self.lessons.learn(situation(seen, jid), coach.advantages(points))

    def history_lines(self, city):
        entries = self.history[-self.limit:] if self.limit else self.history
        lines = []
        for e in entries:
            parts = [f"t{e['t'] + 1}"]
            for jid in city.junctions:
                act = ACTION_CODE[e["actions"][jid]] + ("*" if jid in e["forced"] else "")
                parts.append(f"{short_name(city, jid)} {e['views'][jid]} >{act} {e['points'][jid]:+.1f} "
                             f"e{e['energy'][jid]}")
            parts.append(f"tick {e['tick_points']:+.1f} e{e['tick_energy']} | score {e['score']} energy {e['energy_total']}")
            lines.append(" | ".join(parts))
        return lines

    def trend(self):
        """Points and energy of the last 20 ticks, compared with the 20 before: is it getting better?"""
        def window(es):
            return sum(e["tick_points"] for e in es), sum(e["tick_energy"] for e in es)
        if len(self.history) < 20:
            return None
        now_p, now_e = window(self.history[-20:])
        if len(self.history) < 40:
            return f"Last 20 ticks: {now_p:+.1f} points, {now_e} energy."
        before_p, before_e = window(self.history[-40:-20])
        return (f"Last 20 ticks: {now_p:+.1f} points, {now_e} energy. The 20 before: {before_p:+.1f} points, "
                f"{before_e} energy.")

    # ----- what Jev reads ---------------------------------------------------------------
    def state(self, city, ask):
        """The whole picture for this tick: rules, totals, history, lessons, and now."""
        seen = city.state(vision=VISION)
        if self.state_format != "text":
            return self.state_data(city, seen, ask)
        names = ", ".join(f"{short_name(city, j)} = {city.junctions[j].name}" for j in city.junctions)
        lines = [f"TRAFFIC CONTROL on Zhongxiao E. Rd, junctions from west to east: {names}.",
                 f"Tick {city.t + 1} of {city.ticks}. Weather: {seen['weather']}. "
                 f"Score so far: {city.score}. Energy used so far: {city.energy}.",
                 self.RULES, self.KEY.format(vision=VISION)]
        trend = self.trend()
        if trend:
            lines.append(trend)
        if self.use_history:
            lines.append("HISTORY, one line per tick (what each junction saw > the decision, * = locked, "
                         "its points, e = its energy | the whole tick | the totals):")
            lines += self.history_lines(city) or ["(nothing yet: this is the first tick)"]
        if self.lessons is not None:
            lines.append(f"LESSONS from the coach, who replayed {self.lessons.reviewed} past decisions with every "
                         "action (average extra points of each action in moments like now):")
            lines += [self.lessons.lines(seen, jid, short_name(city, jid)) for jid in ask]
        lines.append(f"NOW (tick {city.t + 1}):")
        for jid in city.junctions:
            j = seen["junctions"][jid]
            stopped = sum(a["stopped"] for a in j["approaches"].values())
            lines.append(f"  {short_name(city, jid)}: {compact(j)} | free space after the junction "
                         f"NS={j['exit_room']['NS']} EW={j['exit_room']['EW']} (0 = blocked) | "
                         f"longest wait {max(a['longest_wait'] for a in j['approaches'].values())} ticks | "
                         f"costing now: pedestrians {-0.1 * j['pedestrians']:+.1f}, "
                         f"stopped vehicles {-0.05 * stopped:+.2f} points per tick")
        return "\n".join(lines)

    def state_data(self, city, seen, ask):
        """The same story as data: a map (JSON) or arrays of numbers."""
        rows = [{"t": e["t"] + 1, "seen": e["views"], "actions": e["actions"], "points": e["points"],
                 "energy": e["energy"], "score": e["score"], "energy_total": e["energy_total"]}
                for e in (self.history[-self.limit:] if self.limit else self.history)] if self.use_history else []
        if self.state_format == "map":
            out = {"rules": self.RULES, "tick": city.t + 1, "ticks": city.ticks, "weather": seen["weather"],
                   "score": city.score, "energy": city.energy, "history": rows,
                   "now": {jid: seen["junctions"][jid] for jid in city.junctions}}
        else:
            out = {"rules": self.RULES, "fields": city.array_fields(), "now": city.state_array(vision=VISION),
                   "history_fields": ["t", "score", "energy_total"] + [f"{jid}.{k}" for jid in city.junctions
                                                                         for k in ("action", "points", "energy")],
                   "history": [[r["t"], r["score"], r["energy_total"]] +
                               [v for jid in city.junctions for v in (list(ACTIONS).index(r["actions"][jid]),
                                                                       r["points"][jid], r["energy"][jid])]
                               for r in rows]}
        if self.lessons is not None:
            out["lessons"] = {jid: self.lessons.lines(seen, jid, short_name(city, jid)) for jid in ask}
        return out

    def question(self, city, jid):
        return choice(self.QUESTION.format(short=short_name(city, jid), name=city.junctions[jid].name,
                                           tick=city.t + 1), ACTIONS)

    @staticmethod
    def safety_rule(state, jid):
        """(action, reason) when a safety rule decides for this junction, else None."""
        j = state["junctions"][jid]
        for side in DIRS:
            if j["approaches"][side]["ambulance"]:
                return ACTION_OF[AXIS[side]], "rule: ambulance first"
        if j["light"] == "WALK" and not j["yellow"] and j["green_for"] >= 1:
            return action_of(state, jid, "busier"), "rule: walk lasts one tick"
        return None

    def act(self, city, ask):
        state = city.state(vision=VISION)
        out = {"actions": {}, "junctions": {}, "tokens": 0, "calls": 0}
        if self.safety:
            for jid in list(ask):
                rule = self.safety_rule(state, jid)
                if rule:
                    out["actions"][jid] = rule[0]
                    out["junctions"][jid] = {"rule": rule[1], "situation": situation(state, jid)}
            ask = [jid for jid in ask if jid not in out["actions"]]
        if not ask:
            return out
        result = decide(state=self.state(city, ask), questions={jid: self.question(city, jid) for jid in ask})
        out["tokens"], out["calls"] = result.get("usage", {}).get("input_tokens", 0), 1
        for jid in ask:
            a = result["answers"][jid]
            out["actions"][jid] = a["choice"]
            out["junctions"][jid] = {"confidence": a.get("confidence"), "probabilities": a.get("probabilities"),
                                     "situation": situation(state, jid)}
        return out


def make_officer(policy, state_format="text", safety=True, lessons=False, seed=0, limit=None):
    if policy == "fixed":
        return FixedOfficer()
    if policy == "greedy":
        return GreedyOfficer()
    if policy in ("jev", "jev-no-history"):
        return JevOfficer(history=policy == "jev", lessons=lessons, state_format=state_format, safety=safety,
                          seed=seed, limit=limit)
    raise SystemExit(f"Unknown policy {policy!r}")
