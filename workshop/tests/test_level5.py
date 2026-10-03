"""Level 5: the city (roads, dynamic speeds, lights, points), the state as map/array, the coach,
memory, officers, the CLI, and an end-to-end learning experiment with a scripted (mocked) Jev."""
import copy
import json
import os
import random
import re
import shutil
import statistics
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import add_path, choice_answer, load, noul_answer, response, run_script

import jev

_RUNS = tempfile.mkdtemp(prefix="city-test-")
os.environ["JUNCTION_RUNS_DIR"] = _RUNS  # never touch the participant's real memory
add_path("level5-junction")
import city as C  # noqa: E402
import coach  # noqa: E402
import memory  # noqa: E402
import officers  # noqa: E402
import run  # noqa: E402

L = C.LENGTH
FZ = "fuxing_zhongxiao"
BASELINES = {"greedy": 165.3, "fixed": -317.6}  # exam (seed 2026, map three, 200 ticks): in the README and slides


def tearDownModule():
    os.environ.pop("JUNCTION_RUNS_DIR", None)
    shutil.rmtree(_RUNS, ignore_errors=True)


class NoLuck:
    """Driving randomness switched off: nobody dawdles, everybody goes straight."""

    def random(self):
        return 0.99

    def choices(self, population, weights=None):
        return ["straight"]


def empty_city(map_name="single", light="NS"):
    c = C.City(0, map_name)
    c.drive = NoLuck()
    for seg in c.segments.values():
        seg.cars = []
    for q in c.backlog.values():
        q.clear()
    for j in c.junctions.values():
        j.light, j.pedestrians = light, []
    return c


def put(c, sid, kind="car", pos=0, speed=0, turn="straight"):
    v = c.new_vehicle(kind)
    v.update(pos=pos, speed=speed, turn=turn)
    c.segments[sid].cars.append(v)
    c.segments[sid].cars.sort(key=lambda x: -x["pos"])
    return v


def keep(c):
    return {jid: C.ACTION_OF[j.light] for jid, j in c.junctions.items()}


def play_rules(seed, map_name="three", policy="greedy", ticks=60):
    return run.play(officers.make_officer(policy), seed, map_name, ticks, quiet=True)


# ---------------------------------------------------------------------------
# The city: maps and roads
# ---------------------------------------------------------------------------

class Maps(unittest.TestCase):
    def test_maps_have_the_right_roads(self):
        three = C.City(1)
        self.assertEqual(list(three.junctions), ["fuxing_zhongxiao", "dunhua_zhongxiao", "guangfu_zhongxiao"])
        self.assertEqual(three.ticks, C.TICKS)
        for name, junctions, entries in [("single", 1, 4), ("corridor", 2, 6), ("three", 3, 8), ("grid", 4, 8)]:
            c = C.City(1, name)
            self.assertEqual(len(c.junctions), junctions, name)
            self.assertEqual(len(c.segments), 4 * junctions, name)
            self.assertEqual(len(c.entries), entries, name)
        grid = C.City(1, "grid")
        self.assertEqual(sorted(grid.junctions), ["dunhua_renai", "dunhua_zhongxiao", "fuxing_renai", "fuxing_zhongxiao"])
        self.assertEqual(grid.junctions[FZ].name, "Fuxing S. Rd x Zhongxiao E. Rd")
        self.assertEqual(grid.segments["dunhua_zhongxiao<west"].source, FZ)  # Zhongxiao links the two
        with self.assertRaises(ValueError):
            C.City(1, "atlantis")

    def test_routing_after_a_turn(self):
        g = C.City(1, "grid")
        west_in = g.segments[f"{FZ}<west"]  # heading east
        self.assertEqual(g.target(west_in, "straight")[0].id, "dunhua_zhongxiao<west")
        self.assertEqual(g.target(west_in, "right")[0].id, "fuxing_renai<north")  # right = south (drive on the right)
        self.assertIsNone(g.target(west_in, "left")[0])  # left = north: leaves the city
        self.assertEqual(g.target(west_in, "left")[1], "north")

    def test_same_seed_same_day(self):
        a = [t["roads"] for t in play_rules(5)[1]]
        b = [t["roads"] for t in play_rules(5)[1]]
        self.assertEqual(a, b)
        self.assertNotEqual(a, [t["roads"] for t in play_rules(6)[1]])
        self.assertEqual(len(a), 60)

    def test_traffic_comes_in_waves_and_rain_stops(self):
        c = C.City(1)
        north = c.segments[f"{FZ}<north"]
        rates = []
        for t in (0, C.WAVE, 2 * C.WAVE, 3 * C.WAVE):
            c.t = t
            rates.append(c.demand(north))
        self.assertEqual(rates[0], rates[3])  # the pattern comes back
        self.assertGreater(rates[0], rates[1])
        c.rain_from = 10
        c.t = 10 + C.RAIN_LENGTH
        self.assertFalse(c.raining())
        c.t = 10
        self.assertTrue(c.raining())

    def test_arrivals_never_depend_on_the_officer(self):
        a, b = C.City(9), C.City(9)
        for t in range(25):
            a.arrive()
            b.arrive()
            a.step(keep(a))
            b.step({jid: "walk" if t % 3 else "east_west" for jid in b.junctions})
        self.assertEqual(a.rng.getstate(), b.rng.getstate())
        self.assertEqual(a.next_id, b.next_id)  # the same vehicles were created


