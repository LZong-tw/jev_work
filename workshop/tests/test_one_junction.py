"""Level 5, the simple start: one junction, roads of 20 blocks x 4 lanes, crashes."""
import json
import re
import unittest
from unittest import mock

from helpers import add_path, choice_answer, noul_answer, response

add_path("level5-junction")
import one_junction as oj  # noqa: E402

quiet = lambda *_: None  # noqa: E731
RED = {s: {"light": [0, 0, 0, 0], "people": 0} for s in oj.SIDES}


def empty_junction():
    j = oj.Junction(1)
    j.lanes = {s: [[] for _ in range(4)] for s in oj.SIDES}
    j.people = {s: 0 for s in oj.SIDES}
    j.spawn = lambda pos=0: None  # no new traffic: only what the test puts there
    j.rain = False
    return j


def put(j, side, lane, pos, n=1):
    for _ in range(n):
        j.lanes[side][lane].append({"id": j.next_id, "pos": pos})
        j.next_id += 1


def plan(**roads):
    return {**RED, **{s: {"light": light, "people": people} for s, (light, people) in roads.items()}}


class Road(unittest.TestCase):
    def test_cars_move_one_block_and_add_up_at_the_stop_line(self):
        j = empty_junction()
        put(j, "left", 0, 15, n=3)  # [.. 3, 0, 0, 0, 1]: 3 cars 5 blocks away, 1 car at the line
        put(j, "left", 0, 19)
        self.assertEqual([b[0] for b in j.cars("left")[15:]], [3, 0, 0, 0, 1])
        j.step(RED)
        self.assertEqual([b[0] for b in j.cars("left")[15:]], [0, 3, 0, 0, 1])
        for _ in range(3):
            j.step(RED)
        self.assertEqual(j.cars("left")[19], [4, 0, 0, 0])  # on red they all wait at the line
        j.step(plan(left=([1, 0, 0, 0], 0)))
        self.assertEqual(j.cars("left")[19], [3, 0, 0, 0])  # green: 1 car per lane per tick
        self.assertEqual(j.history[-1]["cars_crossed"], 1)

    def test_the_officer_sees_20_blocks_of_4_lanes(self):
        j = oj.Junction(2026)
        road = j.cars("top")
        self.assertEqual((len(road), {len(b) for b in road}), (20, {4}))
        self.assertGreater(sum(map(sum, road)), 0)  # the road is not empty at the start


class Penalties(unittest.TestCase):
    def test_stuck_cars_cost_1_or_2_in_the_rush_hours(self):
        j = empty_junction()
        j.minute = 12 * 60  # midday
        put(j, "top", 1, 19, n=3)
        put(j, "top", 1, 10)  # a moving car is not stuck
        j.step(plan(top=([0, 1, 1, 0], 0)))  # 1 crosses, 2 stay
        self.assertEqual((j.history[-1]["stuck_cars"], j.history[-1]["points"]), (2, 1 - 2))
        j.minute = 8 * 60  # morning peak: people are late for work
        j.step(RED)
        self.assertEqual((j.history[-1]["stuck_cars"], j.history[-1]["points"]), (2, -4))

    def test_more_people_cross_in_the_rush_hours(self):
        j = empty_junction()
        j.minute = 12 * 60
        self.assertEqual(j.people_per_tick(), 3)
        j.rain = True
        self.assertEqual(j.people_per_tick(), 2)
        j.minute = 17 * 60 + 30
        self.assertEqual(j.people_per_tick(), 4)
        j.people["left"] = 9
        j.step(plan(left=([0, 0, 0, 0], 1)))
        self.assertEqual(j.history[-1]["walked"], {"left": 4})


class Crashes(unittest.TestCase):
    def test_left_turn_and_the_opposite_straight_crash(self):
        j = empty_junction()
        put(j, "top", 0, 19)
        put(j, "bottom", 1, 19)
        j.step(plan(top=([1, 0, 0, 0], 0), bottom=([0, 1, 1, 0], 0)))
        h = j.history[-1]
        self.assertEqual([c["kind"] for c in h["crashes"]], ["cars"])
        self.assertEqual(h["points"], -20)  # crashed cars give no points

    def test_a_right_turn_through_walking_people_hits_them(self):
        j = empty_junction()
        put(j, "bottom", 3, 19)  # from the bottom, a right turn goes into the right road
        j.people["right"] = 2
        j.step(plan(bottom=([0, 0, 0, 1], 0), right=([0, 0, 0, 0], 1)))
        self.assertEqual([c["kind"] for c in j.history[-1]["crashes"]], ["person"])
        self.assertEqual(j.history[-1]["points"], -50)

    def test_a_green_light_with_no_car_crashes_nothing(self):
        j = empty_junction()
        put(j, "top", 1, 19)
        j.step({s: {"light": [1, 1, 1, 1], "people": 1} for s in oj.SIDES})  # all green, but only 1 car
        self.assertEqual(j.history[-1]["crashes"], [])

    def test_the_traffic_rules(self):
        self.assertTrue(oj.conflict(("top", "L"), ("bottom", "S")))
        self.assertFalse(oj.conflict(("top", "L"), ("bottom", "L")))  # opposite left turns pass each other
        self.assertTrue(oj.conflict(("top", "S"), ("right", "S")))
        self.assertFalse(oj.conflict(("top", "S"), ("bottom", "S")))
        self.assertTrue(oj.conflict(("top", "S"), ("left", "R")))  # both go into the bottom road
        self.assertEqual([oj.exit_road("top", m) for m in "LSR"], ["right", "bottom", "left"])
        self.assertTrue(all(oj.safe(p) for p in oj.plans()))


