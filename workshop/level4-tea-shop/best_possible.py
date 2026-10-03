"""
Level 4 - How do we know the best possible score? We try EVERY plan.

Customers arrive the same way whatever you do, so we can plan the whole day.
16 rounds x 4 actions is too many plans to list (4^16), but many plans reach the
same situation (same round, queue, stock, energy). We remember each situation's best
result and reuse it ("memoization"). Then it takes less than a second.

Run:  python level4-tea-shop/best_possible.py
"""
import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shop  # noqa: E402


def best_possible(seed):
    """Best score for one day. Queue = number of customers who waited 0, 1 and 2 rounds."""
    s = shop.Shop(seed)
    arrivals = []
    for r in range(shop.ROUNDS):
        s.round = r
        arrivals.append(s.arrivals())

    @functools.lru_cache(maxsize=None)
    def best(r, queue, pearls, tea, energy):
        if r == shop.ROUNDS:
            return 0
        top = None
        for action in shop.ACTIONS:
            q = [queue[0] + arrivals[r], queue[1], queue[2]]
            p, t, e, served = pearls, tea, energy, 0
            if action == "make_drinks" and e > 0:
                served = left_to_serve = min(sum(q), 5 if e > 2 else 2, p, t)
                for w in (2, 1, 0):  # the oldest customers are served first
                    take = min(q[w], left_to_serve)
                    q[w] -= take
                    left_to_serve -= take
                p, t, e = p - served, t - served, e - 1
            elif action == "cook_pearls":
                p = min(shop.CAP, p + 15)
            elif action == "brew_tea":
                t = min(shop.CAP, t + 15)
            elif action == "rest":
                e = min(10, e + 4)
            total = 2 * served - 3 * q[2] + best(r + 1, (0, q[0], q[1]), p, t, e)
            top = total if top is None else max(top, total)
        return top

    return best(0, (0, 0, 0), 10, 12, 8)


if __name__ == "__main__":
    for seed in (1, 2, 3):
        print(f"seed {seed}: best possible {best_possible(seed)} points")
