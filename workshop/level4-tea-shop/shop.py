"""
Level 4 - Decisions in a loop: run a bubble tea shop for one day.

Until now: one message -> one decision.
Now:       state -> decision -> action -> NEW state -> decision -> ...

    +-----------+    state     +-----+   action   +-----------+
    |  the shop | -----------> | Jev | ---------> |  the shop |
    |  (state)  | <----------- +-----+            |  changes  |
    +-----------+     points + new state          +-----------+

The code is a STATE MACHINE. It owns the rules (stock, energy, customers).
Jev only picks the next action. Every round gives points:
    +2 for each drink served
    -3 for each customer who leaves angry (waited too long)

Run:
    python level4-tea-shop/shop.py              # Jev runs the shop
    python level4-tea-shop/shop.py --rules      # simple if/else rules run the shop
    python level4-tea-shop/shop.py --seed 7     # a different day
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev import choice, decide, noul  # noqa: E402

ROUNDS = 16  # 11:00 to 18:30, one round = 30 minutes
MAX_WAIT = 2  # customers leave after waiting more than 2 rounds
CAP = 30

ACTIONS = {
    "make_drinks": "serve up to 5 waiting customers (needs pearls, tea and energy)",
    "cook_pearls": "cook a new pot of tapioca pearls: +15 pearls, nobody is served this round",
    "brew_tea": "brew a new bucket of tea: +15 cups of tea, nobody is served this round",
    "rest": "staff take a short break: +4 energy, nobody is served this round",
}


class Shop:
    """All the rules live here. Jev never changes the rules, it only chooses actions."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.round = 0
        self.queue = []  # each customer = how many rounds they have waited
        self.pearls = 10
        self.tea = 12
        self.energy = 8
        self.points = 0
        self.served = 0
        self.angry = 0
        self.weather = self.rng.choice(["sunny", "hot", "rainy"])
        self.mode = "OPEN"

    def clock(self):
        minutes = 11 * 60 + self.round * 30
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def arrivals(self):
        n = 2 + self.rng.randint(0, 2)
        if self.weather == "hot":
            n += 2
        if self.weather == "rainy":
            n -= 1
        if self.clock() in ("12:00", "12:30", "13:00", "17:30", "18:00"):  # lunch + after work
            n += 3
        return max(0, n)

    def update_mode(self):
        """The state machine. The mode is computed from the state, by code."""
        if self.pearls == 0 or self.tea == 0:
            new = "SOLD_OUT"
        elif self.energy <= 2:
            new = "TIRED"
        elif len(self.queue) >= 8:
            new = "RUSH"
        else:
            new = "OPEN"
        changed = new != self.mode
        old, self.mode = self.mode, new
        return f"{old} -> {new}" if changed else None

    def describe(self):
        """What Jev sees. Good descriptions = good decisions."""
        longest = max(self.queue) if self.queue else 0
        return (
            f"Bubble tea shop at {self.clock()} (round {self.round + 1} of {ROUNDS}). Weather: {self.weather}.\n"
            f"Mode: {self.mode}.\n"
            f"Customers waiting: {len(self.queue)} (longest wait: {longest} rounds; they leave after {MAX_WAIT}).\n"
            f"Tapioca pearls left: {self.pearls}. Tea left: {self.tea} cups. Staff energy: {self.energy}/10.\n"
            f"One drink needs 1 pearl portion, 1 cup of tea. Making drinks uses 1 energy.\n"
            f"Points so far: {self.points}."
        )

    def open_round(self):
        """New customers walk in. This happens BEFORE we decide."""
        self.queue += [0] * self.arrivals()

    def step(self, action):
        served = 0
        if action == "make_drinks" and self.energy > 0:
            limit = 5 if self.energy > 2 else 2
            served = min(len(self.queue), limit, self.pearls, self.tea)
            self.queue = self.queue[served:]
            self.pearls -= served
            self.tea -= served
            self.energy -= 1
        elif action == "cook_pearls":
            self.pearls = min(CAP, self.pearls + 15)
        elif action == "brew_tea":
            self.tea = min(CAP, self.tea + 15)
        elif action == "rest":
            self.energy = min(10, self.energy + 4)

        self.queue = [w + 1 for w in self.queue]
        left = sum(1 for w in self.queue if w > MAX_WAIT)
        self.queue = [w for w in self.queue if w <= MAX_WAIT]

        gained = 2 * served - 3 * left
        self.points += gained
        self.served += served
        self.angry += left
        self.round += 1
        return served, left, gained


def rules_policy(shop):
    """A simple if/else officer to compare with."""
    if shop.pearls < 5:
        return "cook_pearls", None
    if shop.tea < 5:
        return "brew_tea", None
    if shop.energy <= 2:
        return "rest", None
    return "make_drinks", None


QUESTIONS = {
    "action": choice(
        "You manage this bubble tea shop. Choose the best action for this round to get the most points "
        "today. Serve customers before they leave, but do not run out of pearls, tea or energy.",
        ACTIONS,
    ),
    "pearls_soon_empty": noul("If we keep serving, will the pearls run out in the next 2 rounds?"),
}


def jev_policy(shop):
    a = decide(state=shop.describe(), questions=QUESTIONS)["answers"]
    return a["action"]["choice"], a


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", action="store_true", help="use the if/else rules instead of Jev")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    shop = Shop(args.seed)
    policy = rules_policy if args.rules else jev_policy
    print(f"Weather today: {shop.weather}.  Manager: {'rules' if args.rules else 'Jev'}\n")
    print(f"{'TIME':<6}{'MODE':<10}{'QUEUE':>6}{'PEARL':>6}{'TEA':>5}{'NRG':>5}  {'ACTION':<12}{'POINTS':>8}  NOTE")

    for _ in range(ROUNDS):
        shop.open_round()
        transition = shop.update_mode()  # the state machine moves BEFORE we decide
        before = (shop.clock(), shop.mode, len(shop.queue), shop.pearls, shop.tea, shop.energy)
        action, answers = policy(shop)
        served, left, gained = shop.step(action)

        note = []
        if answers:
            note.append(f"conf {answers['action']['confidence']:.2f}")
            if answers["pearls_soon_empty"]["noul"] > 0.6:
                note.append("pearls running low?")
        if left:
            note.append(f"{left} left angry!")
        if transition:
            note.append(transition)
        print(f"{before[0]:<6}{before[1]:<10}{before[2]:>6}{before[3]:>6}{before[4]:>5}{before[5]:>5}  "
              f"{action:<12}{gained:>+8}  {', '.join(note)}")

    print(f"\nEnd of day: {shop.points} points. Served {shop.served} drinks, {shop.angry} customers left angry.")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# TRY IT
# 1. Run with --rules, then with Jev, for seeds 1, 2, 3. Who wins? Write it down.
# 2. Improve describe(): add a hint like "Lunch rush at 12:00-13:00 and after
#    17:30". Does Jev plan ahead better?
#    Also read QUESTIONS: it asks for the best action "for this round".
#    Jev takes that literally. Ask for the most points by the END of the day.
# 3. Add a new action "call_friend": +2 serving capacity for 3 rounds, costs
#    5 points. Add it to ACTIONS and to step().
# 4. Look at the MODE column. Draw the state machine on paper:
#    OPEN, RUSH, TIRED, SOLD_OUT, and the arrows between them.
# ---------------------------------------------------------------------------
