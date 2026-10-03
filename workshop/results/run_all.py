"""
Measure every solution against the REAL Jev API, several times, and save the numbers.

    python results/run_all.py                 # all levels, 3 repeats (about US$0.30 at today's price)
    python results/run_all.py --levels 4,5    # only some levels
    python results/run_all.py --repeats 5
    python results/report.py                  # turn results/*.json into RESULTS.md + charts

Each level runs in its own process (every level folder has its own solution_a.py).
Answers are NOT cached here: we want to see how much Jev's answers move between repeats.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSHOP = HERE.parent
sys.path.insert(0, str(WORKSHOP))
sys.path.insert(0, str(HERE))
import jev  # noqa: E402

TOKENS = {"input": 0, "calls": 0}


def counting(decide):
    """Wrap jev.decide to count calls and input tokens."""
    def wrapped(*args, **kwargs):
        result = decide(*args, **kwargs)
        TOKENS["calls"] += 1
        TOKENS["input"] += result.get("usage", {}).get("input_tokens", 0)
        return result
    return wrapped


def use_level(folder):
    """Make `import solution_a` etc. find this level's files."""
    sys.path.insert(0, str(WORKSHOP / folder))


def patch_decide(*modules):
    for m in modules:
        m.decide = counting(jev.decide)


# ----------------------------------------------------------------------------- level 1
def level1(repeats):
    use_level("level1-yes-or-no")
    import solution_a
    import solution_b
    import spam_filter
    from test_sets import SPAM_HOLDOUT
    patch_decide(solution_a, solution_b)

    decide = counting(jev.decide)
    naive_q = jev.noul("Is this message spam?")

    def naive(message):
        p = decide(state=message, questions={"spam": naive_q})["answers"]["spam"]["noul"]
        return p >= 0.5, p

    workshop = list(zip(spam_filter.MESSAGES, spam_filter.EXPECTED))
    configs = {"naive question": naive, "A: one question + criteria": solution_a.is_spam,
               "B: three small questions": solution_b.is_spam}
    out = {}
    for name, fn in configs.items():
        runs = []
        for _ in range(repeats):
            rows = []
            for split, data in (("workshop", workshop), ("holdout", SPAM_HOLDOUT)):
                for message, label in data:
                    spam, _ = fn(message)
                    rows.append({"split": split, "label": label, "got": "spam" if spam else "ok"})
            runs.append(rows)
        out[name] = runs
    return out


# ----------------------------------------------------------------------------- level 2
def level2(repeats):
    use_level("level2-pick-and-rate")
    import inbox
    import solution_a
    import solution_b
    from test_sets import INBOX_HOLDOUT, INBOX_WORKSHOP_LABELS
    patch_decide(solution_a, solution_b, inbox)

    def starter(message):
        a = inbox.decide(state=message, questions=inbox.QUESTIONS)["answers"]
        box = a["box"]["choice"] if a["box"]["confidence"] >= inbox.MIN_CONFIDENCE else "HUMAN"
        return box, a["urgency"]["score"], a["box"]["confidence"]

    data = [("workshop", m, label) for m, label in zip(inbox.INBOX, INBOX_WORKSHOP_LABELS)]
    data += [("holdout", m, label) for m, label in INBOX_HOLDOUT]
    configs = {
        "starter": (starter, set(inbox.QUESTIONS["box"]["criteria"])),
        "A: add lost_item box": (solution_a.sort_message, set(solution_a.BOXES)),
        "B: add 'other' -> human": (solution_b.sort_message, set(solution_b.BOXES) - {"other"}),
    }
    out = {}
    for name, (fn, boxes) in configs.items():
        runs = []
        for _ in range(repeats):
            rows = []
            for split, message, label in data:
                box, urgency, conf = fn(message)
                rows.append({"split": split, "label": label, "got": box, "has_box": label in boxes,
                             "confidence": conf, "urgency": urgency})
            runs.append(rows)
        out[name] = runs
    return out


# ----------------------------------------------------------------------------- level 3
def level3(repeats):
    use_level("level3-guardrail")
    import agent_gate
    import solution_a
    import solution_b
    from test_sets import TOOL_CALLS_HOLDOUT, TOOL_CALLS_WORKSHOP_LABELS
    patch_decide(solution_a, solution_b, agent_gate)

    def starter(call):
        return agent_gate.gate(agent_gate.decide(state=call, questions=agent_gate.QUESTIONS)["answers"])

    workshop_calls = agent_gate.TOOL_CALLS + solution_a.RED_TEAM
    data = [("workshop", c, label) for c, label in zip(workshop_calls, TOOL_CALLS_WORKSHOP_LABELS)]
    data += [("holdout", c, label) for c, label in TOOL_CALLS_HOLDOUT]
    configs = {"starter gate": starter, "A: Jev judges, code decides": solution_a.check,
               "B: Jev decides from a policy": solution_b.check}
    out = {}
    for name, fn in configs.items():
        runs = []
        for _ in range(repeats):
            runs.append([{"split": split, "tool": c["tool"], "label": label, "got": fn(c)[0]} for split, c, label in data])
        out[name] = runs
    return out


