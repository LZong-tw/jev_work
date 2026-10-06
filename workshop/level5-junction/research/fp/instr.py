"""Instrumented run: where points are won/lost, per crossing and hour."""
import sim, json, sys, collections, math
from sim import City, DT, jsround

def run(policy, ticks=270, seed=7, pre_ticks=1, cls=City):
    city = cls(seed)
    log = collections.defaultdict(float)   # (kind, J or loc, hour) -> value
    orig_enter = cls.enter
    def enter(self, v):
        if self._hr >= 0: log[("vx", v.seg.to, self._hr)] += 1
        orig_enter(self, v)
    city.enter = enter.__get__(city)
    # people crossings: patch start_tick by counting waitJ before/after
    orig_st = cls.start_tick
    def st(self):
        before = {p: p.waitJ for p in self.people if p.waitJ is not None}
        orig_st(self)
        for p, j in before.items():
            if p.waitJ is None and self._hr >= 0: log[("px", j, self._hr)] += 1
    city.start_tick = st.__get__(city)
    city._hr = -1
    for _ in range(int(90 / DT)): city.step(DT)
    for _ in range(pre_ticks): city.run_tick()
    for j in city.J: city.all_red(j.id)
    hist = []; score = 0.0; last = city.crossed
    spawnedV0 = city.next_id
    for n in range(1, ticks + 1):
        cur = city.decide_state(n)
        city._hr = int(city.clock // 60)
        lights = {str(k): v for k, v in (policy(hist[-50:], cur) or {}).items()}
        cur["lights_chosen"] = lights; hist.append(cur); del hist[:-500]
        for k, ph in lights.items():
            city.set_lights(int(k), ph); log[("ph", int(k), ph)] += 1
        city.run_tick()
        h = city._hr
        for v in city.vehicles:
            if v.v < 0.3:
                loc = v.seg.to if v.seg.to is not None else "exit"
                log[("wv", loc, h)] += 1
        for p in city.people:
            if p.waitJ is not None: log[("wp", p.waitJ, h)] += 1
        log[("backlog", "all", h)] += sum(len(s.backlog) for s in city.ENTRIES)
        log[("ticks", "all", h)] += 1
        wv, wp = city.waiting(); across = city.crossed - last; last = city.crossed
        score = jsround((score + jsround((across - 0.2 * (wv + wp)) * 10) / 10) * 10) / 10
    log[("end", "backlog", 0)] = sum(len(s.backlog) for s in city.ENTRIES)
    log[("end", "queuedV", 0)] = len(city.vehicles)
    log[("end", "waitP", 0)] = sum(1 for p in city.people if p.waitJ is not None)
    log[("end", "spawnedV", 0)] = city.next_id - spawnedV0
    return score, log

def summarize(score, log, out=sys.stdout):
    hours = sorted({k[2] for k in log if k[0] == "ticks"})
    print(f"score {score}", file=out)
    print("hr  ticks | vehX  pplX | -0.2*wv  -0.2*wp | net | wv by J0..J3,exit | wp by J0..J3 | backlog/tick", file=out)
    for h in hours:
        vx = sum(log[("vx", j, h)] for j in range(4)); px = sum(log[("px", j, h)] for j in range(4))
        wv = {j: log[("wv", j, h)] for j in [0, 1, 2, 3, "exit"]}; wp = {j: log[("wp", j, h)] for j in range(4)}
        WV, WP = sum(wv.values()), sum(wp.values())
        print(f"{h:02d} {int(log[('ticks','all',h)]):4d} | {vx:5.0f} {px:5.0f} | {-.2*WV:7.1f} {-.2*WP:7.1f} | {vx+px-.2*(WV+WP):7.1f} | "
              + " ".join(f"{wv[j]:5.0f}" for j in wv) + " | " + " ".join(f"{wp[j]:5.0f}" for j in range(4))
              + f" | {log[('backlog','all',h)]/log[('ticks','all',h)]:.1f}", file=out)
    tot = collections.Counter()
    for k, v in log.items(): tot[k[0]] += v
    print("totals", {k: round(tot[k], 1) for k in ("vx", "px", "wv", "wp")}, file=out)
    for j in range(4):
        print(f"J{j}: vehX {sum(v for k,v in log.items() if k[0]=='vx' and k[1]==j):.0f} pplX {sum(v for k,v in log.items() if k[0]=='px' and k[1]==j):.0f} "
              f"wv {sum(v for k,v in log.items() if k[0]=='wv' and k[1]==j):.0f} wp {sum(v for k,v in log.items() if k[0]=='wp' and k[1]==j):.0f} "
              f"phases {dict((k[2], int(v)) for k,v in log.items() if k[0]=='ph' and k[1]==j)}", file=out)
    print("end", {k[1]: v for k, v in log.items() if k[0] == "end"}, file=out)

if __name__ == "__main__":
    import policies
    s, log = run(policies.current_rule)
    summarize(s, log)
