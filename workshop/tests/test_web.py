"""The level simulators (Levels 1-4): their servers answer the page from the level's own code, keep the key
local (only their own page may call them), and the pages work in a browser (Playwright, when installed)."""
import http.client
import json
import os
import shutil
import subprocess
import sys
import unittest

from helpers import WORKSHOP, add_path, clean_env, load

NODE = shutil.which("node")
LEVELS = {1: "level1-yes-or-no", 2: "level2-pick-and-rate", 3: "level3-guardrail", 4: "level4-tea-shop", 5: "sandbox"}


class Server:
    """A level's server.py in mock mode, on its own port."""

    def __init__(self, level):
        self.port = 8600 + level * 10 + os.getpid() % 10
        self.proc = subprocess.Popen([sys.executable, str(WORKSHOP / LEVELS[level] / "server.py"), "--port", str(self.port), "--no-open"],  # 5 = the sandbox
                                     cwd=str(WORKSHOP), env=clean_env(JEV_MOCK=1), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.first = self.proc.stdout.readline()
        self.url = f"http://localhost:{self.port}/"

    def call(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        h = {"Host": f"localhost:{self.port}", **({"Content-Type": "application/json"} if body is not None else {}), **(headers or {})}
        c.request(method, path, json.dumps(body) if body is not None else None, h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, (json.loads(data) if r.getheader("Content-Type", "").startswith("application/json") else data)

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)


class LevelServers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servers = {n: Server(n) for n in LEVELS}

    @classmethod
    def tearDownClass(cls):
        [s.close() for s in cls.servers.values()]

    def test_every_server_starts_and_serves_its_page(self):
        for n, s in self.servers.items():
            with self.subTest(level=n):
                self.assertIn(s.url, s.first)
                status, page = s.call("GET", "/")
                self.assertEqual(status, 200)
                self.assertIn(b"/ui/ui.js", page)
                self.assertEqual(s.call("GET", "/ui/ui.js")[0], 200)
                self.assertEqual(s.call("GET", "/ui/ui.css")[0], 200)

    def test_the_level_comes_from_the_levels_own_code(self):
        reviews = load("level1-yes-or-no/reviews.py", "web_reviews")
        inbox = load("level2-pick-and-rate/inbox.py", "web_inbox")
        gate = load("level3-guardrail/agent_gate.py", "web_gate")
        shop = load("level4-tea-shop/shop.py", "web_shop")
        l1, l2, l3, l4, sandbox = (self.servers[n].call("GET", "/api/level")[1] for n in LEVELS)
        names = [t["name"] for t in sandbox["templates"]]
        self.assertIn("Level 2: your inbox questions", names)                  # the sandbox shows YOUR questions too
        self.assertEqual(next(t for t in sandbox["templates"] if t["name"] == "Level 2: your inbox questions")["questions"], inbox.QUESTIONS)
        self.assertIn("jev-latest", sandbox["models"])
        self.assertEqual((l1["reviews"]["items"], l1["reviews"]["question"], l1["reviews"]["threshold"]), (reviews.REVIEWS, reviews.QUESTION, reviews.THRESHOLD))
        self.assertEqual(len(l1["spam"]["items"]), len(l1["spam"]["expected"]))
        self.assertEqual((l2["items"], l2["questions"], l2["min_confidence"]), (inbox.INBOX, inbox.QUESTIONS, inbox.MIN_CONFIDENCE))
        self.assertEqual((l3["items"], l3["questions"]), (gate.TOOL_CALLS, gate.QUESTIONS))
        self.assertEqual((l4["actions"], l4["questions"], l4["rounds"]), (shop.ACTIONS, shop.QUESTIONS, shop.ROUNDS))
        self.assertEqual(l1["jev"]["mock"], True)

    def test_reviews_py_does_not_call_jev_when_imported(self):
        env = clean_env()   # no key, no mock: a Jev call would fail
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path[:0] = ['level1-yes-or-no', '.']; import reviews; print(len(reviews.REVIEWS))"],
                           cwd=str(WORKSHOP), env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "6"), r.stderr)

    def test_jev_calls_go_through_the_server(self):
        s = self.servers[2]
        level = s.call("GET", "/api/level")[1]
        status, r = s.call("POST", "/api/jev", {"state": level["items"][0], "questions": level["questions"]})
        self.assertEqual(status, 200, r)
        self.assertEqual(set(r["answers"]), {"box", "urgency"})
        self.assertIn(r["answers"]["box"]["choice"], level["questions"]["box"]["criteria"])
        self.assertGreater(r["usage"]["input_tokens"], 0)
        self.assertIn("cost_usd", r)
        self.assertEqual(s.call("POST", "/api/jev", {"questions": {}})[0], 400)

    def test_only_its_own_page_may_call_it(self):
        s = self.servers[1]
        body = {"state": "x", "questions": {"q": {"type": "noul", "instructions": "x?"}}}
        self.assertEqual(s.call("POST", "/api/jev", body, {"Origin": "https://evil.example"})[0], 403)   # another website
        self.assertEqual(s.call("POST", "/api/jev", body, {"Host": "evil.example"})[0], 403)             # DNS rebinding
        self.assertEqual(s.call("GET", "/api/level", headers={"Host": f"attacker.test:{s.port}"})[0], 403)
        self.assertEqual(s.call("POST", "/api/jev", body, {"Content-Type": "text/plain"})[0], 415)       # a "simple" cross-site form post
        self.assertEqual(s.call("POST", "/api/jev", body, {"Origin": f"http://localhost:{s.port}"})[0], 200)
        self.assertEqual(s.call("GET", "/ui/../web.py")[0], 404)
        self.assertEqual(s.call("GET", "/ui/..%2fjev.py")[0], 404)

    def test_level2_portfolio_uses_your_describe(self):
        s = self.servers[2]
        add_path("level2-pick-and-rate")                                   # portfolio.py imports market.py next to it
        portfolio = load("level2-pick-and-rate/portfolio.py", "web_portfolio")
        p = s.call("GET", "/api/level")[1]["portfolio"]
        self.assertEqual((p["stocks"], p["questions"], p["min_confidence"]), (portfolio.STOCKS, portfolio.QUESTIONS, portfolio.MIN_CONFIDENCE))
        status, r = s.call("POST", "/api/portfolio_request", {"stock": {"name": " Bubble Cloud ", "notes": "Sales up 80% a year."}})
        self.assertEqual(status, 200, r)
        self.assertEqual(r, {"state": "Bubble Cloud", "questions": portfolio.QUESTIONS})   # the starter's describe(): only the name
        self.assertEqual(s.call("POST", "/api/portfolio_request", {"stock": {"name": "  "}})[0], 400)
        self.assertEqual(s.call("POST", "/api/portfolio_request", {"stock": "TSMC"})[0], 400)

    def test_level3_asks_your_gate(self):
        s = self.servers[3]
        a = {"risk": {"score": 0.2}, "kind": {"choice": "read_only"}, "on_goal": {"noul": 0.9}, "tricked": {"noul": 0.95}}
        self.assertEqual(s.call("POST", "/api/gate", {"answers": a})[1], {"decision": "BLOCK", "reason": "looks like prompt injection"})
        a["tricked"]["noul"] = 0.02
        self.assertEqual(s.call("POST", "/api/gate", {"answers": a})[1]["decision"], "ALLOW")
        status, r = s.call("POST", "/api/gate", {"answers": {"risk": {"score": 1}}})
        self.assertEqual(status, 400)
        self.assertIn("gate() could not use these answers", r["error"])

    def test_level3_console_uses_your_guard(self):
        s, path = self.servers[3], WORKSHOP / "level3-guardrail" / "console_guard.py"
        before = path.read_text(encoding="utf-8")
        c = s.call("GET", "/api/level")[1]["console"]
        self.assertEqual((c["error"], len(c["exam"])), (None, 10))
        self.assertEqual(s.call("POST", "/api/code", {})[1]["console_guard.py"], before)
        status, r = s.call("POST", "/api/console_request", {"command": " rm -rf /shop ", "goal": "tidy up"})
        self.assertEqual((status, r["state"], set(r["questions"])), (200, "rm -rf /shop", {"dangerous"}))   # YOUR describe()
        self.assertEqual(s.call("POST", "/api/console_guard", {"command": "rm -rf /shop", "answers": {"dangerous": {"noul": 0.9}}})[1],
                         {"decision": "BLOCK", "reason": "Jev thinks it is dangerous"})                          # YOUR guard()
        self.assertEqual(s.call("POST", "/api/console_guard", {"command": "ls", "answers": {}})[0], 400)          # guard() needs its answer
        self.assertEqual(s.call("POST", "/api/console_request", {"command": "   "})[0], 400)
        status, r = s.call("POST", "/api/save", {"file": "console_guard.py", "source": before.replace('"looks fine"', '"looks fine" :(')})
        self.assertEqual(status, 400)
        self.assertIn("not saved: line", r["error"])
        self.assertEqual(path.read_text(encoding="utf-8"), before)          # a broken file is never written
        self.assertEqual(s.call("POST", "/api/save", {"file": "console_guard.py", "source": before})[1]["saved"], "console_guard.py")
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        status, r = s.call("POST", "/api/save", {"file": "../web.py", "source": "x = 1"})   # only the level's own files
        self.assertEqual(status, 400)
        self.assertIn("can be saved here", r["error"])

    def test_level4_plays_a_day_like_shop_py(self):
        s = self.servers[4]
        status, day = s.call("POST", "/api/new", {"seed": 1})
        self.assertEqual(status, 200, day)
        self.assertEqual((day["view"]["round"], day["view"]["clock"]), (0, "11:00"))
        self.assertIn("Bubble tea shop at 11:00", day["decision"]["state"])
        self.assertEqual(s.call("POST", "/api/step", {"action": "dance"})[0], 400)
        r = day
        while not r["view"]["done"]:   # the simple rules, round by round, through the server
            action = s.call("POST", "/api/rules", {})[1]["action"]
            r = s.call("POST", "/api/step", {"action": action})[1]
        self.assertEqual(r["view"]["round"], 16)
        self.assertEqual(r["view"]["points"], 47)       # the same day as `shop.py --rules --seed 1`
        self.assertEqual(s.call("POST", "/api/step", {"action": "rest"})[0], 400)   # the day is over