# ---------------------------------------------------------------------------
# Vehicles: dynamic speed (Nagel-Schreckenberg), crossing, spillback, ambulances
# ---------------------------------------------------------------------------

class Driving(unittest.TestCase):
    def test_speed_up_then_stop_at_a_red_light(self):
        c = empty_city(light="EW")  # red for vehicles from the north
        v = put(c, f"{FZ}<north")
        speeds, positions = [], []
        for _ in range(6):
            c.step(keep(c))
            speeds.append(v["speed"])
            positions.append(v["pos"])
        self.assertEqual(speeds[:3], [1, 2, 3])  # car: +1 per tick up to 3
        self.assertEqual(positions[:3], [1, 3, 6])
        self.assertEqual(positions[-1], L - 1)  # waits at the stop line
        self.assertEqual(speeds[-1], 0)
        self.assertGreater(v["wait"], 0)

    def test_kinds_accelerate_differently_and_rain_slows_them(self):
        c = empty_city(light="EW")
        scooter, bus = put(c, f"{FZ}<north", "scooter"), put(c, f"{FZ}<south", "bus")
        c.step(keep(c))
        self.assertEqual((scooter["speed"], bus["speed"]), (2, 1))
        c.rain_from = 0
        self.assertEqual([c.vmax(k) for k in ("scooter", "car", "bus", "ambulance")], [2, 2, 1, 4])

    def test_keeps_distance(self):
        c = empty_city(light="EW")  # red: the front car waits at the stop line
        front = put(c, f"{FZ}<north", pos=L - 1, speed=0)
        back = put(c, f"{FZ}<north", pos=L - 4, speed=3)
        c.step(keep(c))
        self.assertEqual(front["pos"], L - 1)
        self.assertEqual((back["pos"], back["speed"]), (L - 2, 2))  # brakes: stops right behind it
        c.step(keep(c))
        self.assertEqual((back["pos"], back["speed"]), (L - 2, 0))

    def test_green_crosses_one_vehicle_per_tick_and_scores(self):
        c = empty_city(light="NS")
        put(c, f"{FZ}<north", "bus", pos=L - 1, speed=0)
        put(c, f"{FZ}<north", "car", pos=L - 2, speed=0)
        c.step(keep(c))
        self.assertEqual(c.last["crossed"][FZ], ["bus"])  # one per tick
        self.assertEqual(c.last["parts"]["crossed"], 3)  # a bus is worth 3
        self.assertEqual(len(c.trips), 1)  # single map: it left the city
        c.step(keep(c))
        self.assertEqual(c.last["crossed"][FZ], ["car"])

    def test_turning_vehicles_slow_down(self):
        c = empty_city("grid", light="NS")
        straight = put(c, f"{FZ}<south", pos=L - 3, speed=3, turn="straight")  # -> leaves to the north
        c.step(keep(c))
        self.assertNotIn(straight, c.segments[f"{FZ}<south"].cars)
        c = empty_city("grid", light="EW")
        turner = put(c, f"{FZ}<west", pos=L - 3, speed=3, turn="right")  # -> fuxing_renai, slowly
        c.step(keep(c))
        self.assertIn(turner, c.segments["fuxing_renai<north"].cars)
        self.assertEqual(turner["pos"], 0)  # at most 1 cell past the junction

    def test_full_road_blocks_the_junction(self):
        c = empty_city("grid", light="EW")
        nxt = c.segments["dunhua_zhongxiao<west"]
        for p in range(L):
            put(c, nxt.id, pos=p)  # completely full
        c.junctions["dunhua_zhongxiao"].light = "NS"  # and it stays red there
        front = put(c, f"{FZ}<west", pos=L - 1, turn="straight")
        c.step(keep(c))
        self.assertIn(front, c.segments[f"{FZ}<west"].cars)  # spillback: cannot cross
        self.assertEqual(front["speed"], 0)
        self.assertEqual(c.state()["junctions"][FZ]["exit_room"]["EW"], 0)

    def test_a_road_accepts_one_vehicle_per_tick_from_the_junction(self):
        c = empty_city("grid", light="NS")
        # from north turning left (-> east) and from south turning right (-> east): same target road
        put(c, f"{FZ}<north", pos=L - 1, turn="left")
        put(c, f"{FZ}<south", pos=L - 1, turn="right")
        c.step(keep(c))
        self.assertEqual(len(c.segments["dunhua_zhongxiao<west"].cars), 1)

    def test_everybody_makes_way_for_an_ambulance(self):
        c = empty_city(light="NS")
        put(c, f"{FZ}<north", pos=L - 1)
        put(c, f"{FZ}<north", pos=L - 2)
        amb = put(c, f"{FZ}<north", "ambulance", pos=L - 4, speed=4)
        c.step(keep(c))
        self.assertEqual(sorted(c.last["crossed"][FZ]), ["ambulance", "car"])  # passed the queue, same tick
        self.assertNotIn(amb, c.segments[f"{FZ}<north"].cars)

        c = empty_city(light="EW")  # but a red light stops it
        amb = put(c, f"{FZ}<north", "ambulance", pos=L - 2, speed=4)
        c.step(keep(c))
        self.assertEqual((amb["pos"], amb["speed"]), (L - 1, 1))
        c.step(keep(c))
        self.assertEqual(amb["speed"], 0)
        self.assertEqual(c.last["parts"]["ambulance_stopped"], -10)


