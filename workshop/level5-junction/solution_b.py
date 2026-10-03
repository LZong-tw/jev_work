"""
Level 5 - Solution B: a short memory plus the coach's lessons. About 4x fewer tokens.

The full history grows every tick: by tick 200 one call is about 20,000 tokens, and a run
is about 2.5 million. Most of that is old news. Here Jev reads only the last 20 ticks,
and the coach's LESSONS carry what was learned from everything before.

Compare with solution A: what do you lose, what do you save?

Run:  python level5-junction/solution_b.py            (exam traffic, seed 2026)
Real results with jev-latest: see workshop/results/RESULTS.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from officers import GreedyOfficer, JevOfficer  # noqa: E402
from run import EXAM_SEED, play  # noqa: E402

LAST_TICKS = 20


def officer():
    return JevOfficer(history=True, lessons=True, limit=LAST_TICKS)


def main():
    city, trace = play(officer(), EXAM_SEED, quiet=True)
    rules, _ = play(GreedyOfficer(), EXAM_SEED, quiet=True)
    tokens = sum(t["decision"].get("tokens", 0) for t in trace)
    print(f"Solution B: score {city.score}, energy {city.energy}, input tokens {tokens}")
    print(f"Simple rules on the same traffic: score {rules.score}, energy {rules.energy}")


if __name__ == "__main__":
    main()
