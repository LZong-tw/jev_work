"""
Level 5 - Jev runs three traffic lights on Zhongxiao E. Rd, as one smart state machine.

One run = one stream of ticks (200 by default). Every tick Jev reads the whole story so far:
what each junction saw, what was decided, the points and the energy of every past tick,
and the running totals. Can it learn from its own history and get better as it goes?

    python level5-junction/run.py                        # Jev with the full history
    python level5-junction/run.py --lessons              # + the coach's hindsight lessons
    python level5-junction/run.py --policy jev-no-history  # Jev with only the current tick
    python level5-junction/run.py --policy greedy        # simple rules
    python level5-junction/run.py --policy fixed         # timers that ignore traffic
    python level5-junction/run.py --ticks 100            # a shorter stream
    python level5-junction/run.py --exam                 # fixed traffic (seed 2026) for the leaderboard
    python level5-junction/run.py --watch                # draw the city every tick
    python level5-junction/run.py --no-cache             # ask Jev again even for a request it answered before
    python level5-junction/run.py --no-safety            # no safety rules: see what Jev does alone
    python level5-junction/run.py --ticks 10 --no-pedestrians --no-ambulances   # a simpler game, to debug
    python level5-junction/run.py --reset                # delete the saved runs

Same seed = the same run: every Jev answer is saved in runs/answers.jsonl and reused for the
same request (Jev's probabilities move a little between identical calls).

Then open level5-junction/viewer3d.html (3D) or viewer.html (2D) to replay your runs.
See the state as data:  python level5-junction/show_state.py --format map
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from city import DEFAULT_MAP, MAPS, TICKS, VISION, City
from memory import move_of, situation
from officers import STATE_FORMATS, GreedyOfficer, make_officer

# JUNCTION_RUNS_DIR lets tests (or a second player) use a separate folder.
RUNS_DIR = Path(os.environ.get("JUNCTION_RUNS_DIR") or Path(__file__).resolve().parent / "runs")
EXAM_SEED = 2026
KEEP_IN_VIEWER = 15


def play(officer, seed, map_name=DEFAULT_MAP, ticks=TICKS, watch=0.0, quiet=False, **city_options):
    """One stream. Returns (city, trace): one trace entry per tick, for the viewers.
    city_options: ambulances=False, pedestrians=False for a simpler game."""
    city = City(seed, map_name, ticks, **city_options)
    trace = []
    while not city.done():
        city.arrive()
        state = city.state(vision=VISION)
        sits = {jid: situation(state, jid) for jid in city.junctions}
        before = city.snapshot()
        forced = city.forced_actions()
        ask = [jid for jid in city.junctions if jid not in forced]
        decision = officer.act(city, ask) if ask else {"actions": {}, "junctions": {}}
        actions = {**forced, **decision["actions"]}
        if hasattr(officer, "remember"):
            officer.remember(city, actions, forced)
        city.step(actions)
        if hasattr(officer, "observe"):
            officer.observe(city)

        trace.append({**before, "actions": actions, "forced": sorted(forced), "decision": decision,
                      "moves": {jid: move_of(state, jid, actions[jid]) for jid in city.junctions},
                      "reward": city.last["reward"], "rewards": city.last["rewards"], "parts": city.last["parts"],
                      "energy": city.last["energy_total"], "energy_after": city.energy,
                      "situations": sits, "lights_after": {jid: [j.light, j.yellow] for jid, j in city.junctions.items()},
                      "score_after": city.score})

        if watch:
            print("\033[2J\033[H", end="")
            print(f"{officer.name}  tick {city.t}/{city.ticks}  reward {city.last['reward']:+.1f}  "
                  f"score {city.score}  energy {city.energy}  weather {before['weather']}")
            print("  ".join(f"{jid}: {a}{' (locked)' if jid in forced else ''}" for jid, a in actions.items()))
            print(city.render())
            time.sleep(watch)
        elif not quiet:
            print("." if not ask else "|", end="", flush=True)
            if city.t % 50 == 0:
                print(f" {city.t}: score {city.score}, energy {city.energy}", flush=True)
    if not watch and not quiet and city.t % 50:
        print()
    return city, trace


def blocks(trace, size=50):
    """Points and energy per block of ticks: does it get better during the stream?"""
    out = []
    for i in range(0, len(trace), size):
        part = trace[i:i + size]
        out.append((i + 1, i + len(part), round(sum(t["reward"] for t in part), 1), sum(t["energy"] for t in part)))
    return out


def write_viewer_data():
    """runs/runs.js lets the viewers load the runs without a web server."""
    runs = [json.loads(f.read_text()) for f in sorted(RUNS_DIR.glob("run-*.json"))[-KEEP_IN_VIEWER:]]
    (RUNS_DIR / "runs.js").write_text("window.JUNCTION_RUNS = " + json.dumps(runs, separators=(",", ":")) + ";\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", default="jev", choices=["jev", "jev-no-history", "greedy", "fixed"])
    ap.add_argument("--lessons", action="store_true", help="add the coach's hindsight lessons (Jev only)")
    ap.add_argument("--ticks", type=int, default=TICKS, help=f"length of the stream (default {TICKS})")
    ap.add_argument("--history", type=int, default=None, help="show Jev only the last N ticks (default: all)")
    ap.add_argument("--map", default=DEFAULT_MAP, choices=sorted(MAPS))
    ap.add_argument("--state-format", default="text", choices=STATE_FORMATS, help="what Jev reads")
    ap.add_argument("--watch", type=float, nargs="?", const=0.3, default=0.0, help="draw every tick (seconds per tick)")
    ap.add_argument("--exam", action="store_true", help=f"fixed traffic (seed {EXAM_SEED})")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-pedestrians", action="store_true", help="nobody walks: a simpler game")
    ap.add_argument("--no-ambulances", action="store_true", help="no ambulances: a simpler game")
    ap.add_argument("--reset", action="store_true", help="delete the saved runs")
    ap.add_argument("--no-cache", action="store_true", help="do not reuse saved Jev answers")
    ap.add_argument("--no-safety", action="store_true", help="turn off the Jev officer's two safety rules")
    args = ap.parse_args()

    if args.reset:
        for f in RUNS_DIR.glob("*"):
            f.unlink()
        print("Saved runs deleted.")
        return

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    if not args.no_cache:
        os.environ.setdefault("JEV_CACHE", str(RUNS_DIR / "answers.jsonl"))
    n = len(list(RUNS_DIR.glob("run-*.json"))) + 1
    seed = EXAM_SEED if args.exam else (args.seed if args.seed is not None else 1000 + n)
    officer = make_officer(args.policy, args.state_format, safety=not args.no_safety, lessons=args.lessons,
                           seed=seed, limit=args.history)
    label = officer.name + (" + lessons" if args.lessons and args.policy.startswith("jev") else "")
    print(f"=== Run {n}: {label}, map {args.map}, {args.ticks} ticks, seed {seed}{' (EXAM)' if args.exam else ''} ===")
    simpler = {"pedestrians": not args.no_pedestrians, "ambulances": not args.no_ambulances}
    city, trace = play(officer, seed, args.map, args.ticks, watch=args.watch, **simpler)

    rules, _ = play(GreedyOfficer(), seed, args.map, args.ticks, quiet=True, **simpler)  # the same traffic, simple rules
    run = {"run": n, "policy": label, "map": args.map, "seed": seed, "ticks": args.ticks, "exam": args.exam,
           "score": city.score, "energy": city.energy, "rules_score": rules.score, "rules_energy": rules.energy,
           "score_by_tick": [t["score_after"] for t in trace], "layout": city.layout(), "trace": trace}
    (RUNS_DIR / f"run-{n:03d}.json").write_text(json.dumps(run, separators=(",", ":")))
    write_viewer_data()

    print(f"\nFinal score: {city.score}   energy used: {city.energy}   trips finished: {len(city.trips)}")
    print(f"Simple rules on the same traffic: score {rules.score}, energy {rules.energy}")
    print("Points and energy per 50 ticks (does it get better during the stream?):")
    for first, last, points, energy in blocks(trace):
        print(f"  ticks {first:>3}-{last:<3}  points {points:>7.1f}   energy {energy:>5}")
    tokens = sum(t["decision"].get("tokens", 0) for t in trace)
    if tokens:
        calls = sum(t["decision"].get("calls", 0) for t in trace)
        print(f"Jev calls: {calls}, input tokens: {tokens}")
    if args.exam:
        print(f"\nEXAM SCORE: {city.score}   <- post this on the leaderboard")
    print(f"\nReplay: open level5-junction/viewer3d.html  |  runs saved in {RUNS_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