# ---------------------------------------------------------------------------
# Lights and points
# ---------------------------------------------------------------------------

class LightsAndPoints(unittest.TestCase):
    def test_yellow_then_minimum_green(self):
        c = empty_city(light="NS")
        put(c, f"{FZ}<east", pos=L - 1)
        c.step({FZ: "east_west"})
        j = c.junctions[FZ]
        self.assertTrue(j.yellow)
        self.assertEqual(c.last["crossed"][FZ], [])  # nothing crosses on yellow
        self.assertEqual(c.forced_actions(), {FZ: "east_west"})
        c.step({FZ: "north_south"})  # ignored: locked
        self.assertEqual((j.light, j.yellow), ("EW", False))
        self.assertEqual(c.last["crossed"][FZ], ["car"])
        self.assertEqual(c.forced_actions(), {})

    def test_walk_stops_cars_and_clears_people(self):
        c = empty_city(light="WALK")
        c.junctions[FZ].pedestrians = [3, 1, 0]
        put(c, f"{FZ}<north", pos=L - 1)
        c.step({FZ: "walk"})
        self.assertEqual(c.last["walked"][FZ], 3)
        self.assertEqual(c.junctions[FZ].pedestrians, [])
        self.assertEqual(c.last["crossed"][FZ], [])

    def test_points_add_up(self):
        c = empty_city(light="EW")
        c.junctions[FZ].pedestrians = [0, 0, 0, 0]
        stuck = put(c, f"{FZ}<north", pos=L - 1)
        stuck["wait"] = C.ANGRY_AFTER  # will be angry after this tick
        c.backlog[f"{FZ}<south"].extend([c.new_vehicle("car"), c.new_vehicle("car")])
        c.step(keep(c))
        p = c.last["parts"]
        self.assertEqual(p["stopped"], round(3 * C.POINTS["stopped"], 2))  # 1 stopped + 2 waiting outside
        self.assertEqual(p["pedestrians_waiting"], round(4 * C.POINTS["pedestrians_waiting"], 2))
        self.assertEqual(p["angry"], C.POINTS["angry"])
        self.assertAlmostEqual(sum(p.values()), c.last["reward"], places=6)
        self.assertEqual(c.score, c.last["reward"])
        self.assertEqual(c.last["energy"][FZ], 3)  # energy: every idling vehicle, also outside the city
        self.assertEqual((c.last["energy_total"], c.energy), (3, 3))

    def test_score_is_the_sum_of_rewards(self):
        city, trace = play_rules(3)
        self.assertAlmostEqual(sum(t["reward"] for t in trace), city.score, places=4)
        self.assertEqual(sum(t["energy"] for t in trace), city.energy)
        self.assertGreater(len(city.trips), 30)


# ---------------------------------------------------------------------------
# The state as data: map, array, text, picture
# ---------------------------------------------------------------------------