@unittest.skipUnless(NODE, "node is not installed")
class LevelPagesInABrowser(unittest.TestCase):
    def check(self, level):
        s = Server(level)
        try:
            r = subprocess.run([NODE, str(WORKSHOP / "tests" / "levels_web_check.mjs"), str(level), s.url], capture_output=True, text=True, timeout=400)
        finally:
            s.close()
        if r.returncode == 77:
            self.skipTest("playwright not installed")
        report = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual((r.returncode, report["errors"]), (0, []), report)   # deliberate 4xx answers are not page errors
        self.assertIn("MOCK", report["meter"])
        self.assertEqual((report["leaksBefore"], report["leaksAfter"]), ([], []))   # no "null" / "undefined" / "NaN" on the page
        return report

    def test_level1_threshold_and_editor(self):
        r = self.check(1)
        self.assertEqual((r["oneDot"], r["leaksOneAnswered"]), (1, []))
        self.assertEqual(len(r["tags"]), 6)
        self.assertEqual(r["dots"], 6)
        self.assertEqual(r["tagsAtThreshold1"], ["NO"] * 6)          # moving the line relabels, no new call
        self.assertEqual(set(r["request"]), {"state", "questions"})
        self.assertIn("This page needs \"noul\"", r["wrongType"][0])
        self.assertEqual(r["applied"], ["0.97", "YES"])                # a hand-written answer updates the card
        self.assertIn("a number from 0 to 1", r["outOfRange"][0])
        self.assertRegex(r["spamScore"], r"^\d/6$")

    def test_level2_boxes_human_and_editor(self):
        r = self.check(2)
        self.assertEqual(r["columns"], ["order", "complaint", "question", "job", "spam", "🙋 HUMAN?"])
        self.assertEqual((r["humanAt0"], r["humanAt1"]), (0, 7))
        self.assertRegex(r["detail"], r"^Message \d+: job$")          # the clicked card was moved to job by hand
        self.assertGreaterEqual(r["applied"]["job"], 1)
        self.assertEqual(len(r["badAnswer"]), 2)
        self.assertIn("questions.urgency: missing", r["missingQuestion"][0])
        p = r["portfolio"]                                              # the portfolio tab (the challenge)
        self.assertEqual(p["todos"], ["TODO 2", "TODO 1"])
        self.assertEqual((p["count"], p["sorted"], p["leaks"]), ("6", 6, []))
        self.assertEqual(p["columns"][:4], ["rocket", "grower", "steady", "shrinking"])
        self.assertEqual(p["applied"], "Bubble Cloud")
        self.assertEqual(p["afterReload"], "6")                         # the company you added is kept in the browser

    def test_level3_lanes_and_red_team(self):
        r = self.check(3)
        self.assertEqual(sum(r["lanes"].values()), 5)
        self.assertIn("looks like prompt injection", r["redTeam"])
        self.assertEqual(r["allowed"], "ALLOW")
        c = r["console"]                                                     # the console tab (the challenge)
        self.assertGreater(c["highlighted"], 20)                             # the guard's code, highlighted
        self.assertRegex(c["first"], r"^agent \$ cat menu\.txt (RUN|ASK|BLOCK)")
        self.assertIn("BLOCK", c["blocked"])
        self.assertIn("nothing really ran", c["ran"])                        # RUN never runs anything
        self.assertIn("not saved: line", c["syntaxError"])
        self.assertEqual(c["errorLineMarked"], 1)                            # the editor marks the broken line
        self.assertRegex(c["exam"], r"^\d+/10$")                             # the attack wave is scored

    def test_sandbox_builds_any_request_and_shows_widgets(self):
        r = self.check(5)
        self.assertEqual(r["widgets"], [["noul", 5], ["choice", 0], ["score", 5]])   # a gauge, bars, a scale; "Ask 5x" spreads
        self.assertEqual(r["tree"], 2)                                                 # a JSON state as a tree
        self.assertIn("Question 1: write the question.", r["problems"])
        self.assertEqual(r["problemsAfter"], [])
        self.assertEqual(r["req"]["questions"]["pick"]["criteria"], {"taste": None, "price": None})
        self.assertEqual(r["loaded"], ["YES/NO", "SCORE"])                             # JSON back into the form
        self.assertEqual(r["history"], 2)

    def test_level4_a_day_with_every_manager(self):
        r = self.check(4)
        self.assertEqual(r["rulesDay"][0][:3], ["rules", "1", "47"])  # the same day as shop.py --rules
        self.assertEqual(r["rows"], 16)
        self.assertEqual(r["jevRow"][7].split()[0], "jev")
        self.assertEqual((r["appliedRow"][6], r["appliedRow"][7].split()[0]), ("rest", "apply"))
        self.assertIn('"dance" is not known here', r["unknownAction"][0])
        self.assertEqual(r["youRow"][6:8], ["cook_pearls", "you"])
        self.assertEqual(r["fsmNodes"], 4)


if __name__ == "__main__":
    unittest.main()
