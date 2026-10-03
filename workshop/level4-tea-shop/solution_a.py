"""
Level 4 - Solution A: better words only (no extra code rules).

Two changes, both are just text:
  1. A better QUESTION: ask for the most points by the END of the day, not "this round".
     (The starter question makes Jev greedy: it serves until the pearls run out.)
  2. A better describe(): tell Jev when the rush comes, and give advice.

Run:  python level4-tea-shop/solution_a.py
Real results with jev-latest: see workshop/results/RESULTS.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shop  # noqa: E402

RUSH_TIMES = ("12:00", "12:30", "13:00", "17:30", "18:00")


class BetterShop(shop.Shop):
    def rounds_until_rush(self):
        for ahead in range(0, shop.ROUNDS - self.round):
            minutes = 11 * 60 + (self.round + ahead) * 30
            if f"{minutes // 60:02d}:{minutes % 60:02d}" in RUSH_TIMES:
                return ahead
        return None

    def describe(self):
        text = super().describe()
        rush = self.rounds_until_rush()
        leaving = bool(self.queue) and max(self.queue) >= shop.MAX_WAIT
        hints = []
        if leaving:
            hints.append("Some customers are about to leave: serve them this round.")
        if rush == 0:
            hints.append("RUSH NOW: serve as many customers as possible.")
        elif rush is not None:
            hints.append(f"Next rush (many customers) starts in {rush} round(s).")
            if rush <= 2 and not leaving:
                if self.pearls < 15 or self.tea < 15:
                    hints.append("Restock pearls and tea BEFORE the rush, while customers can still wait.")
                elif self.energy <= 4:
                    hints.append("Rest now so the staff are fresh for the rush.")
        if self.energy <= 4 and len(self.queue) <= 2 and not leaving:
            hints.append("Quiet moment and low energy: a good time to rest.")
        hints.append(f"Rounds left today: {shop.ROUNDS - self.round}.")
        return text + "\nAdvice: " + " ".join(hints)


DAY_QUESTIONS = {
    "action": shop.choice(
        "You manage this bubble tea shop for the whole day. Read the Advice line carefully. "
        "Sometimes the best action gives 0 points now but many points later (restock or rest before a rush). "
        "Choose the action that gives the most points by the END of the day.",
        shop.ACTIONS,
    ),
}


def day_policy(s):
    """Fixes 1 + 2: the better question (use it with BetterShop for the advice)."""
    a = shop.decide(state=s.describe(), questions=DAY_QUESTIONS)["answers"]
    return a["action"]["choice"], a


def play(shop_class, policy, seed):
    s = shop_class(seed)
    for _ in range(shop.ROUNDS):
        s.open_round()
        s.update_mode()
        action, _ = policy(s)
        s.step(action)
    return s.points


def main():
    print(f"{'SEED':<6}{'RULES':>8}{'STARTER':>9}{'A':>6}")
    for seed in (1, 2, 3):
        rules = play(shop.Shop, shop.rules_policy, seed)
        starter = play(shop.Shop, shop.jev_policy, seed)
        better = play(BetterShop, day_policy, seed)
        print(f"{seed:<6}{rules:>8}{starter:>9}{better:>6}")


if __name__ == "__main__":
    main()
