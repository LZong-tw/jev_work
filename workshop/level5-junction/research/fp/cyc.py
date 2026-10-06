import sys, statistics as st
from sim import run
def cyc(pattern):
    return lambda h, c: {j: pattern[(c["tick"]) % len(pattern)] for j in range(4)}
pats = {"ACx3+W": "ACACACW", "AACC+W": "AACCAACCW", "ABCD+W": "AABCCDW", "AC+W": "ACW"}
for name, p in pats.items():
    xs = [run(cyc(p), seed=sd, keep_states=False)["score"] for sd in range(1, 6)]
    print(name, xs, "mean %.1f" % st.mean(xs), flush=True)
