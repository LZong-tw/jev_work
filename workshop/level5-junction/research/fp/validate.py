import sys, json, multiprocessing as mp, statistics as st
import sim, best_policy as bp
HOLD = [(s, p) for s in range(11, 31) for p in (0, 1)]
def one(a):
    prm, s, p = a
    return sim.run(bp.policy(**prm), seed=s, pre_ticks=p, keep_states=False)["score"]
if __name__ == "__main__":
    cands = json.loads(sys.argv[1])
    with mp.Pool(10) as pool:
        res = {i: pool.map(one, [(c, s, p) for s, p in HOLD]) for i, c in enumerate(cands)}
    base = res[0]
    for i, c in enumerate(cands):
        r = res[i]; d = [a - b for a, b in zip(r, base)]
        print(c, f"mean={st.mean(r):.1f} sd={st.stdev(r):.1f} min={min(r):.1f} diff_vs_0={st.mean(d):+.1f}±{st.stdev(d)/len(d)**.5:.1f}(se)")
