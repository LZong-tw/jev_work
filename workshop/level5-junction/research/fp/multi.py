import sys, statistics as st, instr, policies, relaxed, collections
from sim import City
def agg(policy, cls, seeds, pre=1):
    rows = []
    for sd in seeds:
        s, log = instr.run(policy, seed=sd, pre_ticks=pre, cls=cls)
        t = collections.Counter()
        for k, v in log.items(): t[k[0]] += v
        rows.append((sd, s, t["vx"], t["px"], t["wv"], t["wp"], log[("end","queuedV",0)]+log[("end","backlog",0)]))
    return rows
seeds = range(1, 11)
for name, pol, cls in [("rule", policies.current_rule, City), ("relaxed", lambda h, c: {}, relaxed.Relaxed)]:
    rows = agg(pol, cls, seeds)
    for r in rows: print(name, "seed %d score %.1f vehX %d pplX %d wv %d wp %d leftover %d" % r)
    for i, lab in [(1,"score"),(2,"vehX"),(3,"pplX"),(4,"wv"),(5,"wp")]:
        xs = [r[i] for r in rows]; print(f"  {name} {lab}: mean {st.mean(xs):.1f} sd {st.stdev(xs):.1f}")