# ----------------------------------------------------------------------------- level 4
def level4(repeats):
    use_level("level4-tea-shop")
    import shop
    import solution_a
    import solution_b
    shop.decide = counting(jev.decide)  # all policies call shop.decide
    seeds = list(range(1, 11))
    configs = {
        "rules (no AI)": (shop.Shop, shop.rules_policy, 1),
        "starter Jev": (shop.Shop, shop.jev_policy, repeats),
        "A: day question + advice": (solution_a.BetterShop, solution_a.day_policy, repeats),
        "B: A + guard rules in code": (solution_a.BetterShop, solution_b.guarded_policy, repeats),
    }
    out = {}
    for name, (cls, policy, n) in configs.items():
        out[name] = [{str(seed): solution_a.play(cls, policy, seed) for seed in seeds} for _ in range(n)]
    from best_possible import best_possible
    out["best possible"] = [{str(seed): best_possible(seed) for seed in seeds}]
    return out


# ----------------------------------------------------------------------------- level 5
def level5(repeats):
    use_level("level5-junction")
    import officers
    import run
    import solution_a
    import solution_b
    officers.decide = counting(jev.decide)

    configs = [
        ("fixed timer (no AI)", officers.FixedOfficer, 1),
        ("simple rules (no AI)", officers.GreedyOfficer, 1),
        ("Jev, current tick only", lambda: officers.JevOfficer(history=False), repeats),
        ("Jev, full history (starter)", officers.JevOfficer, repeats),
        ("A: history + coach lessons", solution_a.officer, repeats),
        ("B: last 20 ticks + lessons", solution_b.officer, repeats),
    ]
    out = {"seed": run.EXAM_SEED, "ticks": run.TICKS, "configs": {}}
    for name, make, n in configs:
        runs = []
        for _ in range(n):
            city, trace = run.play(make(), run.EXAM_SEED, quiet=True)
            runs.append(summarize(city, trace, run.blocks))
        out["configs"][name] = runs
        print(name, [r["score"] for r in runs], flush=True)
    return out


def summarize(city, trace, blocks):
    """The numbers we keep from one Level 5 stream."""
    return {"score": city.score, "energy": city.energy, "blocks": [b[2] for b in blocks(trace)],
            "energy_blocks": [b[3] for b in blocks(trace)],
            "calls": sum(t["decision"].get("calls", 0) for t in trace),
            "tokens": sum(t["decision"].get("tokens", 0) for t in trace),
            "walks": sum(1 for t in trace for j, a in t["actions"].items() if a == "walk" and j not in t["forced"]),
            "pedestrians_at_end": sum(trace[-1]["peds"].values()),
            "parts": {k: round(sum(t["parts"][k] for t in trace), 1) for k in trace[0]["parts"]}}


LEVELS = {1: level1, 2: level2, 3: level3, 4: level4, 5: level5}


OUT = Path(os.environ.get("RESULTS_DIR") or HERE)  # tests write somewhere else


def run_one(level, repeats):
    if jev.config()["mock"] and not os.environ.get("RESULTS_ALLOW_MOCK"):
        sys.exit("run_all.py measures the real API. Set JEV_MOCK=0 (and JEV_BASE_URL / JEV_API_KEY).")
    started = time.time()
    data = LEVELS[level](repeats)
    result = {"level": level, "repeats": repeats, "model": jev.config()["model"], "date": time.strftime("%Y-%m-%d"),
              "seconds": round(time.time() - started), "calls": TOKENS["calls"], "input_tokens": TOKENS["input"],
              "cost_usd": round(TOKENS["input"] * jev.PRICE_PER_MILLION_INPUT_TOKENS / 1e6, 4), "data": data}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"level{level}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"level {level}: {TOKENS['calls']} calls, {TOKENS['input']} input tokens, "
          f"US${result['cost_usd']}, {result['seconds']} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", default="1,2,3,4,5")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--only", type=int, help=argparse.SUPPRESS)  # internal: one level, in this process
    args = ap.parse_args()
    if args.only:
        return run_one(args.only, args.repeats)
    os.environ.pop("JEV_CACHE", None)
    procs = [subprocess.Popen([sys.executable, __file__, "--only", lvl, "--repeats", str(args.repeats)])
             for lvl in args.levels.split(",")]  # levels run in parallel
    codes = [p.wait() for p in procs]
    if any(codes):
        sys.exit("Some levels failed.")
    print("Done. Now run: python results/report.py")


if __name__ == "__main__":
    main()