class StateAsData(unittest.TestCase):
    def setUp(self):
        self.c = play_rules(1)[0]

    def test_map_is_pure_json(self):
        s = self.c.state(vehicles=True)
        self.assertEqual(json.loads(json.dumps(s)), s)
        self.assertEqual(set(s), {"tick", "ticks", "map", "road_length", "weather", "score", "energy", "trips_finished",
                                  "junctions"})
        j = s["junctions"][FZ]
        self.assertEqual(set(j["approaches"]), set(C.DIRS))
        for side, a in j["approaches"].items():
            seg = self.c.segments[f"{FZ}<{side}"]
            self.assertEqual(a["vehicles"], len(seg.cars))
            self.assertEqual(len(a["cars"]), len(seg.cars))
            self.assertEqual(a["stopped"], sum(1 for v in a["cars"] if v["speed"] == 0))
        self.assertNotIn("cars", self.c.state()["junctions"][FZ]["approaches"]["north"])

    def test_array_has_a_name_for_every_number(self):
        values, names = self.c.state_array(), self.c.array_fields()
        self.assertEqual(len(values), len(names))
        self.assertEqual(len(values), 2 + 3 * (10 + 4 * 7))  # three junctions: 116
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(all(isinstance(v, float) for v in values))
        lookup = dict(zip(names, values))
        s = self.c.state()["junctions"][FZ]
        self.assertEqual(lookup[f"{FZ}.pedestrians"], s["pedestrians"])
        self.assertEqual(lookup[f"{FZ}.east.vehicles"], s["approaches"]["east"]["vehicles"])
        self.assertEqual(len(C.City(1, "single").state_array()), 2 + 38)

    def test_text_and_picture(self):
        text = self.c.describe()
        for needle in ("JUNCTION fuxing_zhongxiao (Fuxing S. Rd x Zhongxiao E. Rd)", "from north", "average speed",
                       "Free space on the roads after the junction", "Pedestrians waiting", "YELLOW tick"):
            self.assertIn(needle, text)
        picture = self.c.render()
        self.assertIn("Pedestrians waiting", picture)
        self.assertGreater(len(picture.splitlines()), 2 * L)

    def test_officers_have_limited_vision(self):
        c = empty_city(light="NS")
        put(c, f"{FZ}<east", pos=L - 1)          # near the stop line: visible
        put(c, f"{FZ}<east", pos=0)              # far away: not visible
        put(c, f"{FZ}<west", "ambulance", pos=0)  # far away, but you hear the siren
        full, seen = c.state(), c.state(vision=C.VISION)
        self.assertEqual(full["junctions"][FZ]["approaches"]["east"]["vehicles"], 2)
        self.assertEqual(seen["junctions"][FZ]["approaches"]["east"]["vehicles"], 1)
        self.assertTrue(seen["junctions"][FZ]["approaches"]["west"]["ambulance"])
        self.assertEqual(seen["junctions"][FZ]["approaches"]["west"]["vehicles"], 0)
        self.assertLessEqual(max(seen["junctions"][FZ]["exit_room"].values()), C.VISION)
        text = c.describe(only=[FZ], vision=C.VISION)
        self.assertIn(f"You can see {C.VISION} cells down each road", text)
        self.assertIn("from east  (city edge): 1 vehicles [c]", text)
        self.assertEqual(c.layout()["vision"], C.VISION)

    def test_ambulance_is_announced(self):
        c = empty_city()
        put(c, f"{FZ}<east", "ambulance", pos=3)
        self.assertIn("AMBULANCE coming from the east (you hear the siren)! Give green to east_west.", c.describe())
        self.assertTrue(c.state()["junctions"][FZ]["approaches"]["east"]["ambulance"])

    def test_snapshot_and_layout_for_the_viewer(self):
        snap, layout = self.c.snapshot(), self.c.layout()
        self.assertEqual(json.loads(json.dumps(snap)), snap)
        self.assertTrue(set(snap["roads"]) <= set(layout["roads"]))
        self.assertEqual(set(layout["junctions"]), set(self.c.junctions))

    def test_show_state_script(self):
        r = run_script("level5-junction/show_state.py", "--format", "map", "--tick", "5", "--vehicles")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["tick"], 5)
        r = run_script("level5-junction/show_state.py", "--format", "array", "--map", "single")
        self.assertEqual(len(json.loads(r.stdout.splitlines()[0])), 40)
        self.assertIn("fuxing_zhongxiao.light_NS", r.stdout)
        r = run_script("level5-junction/show_state.py", "--format", "text", "--map", "corridor")
        self.assertIn("JUNCTION dunhua_zhongxiao", r.stdout)


# ---------------------------------------------------------------------------
# Memory: relative situations and moves, lessons
# ---------------------------------------------------------------------------

def mirrored_pair():
    """Two moments that are the same up to a 90-degree turn."""
    a, b = empty_city(light="EW"), empty_city(light="NS")
    for p in range(4):
        put(a, f"{FZ}<north", pos=p)  # NS busy, EW green
        put(b, f"{FZ}<east", pos=p)  # EW busy, NS green
    return a.state(), b.state()


class Memory(unittest.TestCase):
    def test_moves_are_relative(self):
        a, b = mirrored_pair()
        self.assertEqual(memory.move_of(a, FZ, "north_south"), "busier")
        self.assertEqual(memory.move_of(b, FZ, "east_west"), "busier")
        self.assertEqual(memory.move_of(a, FZ, "walk"), "walk")
        self.assertEqual(memory.action_of(a, FZ, "busier"), "north_south")
        self.assertEqual(memory.action_of(b, FZ, "quieter"), "north_south")
        for move in memory.MOVES:
            self.assertEqual(memory.move_of(a, FZ, memory.action_of(a, FZ, move)), move)

    def test_mirrored_moments_share_a_situation(self):
        a, b = mirrored_pair()
        self.assertEqual(memory.situation(a, FZ), memory.situation(b, FZ))
        self.assertEqual(memory.situation(a, FZ),
                         "green=quieter | difference=big | ambulance=none | blocked=none | red_wait=short | pedestrians=few")
        self.assertEqual(memory.coarse(memory.situation(a, FZ)), "green=quieter | ambulance=none | blocked=none")

    def test_lessons_come_from_the_coach_and_blend_few_tries(self):
        lessons = memory.Lessons()
        here = "green=quieter | difference=big | ambulance=none | blocked=none | red_wait=long | pedestrians=few"
        other = "green=quieter | difference=small | ambulance=none | blocked=none | red_wait=short | pedestrians=some"
        lessons.learn(here, {"busier": 4.0, "quieter": -2.0, "walk": -2.0})
        for _ in range(3):
            lessons.learn(other, {"busier": 0.0, "quieter": 0.0, "walk": 0.0})
        rows = {mv: (round(e, 3), n, near) for mv, e, n, near in lessons.lessons(here)}
        # (4 + PRIOR * mean(4, 0, 0, 0)) / (1 + PRIOR) = (4 + 1) / 2
        self.assertEqual(rows["busier"], (2.5, 1, 4))
        self.assertEqual(rows["quieter"], (-1.25, 1, 4))
        self.assertEqual(lessons.lessons(here)[0][0], "busier")
        self.assertEqual(lessons.reviewed, 4)
        self.assertEqual(lessons.lessons("green=walk | difference=small | ambulance=busier | blocked=both | red_wait=long"
                                         " | pedestrians=many"), [])

    def test_lesson_lines_name_real_actions(self):
        a, _ = mirrored_pair()
        lessons = memory.Lessons()
        self.assertIn("no lessons yet", lessons.lines(a, FZ, "FZ"))
        lessons.learn(memory.situation(a, FZ), {"busier": 3.0, "quieter": -1.0, "walk": -2.0})
        self.assertEqual(lessons.lines(a, FZ, "FZ"), "  FZ: north_south +3.0 (2 tries), east_west -1.0 (2 tries), "
                                                     "walk -2.0 (2 tries)")


