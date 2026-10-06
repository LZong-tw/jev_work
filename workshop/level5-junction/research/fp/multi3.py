import statistics as st, instr, relaxed, collections
rows = []
for sd in range(1, 11):
    s, log = instr.run(lambda h, c: {}, seed=sd, cls=relaxed.Relaxed)
    t = collections.Counter()
    for k, v in log.items(): t[k[0]] += v
    rows.append((s, t["vx"], t["px"], t["wv"], t["wp"])); print(sd, rows[-1], flush=True)
    if sd == 7: instr.summarize(s, log, open("relaxed_seed7.txt", "w"))
for i, lab in enumerate(["score", "vehX", "pplX", "wv", "wp"]):
    xs = [r[i] for r in rows]; print(f"relaxed {lab}: mean {st.mean(xs):.1f} sd {st.stdev(xs):.1f}")
