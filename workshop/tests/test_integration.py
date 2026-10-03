"""End-to-end: Python client -> Node proxy -> (mock | fake Jev), the workshop through the proxy,
the Level 5 viewer in a headless browser, and the slide layout check."""
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from helpers import REPO, WORKSHOP, FakeJev, clean_env, noul_answer, patched_env, response, run_script

import jev

NODE = shutil.which("node")
PROXY = REPO / "proxy" / "src" / "server.js"
KEY = "jvp_integration_test_key"


@contextlib.contextmanager
def proxy(**env):
    """Start the real proxy on a free port. Yields its base URL."""
    tmp = Path(tempfile.mkdtemp(prefix="jev-proxy-it-"))
    (tmp / "keys.json").write_text(json.dumps([{"name": "it", "key": KEY, "max_cost_usd": 1.0, "rpm": 100000}]))
    proc_env = clean_env(PORT=0, HOST="127.0.0.1", KEYS_FILE=tmp / "keys.json", USAGE_FILE=tmp / "usage.json",
                         LOG_FILE=tmp / "proxy.log", **env)
    proc = subprocess.Popen([NODE, str(PROXY)], cwd=str(tmp), env=proc_env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        port = None
        for _ in range(50):
            line = proc.stdout.readline()
            m = re.search(r"listening on http://[^:]+:(\d+)", line)
            if m:
                port = int(m.group(1))
                break
        if port is None:
            raise RuntimeError("proxy did not start")
        # keep reading the proxy's log so its output pipe never fills up
        threading.Thread(target=proc.stdout.read, daemon=True).start()
        yield f"http://127.0.0.1:{port}", tmp
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
        shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(NODE, "node is not installed")
class ClientThroughProxy(unittest.TestCase):
    def test_mock_upstream(self):
        with proxy(MOCK_UPSTREAM=1) as (url, _), patched_env(JEV_BASE_URL=url, JEV_API_KEY=KEY, JEV_MOCK="0"):
            r = jev.decide("I love this bubble tea!", {"happy": jev.noul("Is the customer happy?")})
            names = [m["name"] for m in jev.models()["models"]]
        self.assertEqual(names, ["jev-latest", "jev-preview"])
        self.assertEqual(r["model"], "jev-mock")
        self.assertGreater(r["answers"]["happy"]["noul"], 0.5)
        self.assertEqual(set(r["usage"]), {"input_tokens", "output_tokens"})

    def test_live_mode_swaps_the_key_and_passes_answers_through(self):
        answer = {**response({"q": noul_answer(0.8)}), "usage": {"input_tokens": 20, "output_tokens": 21}}

        def responder(path, body, headers):
            return 200, answer, {}

        with FakeJev(responder) as upstream, proxy(UPSTREAM_BASE_URL=upstream.url, JEV_API_KEY="apikey_owner_secret") as (url, tmp), \
                patched_env(JEV_BASE_URL=url, JEV_API_KEY=KEY, JEV_MOCK="0"):
            r = jev.decide("hello", {"q": jev.noul("Ok?")})
            with self.assertRaises(jev.JevError) as bad:
                with patched_env(JEV_API_KEY="jvp_wrong"):
                    jev.decide("hello", {"q": jev.noul("Ok?")})
            log = (tmp / "proxy.log").read_text()

        self.assertEqual(r, answer)  # unchanged
        sent = upstream.requests[0]
        self.assertEqual(sent["path"], "/v1/systemone")
        self.assertEqual(sent["headers"]["authorization"], "Bearer apikey_owner_secret")
        self.assertEqual(sent["body"], {"model": "jev-latest", "state": "hello", "questions": {"q": jev.noul("Ok?")}})
        self.assertEqual((bad.exception.status, bad.exception.code), (401, "authentication_error"))
        self.assertEqual(len(upstream.requests), 1)  # the wrong key never reached Jev
        self.assertNotIn("hello", log)

    def test_workshop_runs_through_the_proxy(self):
        runs = tempfile.mkdtemp(prefix="jev-it-runs-")
        try:
            with proxy(MOCK_UPSTREAM=1) as (url, _):
                env = dict(JEV_BASE_URL=url, JEV_API_KEY=KEY, JEV_MOCK=0, JUNCTION_RUNS_DIR=runs)
                for script, args in [("jev.py", []), ("level1-yes-or-no/reviews.py", []),
                                     ("level2-pick-and-rate/inbox.py", []), ("level3-guardrail/agent_gate.py", []),
                                     ("level4-tea-shop/shop.py", ["--seed", "2"]),
                                     ("level5-junction/run.py", ["--ticks", "20"])]:
                    with self.subTest(script=script):
                        r = run_script(script, *args, **env)
                        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                        self.assertNotIn("MOCK MODE", r.stderr)  # real HTTP calls, not the Python mock
            self.assertEqual(len(json.loads(Path(runs, "run-001.json").read_text())["trace"]), 20)
        finally:
            shutil.rmtree(runs, ignore_errors=True)


@unittest.skipUnless(NODE, "node is not installed")
class Viewer(unittest.TestCase):
    def check(self, folder, script="viewer_check.mjs"):
        r = subprocess.run([NODE, str(WORKSHOP / "tests" / script), str(folder)],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 77:
            self.skipTest("playwright not installed")
        report = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(r.returncode, 0, report)
        return report

    def test_3d_viewer_replays_runs(self):
        folder = Path(tempfile.mkdtemp(prefix="jev-viewer3d-"))
        try:
            shutil.copy(WORKSHOP / "level5-junction" / "viewer3d.html", folder)
            shutil.copytree(WORKSHOP / "level5-junction" / "vendor", folder / "vendor")
            empty = self.check(folder, "viewer3d_check.mjs")
            self.assertTrue(empty["empty"])  # no runs yet: a friendly message, no errors

            env = dict(JUNCTION_RUNS_DIR=folder / "runs")
            self.assertEqual(run_script("level5-junction/run.py", "--policy", "greedy", "--ticks", "30", **env).returncode, 0)
            self.assertEqual(run_script("level5-junction/run.py", "--ticks", "30", JEV_MOCK=1, **env).returncode, 0)
            report = self.check(folder, "viewer3d_check.mjs")
            self.assertEqual(report["webgl"], 1)
            self.assertEqual((report["runs"], report["ticks"], report["junctions"]), (2, 30, 3))
            self.assertEqual(report["labelsOnScreen"], 3)
            self.assertEqual(report["debug"]["officers"], 3)  # one animated officer per junction
            self.assertGreater(report["tickAfterPlay"], 0)
            self.assertTrue(any("locked" in t for t in report["texts"]), report["texts"])
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_viewer_replays_runs(self):
        folder = Path(tempfile.mkdtemp(prefix="jev-viewer-"))
        try:
            shutil.copy(WORKSHOP / "level5-junction" / "viewer.html", folder)
            env = dict(JUNCTION_RUNS_DIR=folder / "runs")
            for _ in range(2):
                self.assertEqual(run_script("level5-junction/run.py", "--policy", "greedy", "--ticks", "30", **env).returncode, 0)
            self.assertEqual(run_script("level5-junction/run.py", "--map", "grid", "--ticks", "30", JEV_MOCK=1, **env).returncode, 0)

            report = self.check(folder)
            self.assertFalse(report["empty"])
            self.assertEqual(report["runs"], 3)
            self.assertEqual(report["ticks"], 30)
            self.assertGreater(report["tickAfterPlay"], 0)
            self.assertGreater(report["canvasColors"], 8)
            self.assertIn("locked", report["tags"])
            self.assertIn("rule-based officer", report["tags"])
            self.assertEqual(report["junctions"], 4)  # the last run shown is the grid
            self.assertEqual(report["bars"], 4 * 3)
            self.assertEqual(report["curveBars"], 3)
            self.assertGreater(report["parts"], 0)
            self.assertEqual(report["errors"], [])
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_one_junction_viewer_animates_without_jumps(self):
        folder = Path(tempfile.mkdtemp(prefix="jev-one-"))
        try:
            shutil.copy(WORKSHOP / "level5-junction" / "one_junction.html", folder)
            self.assertTrue(self.check(folder, "one_junction_check.mjs")["empty"])  # no runs: a friendly message
            env = dict(JUNCTION_RUNS_DIR=folder / "runs")
            for officer in ("random", "rules"):
                r = run_script("level5-junction/one_junction.py", "--officer", officer, "--ticks", "12", "--start", "07:00", **env)
                self.assertEqual(r.returncode, 0, r.stderr)
            report = self.check(folder, "one_junction_check.mjs")
            self.assertEqual((report["runs"], report["errors"]), (2, []))
            # the end of one tick looks like the start of the next: cars glide, they do not jump
            self.assertLess(report["maxBoundary"], report["meanWithin"] / 2, report)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_city_runs_without_collisions_and_exposes_its_state(self):
        r = subprocess.run([NODE, str(WORKSHOP / "tests" / "city_check.mjs"), str(WORKSHOP / "level5-junction" / "city.html")],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 77:
            self.skipTest("playwright not installed")
        report = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(r.returncode, 0, report)
        self.assertEqual((report["errors"], report["totals"]["collisions"]), ([], 0))
        self.assertEqual(report["manual"], ["C", "D", "W", "A", "B"])  # setPhase drives the lights
        self.assertEqual(report["ticks"], 10)  # onSecond: once per simulated second
        # every vehicle that goes is across in exactly 1 tick (3 s = 60 steps), and goes when a tick starts
        self.assertEqual(report["crossing"]["tick"], 3)
        self.assertEqual(report["crossing"]["took"], [report["crossing"]["steps"]])
        self.assertEqual(report["crossing"]["startedAt"], [0])
        # people too: across a zebra in exactly 1 tick, starting when a tick starts; zebras empty at every tick start
        self.assertEqual(report["crossing"]["walkTook"], [report["crossing"]["steps"]])
        self.assertEqual(report["crossing"]["walkStartedAt"], [0])
        self.assertEqual(report["crossing"]["onZebraAtTickStart"], 0)
        # the screen plays each tick from its recording (a snapshot per step), with no jump between ticks
        self.assertEqual(report["playback"]["frames"], report["crossing"]["steps"] + 1)
        self.assertGreater(report["playback"]["compared"], 50)
        self.assertEqual(report["playback"]["maxGap"], 0)
        self.assertGreater(report["playback"]["midVehicles"], 50)
        self.assertEqual(report["schedule"]["seen"], ["A", "C"])  # a schedule runs only its phases
        self.assertIn("phase must be one of", report["schedule"]["bad"])
        self.assertEqual((report["schedule"]["before"], report["schedule"]["after"]), ("A", "WB"))  # day plan by the clock
        self.assertEqual(report["history"]["buckets"], 4)
        self.assertEqual(set(report["history"]["j0"]["vehicles"]["north"]), {"left", "straight", "right", "avg_wait_s", "max_queue"})
        self.assertGreater(report["totals"]["trips_vehicles"], 300)
        self.assertGreater(report["totals"]["trips_people"], 300)
        self.assertEqual(report["junction0"]["lanes"], ["left_turn", "straight_right", "bike"])
        self.assertEqual(set(report["types"]), {"car", "taxi", "bus", "scooter", "bike"})
        # the lanes and turns the lights on screen let go are tinted green (amber while yellow), the zebras while people walk
        def bands(j, heads, moves, color="G"):
            return {f"{j}:{h}:{m}": color for h in heads for m in moves}
        straight_right = ["S", "R", "BS", "BR"]  # B = the bike lane: bikes go with the straight + right light
        walk = {f"3:walk:{arm}": "G" for arm in ("north", "east", "south", "west")}
        greens = report["greens"]
        self.assertEqual(greens["go"]["lit"], {**bands(0, "NS", straight_right), **bands(1, "NS", ["L"]),
                                               **bands(2, "EW", straight_right), **walk})
        self.assertEqual(greens["ending"]["lit"], {**bands(1, "EW", ["L"], "Y"), **bands(2, "EW", straight_right),
                                                   **{k: "Y" for k in walk}})  # all red at 0: nothing
        self.assertEqual(greens["notYet"]["lit"], greens["ending"]["lit"])
        for moment in greens.values():  # the 3D view (when the browser has WebGL) tints exactly the same bands
            if moment["view3d"] is not None:
                self.assertEqual(moment["view3d"], moment["lit"])

    def test_city_server_calls_jev_and_the_page_shows_it_live(self):
        port = 8790 + os.getpid() % 100
        server = subprocess.Popen([sys.executable, str(WORKSHOP / "level5-junction" / "city_server.py"), "--tick", "0.25",
                                   "--port", str(port), "--no-open"],
                                  cwd=str(WORKSHOP), env=clean_env(JEV_MOCK=1), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            first = server.stdout.readline()
            self.assertIn(f"http://localhost:{port}/", first)
            r = subprocess.run([NODE, str(WORKSHOP / "tests" / "city_live_check.mjs"), f"http://localhost:{port}/"],
                               capture_output=True, text=True, timeout=180)
            if r.returncode == 77:
                self.skipTest("playwright not installed")
            report = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertEqual((r.returncode, report["errors"]), (0, []), report)
            self.assertTrue(report["view3d"])                       # the 3D city is the default view
            self.assertGreaterEqual(report["calls"], 2)             # Jev (mock) was asked
            self.assertEqual(report["modes"], ["direct"] * 4)       # the lights are exactly what decide() returned
            self.assertGreater(report["costPath"], 0)
            self.assertGreater(report["latBars"], 0)
            self.assertGreater(report["picks"], 0)
            # the decisions list: one row per tick (= one decide() call), the newest on top
            ticks = [d["tick"] for d in report["decisions"]]
            self.assertEqual(ticks, sorted(ticks, reverse=True))
            self.assertIn(ticks[0], (report["tickN"] - 1, report["tickN"]))  # tickN can be one ahead: decide() still thinking
            self.assertEqual(ticks, list(range(ticks[0], ticks[0] - len(ticks), -1)))
            self.assertTrue(all(d["phases"] == 4 and not d["error"] for d in report["decisions"]), report["decisions"])
            # the live score: every tick has its points, and they add up to the score
            self.assertTrue(all(isinstance(d["points"], (int, float)) for d in report["decisions"]), report["decisions"])
            self.assertAlmostEqual(float(report["score"]), sum(d["points"] for d in report["decisions"]), delta=0.11 * len(ticks))
            st = report["decideState"]                             # what decide() gets as current: small
            self.assertEqual(set(st), {"tick", "clock", "crossings"})
            self.assertEqual(st["tick"], 7)
            self.assertEqual([c["id"] for c in st["crossings"]], [0, 1, 2, 3])
            for c in st["crossings"]:
                self.assertEqual(set(c), {"id", "name", "lights", "ticks", "cars", "people"})
                self.assertIsInstance(c["ticks"], int)
                self.assertIn(c["lights"], ["A", "B", "C", "D", "W"])
                self.assertEqual(set(c["cars"]), {"north", "east", "south", "west"})
                self.assertEqual(set(c["people"]), {"north", "east", "south", "west"})
                for lanes in c["cars"].values():
                    self.assertEqual(set(lanes), {"left", "straight_right", "bikes"})
                    self.assertTrue(all(isinstance(n, int) and n >= 0 for n in lanes.values()))
        finally:
            server.terminate()
            server.wait(timeout=10)

    def test_viewer_without_runs_explains_what_to_do(self):
        folder = Path(tempfile.mkdtemp(prefix="jev-viewer-empty-"))
        try:
            shutil.copy(WORKSHOP / "level5-junction" / "viewer.html", folder)
            report = self.check(folder)
            self.assertTrue(report["empty"])
        finally:
            shutil.rmtree(folder, ignore_errors=True)


@unittest.skipUnless(NODE, "node is not installed")
class Slides(unittest.TestCase):
    def test_every_slide_fits(self):
        r = subprocess.run([NODE, str(REPO / "slides" / "check.mjs")], capture_output=True, text=True, timeout=180)
        if r.returncode == 77:
            self.skipTest("playwright not installed")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("47 slides, 5 fonts loaded, 0 problem(s)", r.stdout)

    def test_pdf_is_committed(self):
        pdf = REPO / "slides" / "jev-workshop-slides.pdf"
        self.assertTrue(pdf.exists())
        self.assertEqual(pdf.read_bytes()[:5], b"%PDF-")
        self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes())), 47)


if __name__ == "__main__":
    unittest.main()
