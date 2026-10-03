"""
Level 4 - Solution B: keep the easy rules in code, let Jev choose the rest.

Starts from solution A (better question + advice), and adds:
  3. GUARD rules: when stock or energy is almost empty, code decides. No AI needed.
  4. Only offer actions that make sense right now. The list of choices can change every round.

Run:  python level4-tea-shop/solution_b.py
Real results with jev-latest: see workshop/results/RESULTS.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shop  # noqa: E402
from solution_a import DAY_QUESTIONS, BetterShop, play  # noqa: E402,F401


def guard(s):
    """Fix 3: hard rules stay in code. Returns an action, or None to let Jev decide."""
    if s.pearls < 5:
        return "cook_pearls"
    if s.tea < 5:
        return "brew_tea"
    if s.energy <= 2:
        return "rest"
    return None


def sensible_actions(s):
    """Only offer actions that make sense now. The list of choices can change every round."""
    acts = {}
    if s.queue:
        acts["make_drinks"] = shop.ACTIONS["make_drinks"]
    if s.pearls <= 15:
        acts["cook_pearls"] = shop.ACTIONS["cook_pearls"]
    if s.tea <= 15:
        acts["brew_tea"] = shop.ACTIONS["brew_tea"]
    if s.energy <= 6:
        acts["rest"] = shop.ACTIONS["rest"]
    return acts or {"rest": shop.ACTIONS["rest"]}


def guarded_policy(s):
    """Fixes 1 + 2 + 3."""
    forced = guard(s)
    if forced:
        return forced, None
    acts = sensible_actions(s)
    if len(acts) == 1:
        return next(iter(acts)), None
    question = dict(DAY_QUESTIONS["action"], criteria=acts)
    a = shop.decide(state=s.describe(), questions={"action": question})["answers"]
    return a["action"]["choice"], a


def main():
    print(f"{'SEED':<6}{'RULES':>8}{'B':>6}")
    for seed in (1, 2, 3):
        print(f"{seed:<6}{play(shop.Shop, shop.rules_policy, seed):>8}{play(BetterShop, guarded_policy, seed):>6}")


if __name__ == "__main__":
    main()
