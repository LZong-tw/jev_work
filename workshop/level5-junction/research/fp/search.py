import sys, json, itertools, multiprocessing as mp
import sim, best_policy as bp
EVAL = [(s, pre) for s in (1, 2, 3, 4, 5, 6) for pre in (0, 1, 2)] + [(7, 1)]
def one(args):
    params, seed, pre = args
    return sim.run(bp.policy(**params), seed=seed, pre_ticks=pre, keep_states=False)["score"]
def evaluate(pool, params):
    r = pool.map(one, [(params, s, p) for s, p in EVAL])
    m = sum(r) / len(r); sd = (sum((x - m) ** 2 for x in r) / len(r)) ** .5
    return m, sd, min(r), r[-1]
if __name__ == "__main__":
    grid = json.loads(sys.argv[1])
    keys = list(grid)
    with mp.Pool(10) as pool:
        for vals in itertools.product(*grid.values()):
            prm = dict(zip(keys, vals))
            m, sd, lo, b = evaluate(pool, prm)
            print(f"{prm} mean={m:.1f} sd={sd:.1f} min={lo:.1f} seed7pre1={b:.1f}", flush=True)
