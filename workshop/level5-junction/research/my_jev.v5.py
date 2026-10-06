"""
YOUR TRAFFIC BRAIN. The city runs, but its traffic lights do nothing until this function answers.

    async def decide(history, current) -> new lights

    history   the earlier states, oldest first (like the accumulator of a fold / reduce)
    current   the state now (the same shape, see State below), for example:
              {"tick": 3, "clock": "09:09", "crossings": [
                  {"id": 0, "name": "Fuxing × Zhongxiao", "lights": "A", "ticks": 2,
                   "cars": {"north": {"left": 0, "straight_right": 2, "bikes": 0}, "east": {...}, "south": {...}, "west": {...}},
                   "people": {"north": 4, "east": 0, "south": 0, "west": 2}},
                  ... 3 more crossings ]}
    return    the new lights, one phase per crossing:   {0: "A", 1: "C", 2: "W", 3: "B"}

    A = north-south straight + right turn     B = north-south left turn
    C = east-west straight + right turn       D = east-west left turn
    W = everyone walks (all four zebras)

The city moves in ticks, one decide() call each (city_server.py --tick: 2 s, 1 s, 0.5 s ...). At the
start of a tick, per lane, the first car at the stop line goes if its light is green, and it is across
the crossing at the end of that tick: exactly 1 tick. The lights become exactly what you return and
stay so for the tick (all red before your first answer). A crossing you leave out keeps its lights.
People too: on W, the people waiting at a zebra go when a tick starts and are across at its end.
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Literal, Optional, TypedDict, Union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev as _jev  # noqa: E402

Phase = Literal["A", "B", "C", "D", "W"]
Lights = dict[int, Phase]
Side = Literal["north", "east", "south", "west"]


class Lanes(TypedDict):
    """Who waits on one side of a crossing, per lane."""
    left: int                                # cars waiting to turn left
    straight_right: int                      # cars waiting to go straight or turn right
    bikes: int                               # bikes and scooters waiting


class Crossing(TypedDict):
    id: int                                  # 0 .. 3, the key of your answer
    name: str
    lights: Optional[Phase]                  # None = all red (before your first answer)
    ticks: int                               # how many ticks these lights have been on
    cars: dict[Side, Lanes]                  # per side the traffic comes from
    people: dict[Side, int]                  # people waiting at each zebra


class State(TypedDict):
    tick: int                                # 1, 2, 3, ... one per decide() call
    clock: str                               # "09:09"
    crossings: list[Crossing]                # in history, each state also has "lights_chosen": what you returned


# =============================================================================================
# Calling Jev, typed. One call = one state (text) + any number of questions; Jev answers each
# question on its own, against the same state. Three kinds of question:
#
#   yes_no(...)  -> answer["noul"]          0.0 .. 1.0, the chance the answer is YES
#   choice(...)  -> answer["choice"]        one of your labels (+ "probabilities" per label)
#   score(...)   -> answer["score"]         0 .. len(levels)-1, can be a fraction like 2.4
# =============================================================================================
class YesNoAnswer(TypedDict):
    type: Literal["noul"]
    noul: float                              # chance of YES


class ChoiceAnswer(TypedDict):
    type: Literal["choice"]
    choice: str                              # the label Jev picked
    confidence: float
    probabilities: dict[str, float]          # every label with its probability


class ScoreAnswer(TypedDict):
    type: Literal["score"]
    score: float                             # 0 .. len(levels)-1
    confidence: float


Answer = Union[YesNoAnswer, ChoiceAnswer, ScoreAnswer]


def yes_no(question: str, yes: str = None, no: str = None) -> dict:
    """A yes/no question. yes / no: optional, what exactly counts as yes and as no."""
    return _jev.noul(question, yes=yes, no=no)


def choice(question: str, options: dict[str, str]) -> dict:
    """Pick one of the options: {"label": "what it means", ...}."""
    return _jev.choice(question, options)


def score(question: str, levels: list[str]) -> dict:
    """Rate on a scale, lowest first: ["none", "a few", "many", "a lot"]."""
    return _jev.score(question, levels)


async def ask_jev(state: str, questions: dict[str, dict]) -> dict[str, Answer]:
    """ONE call to the Jev API. state: what Jev reads. questions: {id: yes_no(...) | choice(...) | score(...)}.
    Returns {id: answer} with the same ids."""
    result = await asyncio.to_thread(_jev.decide, state=state, questions=questions)
    return result["answers"]


# =============================================================================================
# Your function
# =============================================================================================
PHASES: dict[Phase, str] = {
    "A": "green for north and south: straight and right turn",
    "B": "green for north and south: left turn",
    "C": "green for east and west: straight and right turn",
    "D": "green for east and west: left turn",
    "W": "all cars stop, people walk across all four roads",
}


# Cars leaving a crossing toward a neighbour: (crossing, side they leave by) -> (next crossing, side they arrive at).
# 0 top left, 1 top right, 2 bottom left, 3 bottom right.
DOWNSTREAM = {(0, "east"): (1, "west"), (1, "west"): (0, "east"),
              (0, "south"): (2, "north"), (2, "north"): (0, "south"),
              (1, "south"): (3, "north"), (3, "north"): (1, "south"),
              (2, "east"): (3, "west"), (3, "west"): (2, "east")}
# The city's rush hours (from city.html WAVES): hour -> (what happens, phase that will carry it).
RUSH = {9: ("cars from left to right", "C"), 10: ("cars from bottom to top", "A"),
        11: ("cars from left to right", "C"), 12: ("a huge crowd walks", "W"),
        13: ("cars from right to left", "C"), 14: ("cars from top to bottom", "A"),
        15: ("people walk, and cars to the top", "A"), 16: ("cars from left to right", "C"),
        17: ("cars to the left and to the bottom", "A and C"), 18: ("a crowd walks", "W"),
        19: ("cars from bottom to top", "A")}
WALK_STARVE_TICKS = 6      # no W for this long and at least WALK_MIN people waiting -> force W
WALK_MIN = 3               # fewer walkers than this wait longer, so cars keep their green
WALK_MAX_WAIT = 12         # nobody waits longer than this, however few they are
TREND_TICKS = 5
WALK_BATCH = 3             # W takes everyone at once, cars only 1 per lane: let people gather, count them at 1/3
QUEUE_WEIGHT = 0.3         # long queues win even if they move fewer per tick (left turns move max 2, straight+bikes 4)
TIE_MARGIN = 0.5           # hybrid: Jev only chooses among phases this close to the program's best
# Who sets the lights: "rule" program only, "hybrid" program + Jev tie-break,
# "jev" program decides when walkers go (W), Jev picks among the car phases A-D. Set JEV_MODE per server process.
MODE = os.environ.get("JEV_MODE", "hybrid")


def demand(j: Crossing) -> dict[Phase, int]:
    """How many wait on the lanes each phase turns green. 1 car per lane per tick, bikes ride with straight."""
    c = j["cars"]
    lane = lambda sides, k: sum(c[s][k] for s in sides)
    ns, ew = ("north", "south"), ("east", "west")
    return {"A": lane(ns, "straight_right") + lane(ns, "bikes"),
            "B": lane(ns, "left"),
            "C": lane(ew, "straight_right") + lane(ew, "bikes"),
            "D": lane(ew, "left"),
            "W": sum(j["people"].values())}


def served(j: Crossing) -> dict[Phase, int]:
    """How many actually get across this tick: at most 1 per non-empty lane; W takes every walker."""
    c = j["cars"]
    moving = lambda sides, keys: sum(1 for s in sides for k in keys if c[s][k] > 0)
    ns, ew = ("north", "south"), ("east", "west")
    return {"A": moving(ns, ("straight_right", "bikes")), "B": moving(ns, ("left",)),
            "C": moving(ew, ("straight_right", "bikes")), "D": moving(ew, ("left",)),
            "W": sum(j["people"].values()) / WALK_BATCH}


def total_waiting(s: State) -> int:
    return sum(sum(l.values()) for j in s["crossings"] for l in j["cars"].values()) \
        + sum(sum(j["people"].values()) for j in s["crossings"])


def ticks_since(history: list[State], cid: int, phase: Phase) -> int:
    """Ticks since this crossing last had `phase` green (len(history) if never seen)."""
    n = 0
    for s in reversed(history):
        chosen = s.get("lights_chosen") or {}
        if chosen.get(cid, chosen.get(str(cid))) == phase:
            break
        n += 1
    return n


def walk_due(history: list[State], j: Crossing) -> Optional[int]:
    """Ticks until the program forces W at this crossing (0 = this tick), None if nobody waits."""
    people = sum(j["people"].values())
    if not people:
        return None
    limit = WALK_STARVE_TICKS if people >= WALK_MIN else WALK_MAX_WAIT
    return max(0, limit - ticks_since(history, j["id"], "W"))


def trend(history: list[State], j: Crossing) -> str:
    if len(history) < TREND_TICKS:
        return ""
    old = next(c for c in history[-TREND_TICKS]["crossings"] if c["id"] == j["id"])
    count = lambda c: (sum(sum(l.values()) for l in c["cars"].values()), sum(c["people"].values()))
    (oc, op), (nc, np_) = count(old), count(j)
    word = lambda a, b: "growing" if b > a else "shrinking" if b < a else "flat"
    return f"  last {TREND_TICKS} ticks: vehicles {oc} -> {nc} ({word(oc, nc)}), people {op} -> {np_} ({word(op, np_)})"


def rush_outlook(clock: str) -> str:
    h, m = map(int, clock.split(":"))
    now, nxt = RUSH.get(h), RUSH.get((h + 1) % 24)
    parts = [f"Now ({h:02d}:00-{h + 1:02d}:00): " + (f"rush, {now[0]} -> {now[1]} queues grow fastest." if now else "normal traffic.")]
    if nxt:
        parts.append(f"In {60 - m} minutes ({(h + 1) % 24:02d}:00): rush, {nxt[0]} -> clear {nxt[1]} queues before it, "
                     f"and keep other queues short so they do not starve while it lasts.")
    return " ".join(parts)


def describe(j: Crossing, history: list[State]) -> str:
    lights = f"{j['lights']} ({PHASES[j['lights']]}) for {j['ticks']} ticks" if j["lights"] else "all red"
    lines = [f"Crossing {j['id']}: lights {lights}."]
    for side, l in j["cars"].items():
        lines.append(f"  from {side}: {l['straight_right']} straight/right, {l['left']} left, {l['bikes']} bikes")
    lines.append("  people waiting: " + ", ".join(f"{s} {n}" for s, n in j["people"].items()))
    due = walk_due(history, j)
    if due is not None:
        lines.append("  the program will force W (people walk) " + ("THIS tick" if due == 0 else f"in {due} ticks")
                     + ": get the car queues moving before then")
    if t := trend(history, j):
        lines.append(t)
    feeds = [f"leaving {side} -> crossing {nxt}" for (cid, side), (nxt, _) in DOWNSTREAM.items() if cid == j["id"]]
    lines.append("  " + "; ".join(feeds))
    return "\n".join(lines)


async def decide(history: list[State], current: State) -> Lights:
    state = ("Score: every tick +1 for each vehicle or person that gets across, -0.2 for each one still waiting. "
             "Each lane lets 1 vehicle across per tick, so long queues only shrink by giving them green; "
             "a lane left red for many ticks keeps costing points every tick. "
             "When people walk (W) is decided by the program; you only pick among the car greens A-D, "
             "and the program weighs your pick against the counted throughput.\n")
    state += f"Time {current['clock']}. A 2x2 grid: crossing 0 top left, 1 top right, 2 bottom left, 3 bottom right.\n"
    state += rush_outlook(current["clock"]) + " 1 tick = 3 minutes.\n"
    state += "\n".join(describe(j, history) for j in current["crossings"])
    if history:
        prev = history[-1]
        state += (f"\nLast tick the lights chosen were {prev.get('lights_chosen')}; "
                  f"everyone waiting in the city went {total_waiting(prev)} -> {total_waiting(current)}.")

    print(f"[waiting] {current['clock']}  cars+people waiting: {total_waiting(current)}  "
          + "  ".join(f"#{j['id']}:{sum(demand(j).values())}" for j in current["crossings"]), flush=True)
    for j in current["crossings"]:
        c = j["cars"]
        print(f"  [lanes] #{j['id']} " + " ".join(f"{s[0]}:L{c[s]['left']}/S{c[s]['straight_right']}/B{c[s]['bikes']}" for s in c)
              + f" ppl:{sum(j['people'].values())}", flush=True)
    car_phases = [p for p in PHASES if p != "W"]
    questions = {}
    for j in current["crossings"]:
        cid, d, sv = j["id"], demand(j), served(j)
        options = {p: f"{PHASES[p]}: +{sv[p]} now, {d[p] - sv[p]} still waiting on it after, "
                      f"last green {ticks_since(history, cid, p)} ticks ago" for p in car_phases}
        questions[str(cid)] = choice(
            f"Crossing {cid}: which green earns the most points over the next few ticks? "
            f"Weigh vehicles crossing now against queues that have waited long and keep losing points.", options)
    answers = await ask_jev(state, questions) if MODE != "rule" else {}

    lights: Lights = {}
    for j in current["crossings"]:
        cid, sv, d = j["id"], served(j), demand(j)
        probs = answers.get(str(cid), {}).get("probabilities", {})
        if walk_due(history, j) == 0:
            lights[cid] = "W"
            continue
        value = {p: sv[p] + QUEUE_WEIGHT * d[p] for p in PHASES}
        rule = max(PHASES, key=value.get)
        close = [p for p in car_phases if value[p] >= value[rule] - TIE_MARGIN]
        if MODE == "hybrid" and rule != "W" and len(close) > 1 and probs:
            rule = max(close, key=lambda p: probs.get(p, 0.0))
        if MODE == "jev" and rule != "W" and probs:
            rule = max(car_phases, key=lambda p: probs.get(p, 0.0))
        lights[cid] = rule
    return lights
