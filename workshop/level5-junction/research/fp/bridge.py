"""Drive oracle.js (the real city.html JS) with a python policy; mimics city_server.py history handling."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import policies

def run_oracle(policy, ticks=270, pre=0, seed=None, history_len=50):
    env = dict(os.environ, TICKS=str(ticks), PRE=str(pre))
    if seed is not None: env["SEEDQ"] = f"?seed={seed}"
    p = subprocess.Popen(["node", os.path.join(os.path.dirname(__file__), "oracle.js")], env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    hist, states, scores = [], [], []
    while True:
        msg = json.loads(p.stdout.readline())
        if "done" in msg: break
        if "state" in msg:
            cur = msg["state"]
            lights = {str(k): v for k, v in (policy(list(hist[-history_len:]), cur) or {}).items()}
            states.append(json.loads(json.dumps(cur)))
            cur["lights_chosen"] = lights; hist.append(cur); del hist[:-500]
            p.stdin.write(json.dumps(lights) + "\n"); p.stdin.flush()
        else:
            scores.append(msg)
    p.wait()
    return {"score": msg["score"], "states": states, "ticks": scores}

if __name__ == "__main__":
    t = time.time(); r = run_oracle(policies.current_rule, pre=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    print("oracle score", r["score"], "time", round(time.time() - t, 2))
    json.dump(r, open(os.path.join(os.path.dirname(__file__), f"oracle_rule_pre{sys.argv[1] if len(sys.argv)>1 else 0}.json"), "w"))
