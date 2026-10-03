"""
Level 5 - Solution A: let the coach digest the history.

The starter officer reads the whole history, but raw history is hard to use: Jev answers
ONE question at a time, it does not work out "my points are falling BECAUSE nobody walked".
(Real test: it almost never chose walk, 240 people were waiting at the end.)

So we add the coach. HORIZON ticks after each decision (when its future is already past),
the coach replays that moment with every action and writes down which one was better.
Jev then reads short LESSONS for moments like now: "walk +0.8, east_west -0.2, ...".
The history is the same; it is just digested.

Run:  python level5-junction/solution_a.py            (exam traffic, seed 2026)
Real results with jev-latest: see workshop/results/RESULTS.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from officers import GreedyOfficer, JevOfficer  # noqa: E402
from run import EXAM_SEED, play  # noqa: E402


def officer():
    return JevOfficer(history=True, lessons=True)


def main():
    city, _ = play(officer(), EXAM_SEED, quiet=True)
    rules, _ = play(GreedyOfficer(), EXAM_SEED, quiet=True)
    print(f"Solution A: score {city.score}, energy {city.energy}")
    print(f"Simple rules on the same traffic: score {rules.score}, energy {rules.energy}")


if __name__ == "__main__":
    main()
