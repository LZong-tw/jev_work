import statistics as st, sys, greedy
from sim import run
for wW in (1.0, 0.6):
    xs = [run(greedy.make(wW), seed=sd, keep_states=False)["score"] for sd in range(1, 11)]
    print(f"greedy wW={wW}: {xs} mean {st.mean(xs):.1f} sd {st.stdev(xs):.1f}", flush=True)