# ---------------------------------------------------------------------------
# The coach
# ---------------------------------------------------------------------------

class Coach(unittest.TestCase):
    def test_advantages_compare_with_the_average_move(self):
        adv = coach.advantages({"busier": 6.0, "quieter": 0.0, "walk": 3.0})
        self.assertEqual(adv, {"busier": 3.0, "quieter": -3.0, "walk": 0.0})

    def test_replay_does_not_change_the_real_city(self):
        c = C.City(2)
        for _ in range(20):
            c.arrive()
            c.step(keep(c))
        c.arrive()
        before = json.dumps(c.state(vehicles=True), sort_keys=True)
        r1 = coach.replay(c, FZ, keep(c))
        r2 = coach.replay(c, FZ, keep(c))
        self.assertEqual(r1, r2)  # same moment, same traffic, same result
        self.assertEqual(json.dumps(c.state(vehicles=True), sort_keys=True), before)

    def test_coach_sees_that_the_ambulance_needs_green(self):
        c = empty_city(light="NS")
        put(c, f"{FZ}<east", "ambulance", pos=L - 2, speed=1)
        reviewed = coach.review([(copy.deepcopy(c), keep(c), set())])
        points = reviewed[(0, FZ)]
        # the only vehicle is the ambulance on east_west, so "busier" = give it green
        self.assertGreater(points["busier"], points["quieter"] + 9)
        self.assertGreater(points["busier"], points["walk"] + 9)

    def test_review_skips_locked_junctions(self):
        c = empty_city("corridor")
        c.junctions[FZ].locked = 1
        reviewed = coach.review([(copy.deepcopy(c), keep(c), {FZ})])
        self.assertEqual(set(reviewed), {(0, "dunhua_zhongxiao")})
        self.assertEqual(set(reviewed[(0, "dunhua_zhongxiao")]), set(memory.MOVES))


# ---------------------------------------------------------------------------
# Officers
# ---------------------------------------------------------------------------

