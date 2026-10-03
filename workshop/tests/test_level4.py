"""Level 4: the tea shop rules, the state machine, and the decision loop."""
import contextlib
import functools
import io
import re
import sys
import unittest
from unittest import mock

from helpers import add_path, choice_answer, load, load_solutions, noul_answer, response, run_script

import jev

add_path("level4-tea-shop")
shop = load("level4-tea-shop/shop.py", "shop")
sys.modules["shop"] = shop  # the solutions do "import shop": share this instance


def optimum(seed):
    return load("level4-tea-shop/best_possible.py", "shop_best").best_possible(seed)


def fresh(seed=1, **state):
    s = shop.Shop(seed)
    for k, v in state.items():
        setattr(s, k, v)
    return s


class Rules(unittest.TestCase):
    def test_same_seed_same_day(self):
        a, b = shop.Shop(5), shop.Shop(5)
        self.assertEqual(a.weather, b.weather)
        self.assertEqual([a.arrivals() for _ in range(10)], [b.arrivals() for _ in range(10)])

    def test_make_drinks_is_limited_by_queue_stock_and_energy(self):
        s = fresh(queue=[0] * 8, pearls=30, tea=30, energy=8)
        served, left, gained = s.step("make_drinks")
        self.assertEqual((served, gained), (5, 10))  # max 5 per round, +2 each
        self.assertEqual((s.pearls, s.tea, s.energy), (25, 25, 7))

        s = fresh(queue=[0] * 8, pearls=3, tea=30, energy=8)
        self.assertEqual(s.step("make_drinks")[0], 3)  # out of pearls

        s = fresh(queue=[0] * 8, pearls=30, tea=30, energy=2)
        self.assertEqual(s.step("make_drinks")[0], 2)  # tired: only 2

        s = fresh(queue=[0] * 8, pearls=30, tea=30, energy=0)
        self.assertEqual(s.step("make_drinks")[0], 0)  # exhausted

    def test_restock_and_rest_have_caps(self):
        s = fresh(pearls=20, tea=25, energy=8)
        s.step("cook_pearls")
        self.assertEqual(s.pearls, shop.CAP)
        s.step("brew_tea")
        self.assertEqual(s.tea, shop.CAP)
        s.step("rest")
        self.assertEqual(s.energy, 10)

    def test_customers_leave_after_waiting_too_long(self):
        s = fresh(queue=[shop.MAX_WAIT, shop.MAX_WAIT, 0], pearls=10, tea=10)
        served, left, gained = s.step("rest")
        self.assertEqual((served, left, gained), (0, 2, -6))
        self.assertEqual(s.queue, [1])
        self.assertEqual(s.angry, 2)

    def test_points_add_up(self):
        s = shop.Shop(3)
        total = 0
        for _ in range(shop.ROUNDS):
            s.open_round()
            s.update_mode()
            total += s.step(shop.rules_policy(s)[0])[2]
        self.assertEqual(total, s.points)
        self.assertEqual(s.round, shop.ROUNDS)

    def test_rules_baseline_scores(self):
        # These numbers are printed on the slides and in the instructor guide.
        from_solution, _ = load_solutions("level4-tea-shop")
        scores = [from_solution.play(shop.Shop, shop.rules_policy, seed) for seed in (1, 2, 3)]
        self.assertEqual(scores, [47, 30, 41])


class StateMachine(unittest.TestCase):
    def test_modes(self):
        cases = [
            (dict(pearls=0, tea=10, energy=8, queue=[]), "SOLD_OUT"),
            (dict(pearls=10, tea=0, energy=8, queue=[]), "SOLD_OUT"),
            (dict(pearls=10, tea=10, energy=2, queue=[0] * 9), "TIRED"),
            (dict(pearls=10, tea=10, energy=8, queue=[0] * 8), "RUSH"),
            (dict(pearls=10, tea=10, energy=8, queue=[0] * 7), "OPEN"),
        ]
        for state, mode in cases:
            with self.subTest(mode=mode):
                s = fresh(**state)
                s.update_mode()
                self.assertEqual(s.mode, mode)

    def test_transition_is_reported_once(self):
        s = fresh(queue=[0] * 8)
        self.assertEqual(s.update_mode(), "OPEN -> RUSH")
        self.assertIsNone(s.update_mode())

    def test_rules_policy(self):
        self.assertEqual(shop.rules_policy(fresh(pearls=2))[0], "cook_pearls")
        self.assertEqual(shop.rules_policy(fresh(pearls=10, tea=2))[0], "brew_tea")
        self.assertEqual(shop.rules_policy(fresh(pearls=10, tea=10, energy=1))[0], "rest")
        self.assertEqual(shop.rules_policy(fresh(pearls=10, tea=10, energy=8))[0], "make_drinks")


