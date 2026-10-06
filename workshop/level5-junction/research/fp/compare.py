import json, sys, time
import sim, policies, bridge
def cmp(pre, ticks=270, seed=None, policy=policies.current_rule):
    o = bridge.run_oracle(policy, ticks=ticks, pre=pre, seed=seed)
    t = time.time(); p = sim.run(policy, ticks=ticks, pre_ticks=pre, seed=seed or 7); dt = time.time() - t
    first = next((i for i, (a, b) in enumerate(zip(o["states"], p["states"])) if a != b), None)
    tfirst = next((i for i, (a, b) in enumerate(zip(o["ticks"], p["ticks"])) if a != b), None)
    print(f"pre={pre} seed={seed or 7} oracle={o['score']} port={p['score']} first_state_diff={first} first_tick_diff={tfirst} port_time={dt:.2f}s")
    if first is not None:
        print(json.dumps(o["states"][first])[:1500]); print(json.dumps(p["states"][first])[:1500])
    return o, p
if __name__ == "__main__":
    cmp(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
