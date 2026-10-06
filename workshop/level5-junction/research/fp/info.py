"""Value-of-information experiments. Policies get (hist, cur, city); city is the live sim (oracle access)."""
import copy, json, sys, random
import sim
from sim import City, DT, jsround, SIDES, SIDE_HEAD
from policies import current_rule


class RNG:
    """Picklable/deepcopy-safe mulberry32 (sim's closure version would be shared by deepcopy)."""
    def __init__(self, seed):
        self.s = seed & sim.M32

    def __call__(self):
        a = self.s = (self.s + 0x6D2B79F5) & sim.M32
        t = sim._imul(a ^ (a >> 15), 1 | a)
        t = ((t + sim._imul(t ^ (t >> 7), 61 | t)) & sim.M32) ^ t
        return ((t ^ (t >> 14)) & sim.M32) / 4294967296


def tick(city, lights):
    for k, ph in lights.items():
        city.set_lights(int(k), ph)
    last = city.crossed
    city.run_tick()
    wv, wp = city.waiting()
    return jsround(((city.crossed - last) - 0.2 * (wv + wp)) * 10) / 10


def run(policy, ticks=270, seed=7, pre_ticks=1):
    city = City(seed)
    city.rnd = RNG(seed)
    for _ in range(int(90 / DT)):
        city.step(DT)
    for _ in range(pre_ticks):
        city.run_tick()
    for j in city.J:
        city.all_red(j.id)
    hist, score = [], 0.0
    for n in range(1, ticks + 1):
        cur = city.decide_state(n)
        lights = {str(k): v for k, v in policy(hist[-50:], cur, city, n).items()}
        cur["lights_chosen"] = lights
        hist.append(cur)
        score = jsround((score + tick(city, lights)) * 10) / 10
    return score


def rule(hist, cur, city, n):
    return current_rule(hist, cur)


def full_view(hist, cur, city, n):
    """Rule, but the state counts EVERY vehicle on each approach (moving, >80 m) plus the edge backlog."""
    cur = json.loads(json.dumps(cur))
    for jc, j in zip(cur["crossings"], city.J):
        for side in SIDES:
            seg = j.inseg[SIDE_HEAD[side]]
            q = {l: len(seg.lanes[l]) for l in "LSB"}
            for v in seg.backlog:
                q["B" if v.bike else "S"] += 1
            jc["cars"][side] = {"left": q["L"], "straight_right": q["S"], "bikes": q["B"]}
    return current_rule(hist, cur)


def view(far_stopped, near_moving):
    def pol(hist, cur, city, n):
        cur = json.loads(json.dumps(cur))
        for jc, j in zip(cur["crossings"], city.J):
            for side in SIDES:
                seg = j.inseg[SIDE_HEAD[side]]
                q = {}
                for l in "LSB":
                    q[l] = sum(1 for v in seg.lanes[l] if (seg.len - v.s <= 80 and (v.v < 0.3 or near_moving))
                               or (seg.len - v.s > 80 and v.v < 0.3 and far_stopped))
                jc["cars"][side] = {"left": q["L"], "straight_right": q["S"], "bikes": q["B"]}
        return current_rule(hist, cur)
    return pol


def rollout(H=3, clairvoyant=True):
    """One-step policy improvement over the rule: for each crossing try all 5 phases (others at the rule's pick),
    simulate H ticks (rule afterwards) on a clone, keep the best. clairvoyant=True keeps the real RNG stream
    (knows the future arrivals/turns); False reseeds the clone (same model, unknown future)."""
    def pol(hist, cur, city, n):
        base = {str(k): v for k, v in current_rule(hist, cur).items()}
        best = dict(base)
        for cid in map(str, range(4)):
            vals = {}
            for ph in "ABCDW":
                trial = dict(best); trial[cid] = ph
                c = copy.deepcopy(city)
                if not clairvoyant:
                    c.rnd = RNG(random.getrandbits(32))
                h = hist + [dict(cur, lights_chosen=trial)]
                tot = tick(c, trial)
                for k in range(1, H):
                    s = c.decide_state(n + k)
                    l = {str(a): b for a, b in current_rule(h[-50:], s).items()}
                    s["lights_chosen"] = l; h.append(s)
                    tot += tick(c, l)
                vals[ph] = tot
            m = max(vals.values())
            if vals[best[cid]] < m:
                best[cid] = max(vals, key=vals.get)
        return best
    return pol


def close_sets(hist, cur):
    """The hybrid-mode candidate sets my_jev.decide hands to Jev (None where the program decides alone)."""
    import policies
    m = policies._my_jev
    out = {}
    for j in cur["crossings"]:
        if m.walk_due(hist, j) == 0:
            out[str(j["id"])] = None; continue
        sv, d = m.served(j), m.demand(j)
        value = {p: sv[p] + m.QUEUE_WEIGHT * d[p] for p in m.PHASES}
        rule = max(m.PHASES, key=value.get)
        close = [p for p in "ABCD" if value[p] >= value[rule] - m.TIE_MARGIN]
        out[str(j["id"])] = close if rule != "W" and len(close) > 1 else None
    return out


def tie(kind, H=3):
    """Hybrid mode with a perfect or random tie-breaker: Jev's best possible / null contribution."""
    def pol(hist, cur, city, n):
        best = {str(k): v for k, v in current_rule(hist, cur).items()}
        for cid, close in close_sets(hist, cur).items():
            if not close:
                continue
            if kind == "random":
                best[cid] = random.choice(close); continue
            vals = {}
            for ph in close:
                trial = dict(best); trial[cid] = ph
                c = copy.deepcopy(city)
                if kind == "blind":
                    c.rnd = RNG(random.getrandbits(32))
                h = hist + [dict(cur, lights_chosen=trial)]
                tot = tick(c, trial)
                for k in range(1, H):
                    s = c.decide_state(n + k)
                    l = {str(a): b for a, b in current_rule(h[-50:], s).items()}
                    s["lights_chosen"] = l; h.append(s)
                    tot += tick(c, l)
                vals[ph] = tot
            best[cid] = max(close, key=lambda p: (vals[p], p == best[cid]))
        return best
    return pol


POL = {"tie_random": tie("random"), "tie_oracle": tie("oracle"), "tie_blind": tie("blind"),
       "rule": rule, "full_view": full_view, "far_stopped": view(True, False), "near_moving": view(False, True),
       "view_check": view(False, False),
       "roll_clair": rollout(3, True), "roll_blind": rollout(3, False)}

if __name__ == "__main__":
    name, seed, pre = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    random.seed(seed * 1000 + pre)
    print(json.dumps({"pol": name, "seed": seed, "pre": pre, "score": run(POL[name], seed=seed, pre_ticks=pre)}), flush=True)
