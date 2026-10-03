"""
The coach: replay past decisions in hindsight and test every move.

A real traffic officer learns from experience, but one run is full of luck: a bus
arrives, it starts to rain, a jam comes from the next junction. If we only compare
"what happened after I switched" with "what happened after I kept the light", luck
hides the effect of the move.

So HORIZON ticks after each decision (when its future is already past), the coach goes back
to that moment, and for each junction tries
all three moves on a copy of the city at that exact moment:

    green for the busier road  |  green for the quieter road  |  walk

The same vehicles arrive in every replay (the world's randomness does not depend on
the officer). After the move, the replay continues for a few ticks with the simple
rules. The coach writes down how many points each move gave that junction.

Lessons for the rest of the stream = "in situations like this, this move was X points better
than the average move". Because the coach tries every move, the officer does not
need to make random moves to learn.
"""
import copy

from city import VISION
from memory import MOVES, action_of, situation

HORIZON = 10  # ticks the coach plays after the move
DISCOUNT = 0.9

_rules = None


def rules():
    global _rules
    if _rules is None:
        from officers import GreedyOfficer  # here, not at the top: officers.py imports this file
        _rules = GreedyOfficer()
    return _rules


def replay(city, jid, actions, horizon=None):
    """Points for junction `jid`: apply `actions` now, then play by the simple rules."""
    horizon = horizon or HORIZON
    c = copy.deepcopy(city)
    c.step(actions)
    total = c.last["rewards"][jid]
    for k in range(1, horizon):
        if c.done():
            break
        c.arrive()
        forced = c.forced_actions()
        ask = [j for j in c.junctions if j not in forced]
        c.step({**forced, **rules().act(c, ask)["actions"]})
        total += DISCOUNT ** k * c.last["rewards"][jid]
    return round(total, 2)


def review(moments, horizon=None):
    """moments: [(city copy before the decision, actions taken, forced junction ids)].
    Returns {(tick, junction): {move: points}} for every decision that was not forced."""
    results = {}
    for city, actions, forced in moments:
        state = city.state(vision=VISION)  # moves mean what the officer could see: "busier" in its view
        for jid in city.junctions:
            if jid in forced:
                continue
            points = {}
            for move in MOVES:
                tried = dict(actions)
                tried[jid] = action_of(state, jid, move)
                points[move] = replay(city, jid, tried, horizon)
            results[(city.t, jid)] = points
    return results


def advantages(points):
    """Each move compared with the average move at that moment (positive = better)."""
    mean = sum(points.values()) / len(points)
    return {m: round(v - mean, 2) for m, v in points.items()}


__all__ = ["review", "replay", "advantages", "situation", "HORIZON"]