class Officers(unittest.TestCase):
    def test_random_officer_10_ticks(self):
        j, frames, tokens = oj.play(oj.RandomOfficer(seed=1), seed=2026, ticks=10, out=quiet)
        self.assertEqual((len(j.history), len(frames), tokens), (10, 11, 0))
        self.assertGreater(sum(len(h["crashes"]) for h in j.history), 0)  # random lights crash
        again, _, _ = oj.play(oj.RandomOfficer(seed=1), seed=2026, ticks=10, out=quiet)
        self.assertEqual(j.history, again.history)  # same seed, same run

    def test_rules_officer_never_crashes(self):
        j, _, _ = oj.play(oj.RulesOfficer(), seed=7, ticks=30, start="16:30", out=quiet)
        self.assertEqual(sum(len(h["crashes"]) for h in j.history), 0)
        rnd, _, _ = oj.play(oj.RandomOfficer(), seed=7, ticks=30, start="16:30", out=quiet)
        self.assertGreater(j.score, rnd.score)
        night, _, _ = oj.play(oj.RulesOfficer(), seed=7, ticks=36, start="23:00", out=quiet)
        self.assertGreater(night.score, 0)  # quiet roads: nobody gets stuck for long

    def test_jev_officer_10_ticks(self):
        sent = []

        def fake_decide(state, questions):
            sent.append((state, questions))
            return response({"switch": noul_answer(0.8)})  # always: switch

        with mock.patch.object(oj, "decide", fake_decide):
            j, frames, tokens = oj.play(oj.JevOfficer(), seed=2026, ticks=10, out=quiet)
        self.assertEqual(len(sent), 9)  # one yes/no per tick; tick 1 is the minimum green, no question
        self.assertEqual(tokens, 9 * 42)
        names = [oj.CYCLE[i % 5][0] for i in range(10)]  # switching every tick walks through the cycle
        self.assertEqual([h["decision"] for h in j.history], [oj.PLANS[n][0] for n in names])
        self.assertEqual(sum(len(h["crashes"]) for h in j.history), 0)
        state, questions = sent[0]
        self.assertEqual(questions["switch"]["type"], "noul")
        self.assertIn("NOW: phase 1 (top/bottom straight + right turn), green for 1 ticks.", state)
        self.assertRegex(state, r"green now: \d+ cars waiting at its lights, \d+ more arriving")
        self.assertRegex(state, r"next phase 2 \(top/bottom left turns.*\): \d+ cars waiting")
        self.assertIn("LAST", sent[-1][0])

    def test_jev_with_memory_reads_what_its_own_decisions_led_to(self):
        sent = []

        def fake_decide(state, questions):
            sent.append(state)
            return response({"switch": noul_answer(0.8 if len(sent) % 2 else 0.2)})

        with mock.patch.object(oj, "decide", fake_decide):
            j, _, _ = oj.play(oj.JevOfficer(memory=True), ticks=12, out=quiet)
        self.assertNotIn("YOUR PAST DECISIONS", sent[0])  # nothing known yet
        last = sent[-1]
        self.assertRegex(last, r"YOUR PAST DECISIONS \(\d+ so far\)")
        self.assertRegex(last, r"still waiting on green, you (switched|kept green): \d+ times, average [+-]\d")
        self.assertRegex(last, r"Now: (0|1-4|5\+) cars still waiting on green\.")

    def test_a_run_has_3_days_and_scores_per_day(self):
        self.assertEqual(oj.TICKS_PER_DAY, 144)
        j, _, _ = oj.play(oj.FixedTimer(), ticks=3 * 144, start="00:00", out=quiet)
        days = oj.per_day(j)
        self.assertEqual(len(days), 3)
        self.assertAlmostEqual(sum(days), j.score, places=1)
        self.assertEqual((j.history[0]["time"], j.history[144]["time"]), ("00:00", "00:00"))

    def test_the_light_keeps_min_and_max_green(self):
        class Never(oj.TimingOfficer):
            def switch(self, j):
                return False, None

        j, _, _ = oj.play(Never(), ticks=14, out=quiet)
        phases = [h["decision"] for h in j.history]
        self.assertEqual(phases[:6], [oj.PLANS["top_bottom_go"][0]] * 6)  # at most 6 ticks green
        self.assertEqual(phases[6:12], [oj.PLANS["top_bottom_left_turns"][0]] * 6)
        fixed, _, _ = oj.play(oj.FixedTimer(), ticks=7, out=quiet)
        self.assertEqual([h["decision"] for h in fixed.history][2:4],
                         [oj.PLANS["top_bottom_go"][0], oj.PLANS["top_bottom_left_turns"][0]])

    def test_every_plan_is_safe(self):
        self.assertTrue(all(oj.safe(p) for p, _ in oj.PLANS.values()))

    def test_runs_are_saved_for_the_viewer(self):
        import tempfile
        from pathlib import Path
        folder = Path(tempfile.mkdtemp())
        with mock.patch.object(oj, "RUNS_DIR", folder):
            j, frames, tokens = oj.play(oj.RulesOfficer(), ticks=5, out=quiet)
            oj.save_run("rules", 2026, "07:00", j, frames, tokens)
        js = (folder / "one_runs.js").read_text()
        self.assertTrue(js.startswith("window.ONE_JUNCTION_RUNS = "))
        run = json.loads(js[len("window.ONE_JUNCTION_RUNS = "):].rstrip().rstrip(";"))[0]
        self.assertEqual((run["officer"], len(run["frames"])), ("rules", 6))


if __name__ == "__main__":
    unittest.main()