class Officers(unittest.TestCase):
    def test_fixed_timer_with_offsets(self):
        o, c = officers.FixedOfficer(), C.City(1, "grid")
        plan = []
        for t in range(13):
            c.t = t
            plan.append(o.act(c, list(c.junctions))["actions"])
        self.assertEqual([a[FZ] for a in plan], ["north_south"] * 6 + ["east_west"] * 6 + ["walk"])
        self.assertEqual(plan[0]["dunhua_zhongxiao"], "north_south")
        self.assertEqual(plan[3]["dunhua_zhongxiao"], "east_west")  # 3 ticks later in the cycle

    def test_greedy_rules(self):
        g = officers.GreedyOfficer()
        c = empty_city(light="NS")
        put(c, f"{FZ}<east", "ambulance", pos=2)
        self.assertEqual(g.act(c, [FZ])["actions"][FZ], "east_west")  # ambulance first
        c = empty_city(light="NS")
        c.junctions[FZ].pedestrians = [0] * 8
        self.assertEqual(g.act(c, [FZ])["actions"][FZ], "walk")
        c = empty_city(light="NS")
        for p in range(3):
            put(c, f"{FZ}<east", pos=L - 1 - p)
        self.assertEqual(g.act(c, [FZ])["actions"][FZ], "north_south")  # not clearly busier: keep
        put(c, f"{FZ}<west", pos=0)  # too far away to see
        self.assertEqual(g.act(c, [FZ])["actions"][FZ], "north_south")
        put(c, f"{FZ}<west", pos=L - 1)
        self.assertEqual(g.act(c, [FZ])["actions"][FZ], "east_west")
        c = empty_city(light="NS")
        put(c, f"{FZ}<north", pos=L - 2)
        put(c, f"{FZ}<north", pos=L - 3)
        v = put(c, f"{FZ}<east", pos=L - 1)
        v["wait"] = officers.GreedyOfficer.PATIENCE + 1
        self.assertEqual(g.act(c, [FZ])["actions"][FZ], "east_west")  # waited too long

    def test_jev_reads_the_whole_story_in_one_call(self):
        calls = []

        def fake(state, questions):
            calls.append((state, questions))
            return response({q: choice_answer("north_south", 0.6, ["east_west", "walk"]) for q in questions}, tokens=900)

        o = officers.JevOfficer()
        with mock.patch.object(officers, "decide", fake):
            city, trace = run.play(o, 2, "three", ticks=12, quiet=True)
        self.assertEqual(len(calls), sum(t["decision"].get("calls", 0) for t in trace))  # one call per tick (or 0)
        self.assertEqual(len(o.history), 12)  # every tick is remembered, also the locked ones
        state, questions = calls[-1]
        self.assertTrue(set(questions) <= set(city.junctions))
        for needle in ("TRAFFIC CONTROL on Zhongxiao E. Rd", "FZ = Fuxing S. Rd x Zhongxiao E. Rd", "GOAL:",
                       "ENERGY per junction per tick", "HISTORY, one line per tick", "NOW (tick", "costing now:"):
            self.assertIn(needle, state)
        lines = [line for line in state.splitlines() if line.startswith("t") and " | FZ " in line]
        self.assertGreaterEqual(len(lines), 10)  # the past ticks, oldest first
        self.assertTrue(lines[0].startswith("t1 | FZ "))
        self.assertRegex(lines[0], r"\| tick [+-]\d+\.\d e\d+ \| score -?\d")
        self.assertIn(">NS", state)  # the decisions
        jev.mock_decide({"model": "jev-latest", "state": state, "questions": questions})  # a valid API request
        q = questions[next(iter(questions))]["instructions"]
        self.assertIn("Read the HISTORY", q)

        # only the last N ticks, and no history at all
        short = officers.JevOfficer(limit=3)
        short.history = o.history
        self.assertEqual(len(short.history_lines(city)), 3)
        calls.clear()
        with mock.patch.object(officers, "decide", fake):
            run.play(officers.JevOfficer(history=False), 2, "three", ticks=8, quiet=True)
        self.assertNotIn("HISTORY", calls[-1][0])
        self.assertIn("NOW (tick", calls[-1][0])

    def test_state_as_map_and_array_with_history(self):
        seen = []

        def fake(state, questions):
            seen.append((state, questions))
            return response({q: choice_answer("east_west") for q in questions})

        for fmt in ("map", "array"):
            seen.clear()
            with mock.patch.object(officers, "decide", fake):
                run.play(officers.JevOfficer(state_format=fmt, lessons=True), 3, "three", ticks=15, quiet=True)
            state, questions = seen[-1]
            self.assertEqual(json.loads(json.dumps(state)), state)
            self.assertEqual(len(state["history"]), 14 if fmt == "map" else len(state["history"]))
            self.assertIn("lessons", state)
            if fmt == "array":
                self.assertEqual(len(state["fields"]), len(state["now"]))
                self.assertEqual(len(state["history"][0]), len(state["history_fields"]))
            jev.mock_decide({"model": "jev-latest", "state": state, "questions": questions})

    def test_the_coach_reviews_only_decisions_whose_future_is_past(self):
        o = officers.JevOfficer(lessons=True)
        with mock.patch.object(officers, "decide",
                               lambda state, questions: response({q: choice_answer("north_south") for q in questions})):
            run.play(o, 4, "three", ticks=coach.HORIZON + 5, quiet=True)
        self.assertGreater(o.lessons.reviewed, 0)
        self.assertLessEqual(len(o.moments), coach.HORIZON)  # the last HORIZON ticks wait for their future
        self.assertTrue(all(m[0].t + coach.HORIZON > coach.HORIZON + 5 for m in o.moments))

    def test_safety_rules_decide_before_jev(self):
        asked = []

        def fake(state, questions):
            asked.append(set(questions))
            return response({q: choice_answer("walk", 0.6, ["north_south", "east_west"]) for q in questions})

        c = C.City(2, "three")  # seed 2: no ambulance at the start
        c.arrive()
        j = c.junctions[FZ]
        j.light, j.yellow, j.green_for = "WALK", False, 1  # people already crossed
        busier = memory.action_of(c.state(vision=C.VISION), FZ, "busier")
        with mock.patch.object(officers, "decide", fake):
            out = officers.JevOfficer().act(c, [FZ, "dunhua_zhongxiao"])
            self.assertEqual(out["actions"][FZ], busier)
            self.assertEqual(out["junctions"][FZ]["rule"], "rule: walk lasts one tick")
            self.assertEqual(asked[-1], {"dunhua_zhongxiao"})  # the rule's junction is not sent to Jev
            no_rules = officers.JevOfficer(safety=False).act(c, [FZ])
            self.assertEqual(no_rules["actions"][FZ], "walk")
        rule = officers.JevOfficer.safety_rule
        c2 = C.City(1, "single")
        c2.arrive()
        state = c2.state()
        state["junctions"][FZ]["approaches"]["east"]["ambulance"] = True
        self.assertEqual(rule(state, FZ), ("east_west", "rule: ambulance first"))
        state["junctions"][FZ]["approaches"]["east"]["ambulance"] = False
        self.assertIsNone(rule(state, FZ))

    def test_unknown_policy_and_format(self):
        with self.assertRaises(SystemExit):
            officers.make_officer("robot")
        with self.assertRaises(ValueError):
            officers.JevOfficer(state_format="xml")