class DecisionLoop(unittest.TestCase):
    def test_describe_has_the_facts_jev_needs(self):
        text = fresh(queue=[0, 1, 2], pearls=7, tea=9, energy=4).describe()
        for needle in ("11:00", "Customers waiting: 3", "longest wait: 2", "pearls left: 7", "Tea left: 9", "energy: 4/10"):
            self.assertIn(needle, text)

    def test_questions_are_valid(self):
        jev.mock_decide({"model": "jev-latest", "state": "x", "questions": shop.QUESTIONS})
        self.assertEqual(set(shop.QUESTIONS["action"]["criteria"]), set(shop.ACTIONS))

    def test_jev_policy_uses_the_choice(self):
        seen = []

        def fake(state, questions):
            seen.append(state)
            return response({"action": choice_answer("brew_tea"), "pearls_soon_empty": noul_answer(0.8)})

        with mock.patch.object(shop, "decide", fake):
            action, answers = shop.jev_policy(fresh())
        self.assertEqual(action, "brew_tea")
        self.assertEqual(answers["pearls_soon_empty"]["noul"], 0.8)
        self.assertIn("Bubble tea shop", seen[0])

    def test_scripted_jev_following_the_advice_beats_the_rules(self):
        """With solution_a.py's better description, a manager that simply follows the advice
        reaches the best possible score. The decision loop rewards planning ahead."""
        def follower(state, questions):
            num = lambda pattern: int(re.search(pattern, state).group(1))  # noqa: E731
            pearls, tea, energy = num(r"pearls left: (\d+)"), num(r"Tea left: (\d+)"), num(r"energy: (\d+)/10")
            if "BEFORE the rush" in state:
                act = "cook_pearls" if pearls < 15 and pearls <= tea else "brew_tea" if tea < 15 else "cook_pearls"
            elif "fresh for the rush" in state or "good time to rest" in state:
                act = "rest"
            elif pearls < 5:
                act = "cook_pearls"
            elif tea < 5:
                act = "brew_tea"
            elif energy <= 2:
                act = "rest"
            else:
                act = "make_drinks"
            return response({"action": choice_answer(act), "pearls_soon_empty": noul_answer(0.1)})

        solution, _ = load_solutions("level4-tea-shop")
        with mock.patch.object(shop, "decide", follower):
            advised = [solution.play(solution.BetterShop, shop.jev_policy, seed) for seed in (1, 2, 3)]
        rules = [solution.play(shop.Shop, shop.rules_policy, seed) for seed in (1, 2, 3)]
        self.assertEqual(rules, [47, 30, 41])
        self.assertEqual(advised, [optimum(seed) for seed in (1, 2, 3)])
        self.assertEqual(advised, [72, 60, 51])

    def test_main_prints_a_full_day(self):
        out = io.StringIO()
        with mock.patch("sys.argv", ["shop.py", "--rules", "--seed", "2"]), contextlib.redirect_stdout(out):
            shop.main()
        text = out.getvalue()
        self.assertIn("End of day: 30 points", text)
        self.assertIn("OPEN -> RUSH", text)
        self.assertEqual(sum(1 for line in text.splitlines() if line[:2] in ("11", "12", "13", "14", "15", "16", "17", "18")), shop.ROUNDS)


class Solution(unittest.TestCase):
    def setUp(self):
        self.a, self.b = load_solutions("level4-tea-shop")

    def test_better_describe_adds_advice(self):
        s = self.a.BetterShop(1)
        s.round = 1  # 11:30, rush at 12:00
        s.pearls = 4
        text = s.describe()
        self.assertIn("Next rush (many customers) starts in 1 round(s).", text)
        self.assertIn("Restock pearls and tea BEFORE the rush", text)
        self.assertIn("Rounds left today: 15.", text)
        s.queue = [shop.MAX_WAIT]
        text = s.describe()
        self.assertIn("about to leave", text)
        self.assertNotIn("BEFORE the rush", text)  # never restock while someone is leaving
        s.queue, s.pearls, s.tea, s.energy = [], 20, 20, 3
        self.assertIn("fresh for the rush", s.describe())
        s.round = 2
        self.assertIn("RUSH NOW", s.describe())

    def test_guard_rules_decide_without_jev(self):
        def never(state, questions):
            raise AssertionError("Jev should not be asked")

        with mock.patch.object(shop, "decide", never):
            self.assertEqual(self.b.guarded_policy(fresh(pearls=3))[0], "cook_pearls")
            self.assertEqual(self.b.guarded_policy(fresh(tea=4))[0], "brew_tea")
            self.assertEqual(self.b.guarded_policy(fresh(energy=2))[0], "rest")
            # only one sensible action: no call needed
            self.assertEqual(self.b.guarded_policy(fresh(pearls=20, tea=20, energy=8, queue=[0]))[0], "make_drinks")

    def test_guarded_policy_offers_only_sensible_actions_and_the_day_question(self):
        seen = []

        def fake(state, questions):
            seen.append(questions["action"])
            return response({"action": choice_answer("cook_pearls")})

        s = fresh(pearls=10, tea=20, energy=8)
        s.queue = [0, 0]
        with mock.patch.object(shop, "decide", fake):
            action, _ = self.b.guarded_policy(s)
            day_action, _ = self.a.day_policy(s)
        self.assertEqual((action, day_action), ("cook_pearls", "cook_pearls"))
        self.assertEqual(sorted(seen[0]["criteria"]), ["cook_pearls", "make_drinks"])
        self.assertIn("END of the day", seen[0]["instructions"])
        self.assertEqual(sorted(seen[1]["criteria"]), sorted(shop.ACTIONS))
        self.assertEqual(sorted(self.a.DAY_QUESTIONS["action"]["criteria"]), sorted(shop.ACTIONS))  # not changed

    def test_runs_end_to_end_in_mock_mode(self):
        for name in ("solution_a.py", "solution_b.py", "best_possible.py"):
            r = run_script(f"level4-tea-shop/{name}", JEV_MOCK=1)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(len(r.stdout.strip().splitlines()), 4 if name != "best_possible.py" else 3)

    def test_shop_runs_in_mock_mode(self):
        r = run_script("level4-tea-shop/shop.py", "--seed", "3", JEV_MOCK=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("End of day:", r.stdout)
        self.assertIn("conf", r.stdout)


if __name__ == "__main__":
    unittest.main()
