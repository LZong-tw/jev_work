"""Pure-Python light controller: decide_sync(history, current, **params) -> {cid: phase}."""
CAR = ("A", "B", "C", "D")
NS, EW = ("north", "south"), ("east", "west")
LANES = {"A": (NS, ("straight_right", "bikes")), "B": (NS, ("left",)),
         "C": (EW, ("straight_right", "bikes")), "D": (EW, ("left",))}
DOWN = {(0, "east"): (1, "west"), (0, "south"): (2, "north"), (1, "west"): (0, "east"), (1, "south"): (3, "north"),
        (2, "north"): (0, "south"), (2, "east"): (3, "west"), (3, "north"): (1, "south"), (3, "west"): (2, "east")}
OUT = {"north": "south", "south": "north", "east": "west", "west": "east"}  # straight: arrive from X, leave by OUT[X]

DEFAULTS = dict(qw=0.1, walk_batch=3.0, walk_starve=12, walk_min=3, walk_max_wait=12, hold=0.0, down_w=0.15)


def _since(history, cid, phase):
    n = 0
    for s in reversed(history):
        ch = s.get("lights_chosen") or {}
        if ch.get(str(cid), ch.get(cid)) == phase:
            break
        n += 1
    return n


def decide_sync(history, current, **kw):
    p = {**DEFAULTS, **kw}
    by_id = {j["id"]: j for j in current["crossings"]}
    lights = {}
    for j in current["crossings"]:
        c, cid = j["cars"], j["id"]
        people = sum(j["people"].values())
        if people:
            limit = p["walk_starve"] if people >= p["walk_min"] else p["walk_max_wait"]
            if _since(history, cid, "W") >= limit:
                lights[cid] = "W"
                continue
        value = {}
        for ph, (sides, keys) in LANES.items():
            served = sum(1 for s in sides for k in keys if c[s][k] > 0)
            queued = sum(c[s][k] for s in sides for k in keys)
            down = 0
            if p["down_w"] and ph in ("A", "C"):
                for s in sides:
                    nxt = DOWN.get((cid, OUT[s]))
                    if nxt:
                        nj, nside = by_id[nxt[0]], nxt[1]
                        down += sum(nj["cars"][nside].values())
            value[ph] = served + p["qw"] * queued - p["down_w"] * down
        value["W"] = people / p["walk_batch"] + p["qw"] * people
        if j["lights"] in value:
            value[j["lights"]] += p["hold"]
        lights[cid] = max(value, key=value.get)
    return lights


def policy(**kw):
    return lambda h, c: decide_sync(h, c, **kw)


async def decide(history, current):
    """Drop-in for my_jev.decide: no network call."""
    return decide_sync(history, current)