# ---------------------------------------------------------------------------
# The game loop and the command line
# ---------------------------------------------------------------------------

class Loop(unittest.TestCase):
    def test_a_simpler_game_without_pedestrians_and_ambulances(self):
        seen = {"ambulances": 0, "people": 0}

        class Spy(officers.GreedyOfficer):
            def act(self, city, ask):
                seen["ambulances"] += len(city.ambulances())
                seen["people"] += sum(len(j.pedestrians) for j in city.junctions.values())
                return super().act(city, ask)

        city, trace = run.play(Spy(), 7, ticks=200, quiet=True, ambulances=False, pedestrians=False)
        self.assertEqual(seen, {"ambulances": 0, "people": 0})
        self.assertNotIn("walk", {a for t in trace for a in t["actions"].values()})
        same, _ = run.play(officers.GreedyOfficer(), 7, ticks=200, quiet=True, ambulances=False, pedestrians=False)
        self.assertEqual(city.score, same.score)  # still the same run for the same seed
        run.play(Spy(), 7, ticks=200, quiet=True)
        self.assertGreater(seen["people"], 0)  # the full game still has people

    def test_locked_junctions_are_not_asked(self):
        asked = []

        class Spy(officers.GreedyOfficer):
            name = "spy"

            def act(self, city, ask):
                asked.append((list(ask), sorted(city.forced_actions())))
                return super().act(city, ask)

        city, trace = run.play(Spy(), 4, "three", ticks=60, quiet=True)
        self.assertTrue(any(forced for _, forced in asked))
        for ask, forced in asked:
            self.assertFalse(set(ask) & set(forced))
        self.assertEqual(len(trace), 60)
        self.assertTrue(all(set(t["moves"].values()) <= set(memory.MOVES) for t in trace))
        self.assertEqual(run.blocks(trace, 25)[0][:2], (1, 25))
        self.assertAlmostEqual(sum(b[2] for b in run.blocks(trace)), city.score, places=4)

    def test_cli(self):
        runs_dir = tempfile.mkdtemp(dir=_RUNS)
        r = run_script("level5-junction/run.py", "--policy", "greedy", "--ticks", "40", JUNCTION_RUNS_DIR=runs_dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Points and energy per 50 ticks", r.stdout)
        self.assertIn("Simple rules on the same traffic", r.stdout)
        detail = json.loads(Path(runs_dir, "run-001.json").read_text())
        self.assertEqual(len(detail["trace"]), 40)
        self.assertEqual(set(detail["layout"]["junctions"]), set(C.City(1).junctions))
        self.assertIn("energy", detail)
        self.assertTrue(Path(runs_dir, "runs.js").read_text().startswith("window.JUNCTION_RUNS = ["))

        exam = run_script("level5-junction/run.py", "--policy", "greedy", "--exam", JUNCTION_RUNS_DIR=runs_dir)
        self.assertIn(f"EXAM SCORE: {BASELINES['greedy']}", exam.stdout)
        fixed = run_script("level5-junction/run.py", "--policy", "fixed", "--exam", JUNCTION_RUNS_DIR=runs_dir)
        self.assertIn(f"EXAM SCORE: {BASELINES['fixed']}", fixed.stdout)

        for args in (["--state-format", "text"], ["--state-format", "map", "--lessons"], ["--state-format", "array"],
                     ["--policy", "jev-no-history"], ["--history", "5", "--lessons"]):
            mocked = run_script("level5-junction/run.py", "--map", "corridor", "--ticks", "25", *args,
                                JEV_MOCK=1, JUNCTION_RUNS_DIR=runs_dir)
            self.assertEqual(mocked.returncode, 0, mocked.stderr)
            self.assertRegex(mocked.stdout, r"Jev calls: \d+, input tokens: \d+")

        reset = run_script("level5-junction/run.py", "--reset", JUNCTION_RUNS_DIR=runs_dir)
        self.assertIn("deleted", reset.stdout)
        self.assertEqual(os.listdir(runs_dir), [])

    def test_same_seed_same_run_thanks_to_the_answer_cache(self):
        runs_dir = tempfile.mkdtemp(dir=_RUNS)
        exam = ("level5-junction/run.py", "--exam", "--ticks", "30")
        first = run_script(*exam, JEV_MOCK=1, JUNCTION_RUNS_DIR=runs_dir)
        cache = Path(runs_dir, "answers.jsonl")
        saved = cache.read_text().count("\n")
        self.assertGreater(saved, 15)
        second = run_script(*exam, JEV_MOCK=1, JUNCTION_RUNS_DIR=runs_dir)
        score = lambda r: re.search(r"EXAM SCORE: (\S+)", r.stdout).group(1)  # noqa: E731
        self.assertEqual(score(first), score(second))
        self.assertEqual(cache.read_text().count("\n"), saved)  # every answer came from the cache
        run_script(*exam, "--no-cache", JEV_MOCK=1, JUNCTION_RUNS_DIR=runs_dir)
        self.assertEqual(cache.read_text().count("\n"), saved)

    def test_jitter_without_cache_is_removed_by_the_cache(self):
        """A fake Jev whose probabilities move a little on every call, like the real one."""
        rng = random.Random(1)

        def jittery(state, questions):
            answers = {}
            for q in questions:
                p = {a: rng.random() for a in C.ACTIONS}
                best = max(p, key=p.get)
                answers[q] = choice_answer(best, 0.5, [a for a in C.ACTIONS if a != best])
            return response(answers)

        cache = Path(tempfile.mkdtemp(dir=_RUNS), "answers.jsonl")

        def cached(state, questions):
            return jev.decide(state, questions, cache=str(cache))

        def score():
            return run.play(officers.JevOfficer(history=False), 7, "corridor", ticks=40, quiet=True)[0].score

        with mock.patch.object(jev, "mock_decide", lambda body: jittery(body["state"], body["questions"])), \
                mock.patch.dict(os.environ, {"JEV_MOCK": "1"}), mock.patch.object(officers, "decide", cached):
            a, b = score(), score()
        self.assertEqual(a, b)
        with mock.patch.object(officers, "decide", jittery):
            c, d = score(), score()
        self.assertNotEqual(c, d)  # without the cache, the same seed gives another run

    def test_solutions_run(self):
        for name in ("solution_a.py", "solution_b.py"):
            r = run_script(f"level5-junction/{name}", JEV_MOCK=1)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"Simple rules on the same traffic: score {BASELINES['greedy']}", r.stdout)
        a = load("level5-junction/solution_a.py", "city_solution_a").officer()
        b = load("level5-junction/solution_b.py", "city_solution_b").officer()
        self.assertTrue(a.lessons is not None and a.limit is None)
        self.assertTrue(b.lessons is not None and b.limit == 20)

    def test_watch_mode_draws_the_city(self):
        runs_dir = tempfile.mkdtemp(dir=_RUNS)
        r = run_script("level5-junction/run.py", "--policy", "fixed", "--map", "single", "--ticks", "15",
                       "--watch", "0.001", JUNCTION_RUNS_DIR=runs_dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count("Pedestrians waiting"), 15)


