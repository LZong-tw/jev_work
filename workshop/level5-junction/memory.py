"""
Situations and lessons: how the officer can learn DURING the stream.

Jev itself never changes. What changes is what we show it: the history of the stream,
and (optionally) LESSONS from the coach (coach.py), who replays past decisions in hindsight.

1. Each junction, each tick, is a SITUATION, said in RELATIVE words, e.g.
   "green=quieter | difference=big | ambulance=none | blocked=none | red_wait=long | pedestrians=few"
   and each move is relative too: green for the BUSIER road, the QUIETER road, or WALK.
   So one lesson works at every junction and in both directions.
2. HORIZON ticks after a decision, the coach replays it with every move (same traffic arriving)
   and measures how many more points each move gave than the average move.
3. LESSONS = the average of those numbers for each move in situations like now, from this
   stream so far. With few tries, we also trust the average of similar situations.
"""
from collections import defaultdict

from city import AXIS, DIRS

PRIOR = 1  # how many "tries" the similar-situations average is worth
BUSIER = 3  # a road is "busier" when it has at least 3 more vehicles
PATIENCE = 6  # "red_wait=long" when someone on the red road waited longer than this


# Lessons are about MOVES, relative to the junction, not about compass directions.
# "Green for the busier road" means the same thing at every junction and in both
# directions, so one lesson helps in many more places.
MOVES = {
    "busier": "green for the busier road",
    "quieter": "green for the quieter road",
    "walk": "pedestrians walk",
}
AXIS_ACTION = {"NS": "north_south", "EW": "east_west"}


def pedestrian_level(n):
    return "few" if n < 4 else "some" if n < 9 else "many"


def roads(state, jid):
    """(busier axis, quieter axis, vehicles on each). A tie goes to the longer wait, then to NS."""
    a = state["junctions"][jid]["approaches"]
    load = {ax: sum(a[d]["vehicles"] for d in DIRS if AXIS[d] == ax) for ax in ("NS", "EW")}
    wait = {ax: max(a[d]["longest_wait"] for d in DIRS if AXIS[d] == ax) for ax in ("NS", "EW")}
    busier = max(("NS", "EW"), key=lambda ax: (load[ax], wait[ax], ax == "NS"))
    quieter = "EW" if busier == "NS" else "NS"
    return busier, quieter, load


def move_of(state, jid, action):
    """Absolute action ("east_west") -> relative move ("busier")."""
    if action == "walk":
        return "walk"
    busier, _, _ = roads(state, jid)
    return "busier" if action == AXIS_ACTION[busier] else "quieter"


def action_of(state, jid, move):
    """Relative move ("busier") -> absolute action for this junction right now ("east_west")."""
    if move == "walk":
        return "walk"
    busier, quieter, _ = roads(state, jid)
    return AXIS_ACTION[busier if move == "busier" else quieter]


def situation(state, jid):
    """Group similar moments at one junction, in relative words. `state` is city.state()."""
    j = state["junctions"][jid]
    a = j["approaches"]
    busier, quieter, load = roads(state, jid)
    rel = {busier: "busier", quieter: "quieter"}
    green = "walk" if j["light"] == "WALK" else rel[j["light"]]
    amb = next((rel[AXIS[d]] for d in DIRS if a[d]["ambulance"]), "none")
    blocked = [rel[ax] for ax in ("NS", "EW") if j["exit_room"][ax] == 0]
    red_wait = max(a[d]["longest_wait"] for d in DIRS if AXIS[d] != j["light"])
    return " | ".join([
        f"green={green}",
        f"difference={'big' if load[busier] - load[quieter] >= BUSIER else 'small'}",
        f"ambulance={amb}",
        f"blocked={'both' if len(blocked) == 2 else blocked[0] if blocked else 'none'}",
        f"red_wait={'long' if red_wait > PATIENCE else 'short'}",
        f"pedestrians={pedestrian_level(j['pedestrians'])}",
    ])


def coarse(sit):
    """Fallback group: what is green now, the ambulance, and what is blocked."""
    parts = dict(p.split("=") for p in sit.split(" | "))
    return f"green={parts['green']} | ambulance={parts['ambulance']} | blocked={parts['blocked']}"


class Lessons:
    """What the coach has learned so far in THIS stream."""

    def __init__(self):
        self.stats = defaultdict(lambda: defaultdict(list))
        self.coarse_stats = defaultdict(lambda: defaultdict(list))
        self.reviewed = 0

    def learn(self, sit, advantages):
        """advantages = {move: points compared with the average move} for one decision."""
        self.reviewed += 1
        for move, points in advantages.items():
            self.stats[sit][move].append(points)
            self.coarse_stats[coarse(sit)][move].append(points)

    def lessons(self, sit):
        """Expected result of each move in this situation, best first:
        [(move, expected, tries_here, tries_similar), ...].

        Few tries in the exact situation are not reliable (one lucky try!). So we blend in the
        average of the bigger, similar group, as if it were PRIOR extra tries."""
        exact = self.stats.get(sit, {})
        similar = self.coarse_stats.get(coarse(sit), {})
        rows = []
        for move in set(exact) | set(similar):
            here, near = exact.get(move, []), similar.get(move, [])
            if near:
                expected = (sum(here) + PRIOR * (sum(near) / len(near))) / (len(here) + PRIOR)
            else:
                expected = sum(here) / len(here)
            rows.append((move, expected, len(here), len(near)))
        rows.sort(key=lambda r: -r[1])
        return rows

    def lines(self, state, jid, short):
        """The lessons for one junction, as text for Jev."""
        rows = self.lessons(situation(state, jid))
        if not rows:
            return f"  {short}: no lessons yet for a moment like this"
        return f"  {short}: " + ", ".join(f"{action_of(state, jid, m)} {e:+.1f} ({n + k} tries)" for m, e, n, k in rows)