class Baselines(unittest.TestCase):
    def test_exam_baselines(self):
        for policy, expected in BASELINES.items():
            city, _ = run.play(officers.make_officer(policy), run.EXAM_SEED, quiet=True)
            self.assertEqual(city.score, expected, policy)
        # the simple rules are a real opponent: clearly better than a timer
        self.assertGreater(BASELINES["greedy"], BASELINES["fixed"] + 300)


# ---------------------------------------------------------------------------
# Learning during the stream: a scripted Jev that only follows the coach's LESSONS
# ---------------------------------------------------------------------------

LESSON_LINE = re.compile(r"^  ([A-Z]{2}): (.+)$")
LESSON_ITEM = re.compile(r"(north_south|east_west|walk) ([+-]\d+\.\d)")


def lesson_follower(rng):
    """A fake Jev that ONLY reads the LESSONS in the state and picks the best one per junction.
    No lessons -> random. It knows nothing about traffic, so any skill comes from the coach."""
    used = {"questions": 0, "with_lessons": 0}

    def decide(state, questions):
        found = {}
        if "LESSONS from the coach" in state:
            part = state.split("LESSONS from the coach", 1)[1].split("NOW (tick", 1)[0]
            for line in part.splitlines():
                m = LESSON_LINE.match(line)
                if m:
                    found[m.group(1)] = {a: float(v) for a, v in LESSON_ITEM.findall(m.group(2))}
        answers = {}
        for qid, q in questions.items():
            used["questions"] += 1
            short = re.search(r"junction ([A-Z]{2}) ", q["instructions"]).group(1)
            if found.get(short):
                used["with_lessons"] += 1
                action = max(found[short], key=found[short].get)
            else:
                action = rng.choice(list(q["criteria"]))
            answers[qid] = choice_answer(action, 0.8, [a for a in q["criteria"] if a != action])
        return response(answers)

    return decide, used


class Learning(unittest.TestCase):
    def test_the_coach_makes_a_random_officer_better_during_the_stream(self):
        for seed in (2026, 11):
            decide, used = lesson_follower(random.Random(seed))
            with mock.patch.object(officers, "decide", decide):
                random_play = run.play(officers.JevOfficer(history=False, safety=False), seed, quiet=True)[0]
                taught, trace = run.play(officers.JevOfficer(history=False, lessons=True, safety=False), seed,
                                         quiet=True)
            # without lessons the officer plays randomly and badly; the lessons it collects
            # during the stream make it much better (note: comparing first and second half is NOT
            # a fair test of learning: the traffic is different in each half, waves and rain)
            self.assertGreater(taught.score, random_play.score + 300, f"seed {seed}")
            self.assertGreater(used["with_lessons"] / used["questions"], 0.3)
            self.assertEqual(len(trace), C.TICKS)


if __name__ == "__main__":
    unittest.main()
