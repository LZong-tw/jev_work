"""Levels 1-3: every script runs, and the logic is right when Jev gives known answers."""
import contextlib
import json
import io
import sys
import unittest
from unittest import mock

from helpers import (FakeJev, add_path, choice_answer, load, load_solutions, noul_answer, response, run_script,
                     score_answer)

import jev

SCRIPTS = [
    "level1-yes-or-no/reviews.py",
    "level1-yes-or-no/spam_filter.py",
    "level1-yes-or-no/solution_a.py",
    "level1-yes-or-no/solution_b.py",
    "level2-pick-and-rate/inbox.py",
    "level2-pick-and-rate/solution_a.py",
    "level2-pick-and-rate/solution_b.py",
    "level2-pick-and-rate/portfolio.py",
    "level3-guardrail/agent_gate.py",
    "level3-guardrail/solution_a.py",
    "level3-guardrail/solution_b.py",
    "level3-guardrail/console_guard.py",
]


class AllScriptsRunInMockMode(unittest.TestCase):
    def test_scripts_exit_cleanly(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                r = run_script(script, JEV_MOCK=1)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(r.stdout.strip())
                self.assertIn("MOCK MODE", r.stderr)

    def test_bonus_refuses_mock_mode(self):
        r = run_script("level3-guardrail/bonus_models.py", JEV_MOCK=1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("needs the real API", r.stderr)


class Level1(unittest.TestCase):
    SPAM_WORDS = ("won", "password", "earn")

    def spam_responder(self, path, body, headers):
        text = body["state"].lower()
        p = 0.96 if any(w in text for w in self.SPAM_WORDS) else 0.04
        return 200, response({"spam": noul_answer(p)}), {}

    def test_solution_a_one_question_with_criteria(self):
        with FakeJev(self.spam_responder) as fake:
            r = run_script("level1-yes-or-no/solution_a.py", JEV_BASE_URL=fake.url, JEV_API_KEY="k")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Score: 6/6", r.stdout)
        q = fake.requests[0]["body"]["questions"]["spam"]
        self.assertEqual(sorted(q["criteria"]), ["false", "true"])  # says what YES and NO mean
        self.assertIn("password", q["criteria"]["true"])

    def test_solution_b_three_small_questions(self):
        def responder(path, body, headers):
            text = body["state"].lower()
            return 200, response({
                "prize_or_money": noul_answer(0.95 if "won" in text or "earn" in text else 0.03),
                "asks_secret": noul_answer(0.9 if "password" in text else 0.02),
                "stranger_link": noul_answer(0.1),
            }), {}

        with FakeJev(responder) as fake:
            r = run_script("level1-yes-or-no/solution_b.py", JEV_BASE_URL=fake.url, JEV_API_KEY="k")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Score: 6/6", r.stdout)
        self.assertEqual(len(fake.requests), 6)  # one call per message, three questions in it
        self.assertEqual(len(fake.requests[0]["body"]["questions"]), 3)
        self.assertIn("asks_secret 0.90", r.stdout)  # it says WHY

    def test_starter_still_has_todo(self):
        with FakeJev(self.spam_responder) as fake:
            r = run_script("level1-yes-or-no/spam_filter.py", JEV_BASE_URL=fake.url, JEV_API_KEY="k")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(fake.requests[0]["body"]["questions"]["spam"]["instructions"], "TODO: write your question here")

    def test_reviews_threshold(self):
        def responder(path, body, headers):
            happy = any(w in body["state"] for w in ("perfect", "friendly"))
            return 200, response({"happy": noul_answer(0.9 if happy else 0.2)}), {}

        with FakeJev(responder) as fake:
            r = run_script("level1-yes-or-no/reviews.py", JEV_BASE_URL=fake.url, JEV_API_KEY="k")
        lines = r.stdout.strip().splitlines()
        self.assertEqual(len(lines), 6)
        self.assertEqual([line[:3] for line in lines], ["YES", "NO ", "NO ", "YES", "NO ", "NO "])


def inbox_answer(state, questions):
    s = state.lower()
    boxes = questions["box"]["criteria"]
    box = ("order" if "order 20" in s else "complaint" if "refund" in s else "job" if "hiring" in s
           else "spam" if "verify here" in s else "lost_item" if "umbrella" in s and "lost_item" in boxes
           else "other" if "umbrella" in s and "other" in boxes else "question")
    conf = 0.4 if "umbrella" in s and box == "question" else 0.95
    urgency = 3.0 if "now" in s else 2.0 if "tomorrow" in s else 0.5
    others = [k for k in questions["box"]["criteria"] if k != box]
    ans = choice_answer(box, conf, others)
    if "typhoon" in s:  # torn between two boxes
        ans["probabilities"]["order"] = 0.3
    return response({"box": ans, "urgency": score_answer(urgency)})


class Level2(unittest.TestCase):
    def setUp(self):
        add_path("level2-pick-and-rate")
        self.inbox = load("level2-pick-and-rate/inbox.py", "inbox_under_test")

    def test_questions_are_valid_for_the_api(self):
        jev.mock_decide({"model": "jev-latest", "state": "x", "questions": self.inbox.QUESTIONS})  # raises if invalid

    def test_low_confidence_goes_to_a_human(self):
        out = io.StringIO()
        with mock.patch.object(self.inbox, "decide", lambda state, questions: inbox_answer(state, questions)), \
                contextlib.redirect_stdout(out):
            self.inbox.main()
        rows = out.getvalue().splitlines()[1:]
        self.assertEqual(len(rows), len(self.inbox.INBOX))
        self.assertTrue(any(r.startswith("complaint") and "foodpanda" in r for r in rows))
        umbrella = next(r for r in rows if "umbrella" in r)
        self.assertTrue(umbrella.startswith("HUMAN?"))

    def run_solution(self, name):
        def responder(path, body, headers):
            return 200, inbox_answer(body["state"], body["questions"]), {}

        with FakeJev(responder) as fake:
            r = run_script(f"level2-pick-and-rate/{name}", JEV_BASE_URL=fake.url, JEV_API_KEY="k")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = r.stdout.split("Most urgent first:")[1].strip().splitlines()
        urgencies = [float(line.split()[0]) for line in rows]
        self.assertEqual(urgencies, sorted(urgencies, reverse=True))
        return rows, fake.requests[0]["body"]["questions"]["box"]["criteria"]

    def test_solution_a_adds_the_missing_box(self):
        rows, boxes = self.run_solution("solution_a.py")
        self.assertIn("lost_item", boxes)
        self.assertTrue(any("lost_item" in line and "umbrella" in line for line in rows))

    def test_solution_b_sends_other_to_a_human(self):
        rows, boxes = self.run_solution("solution_b.py")
        self.assertIn("other", boxes)
        self.assertNotIn("lost_item", boxes)
        self.assertTrue(any("HUMAN" in line and "umbrella" in line for line in rows))
        self.assertTrue(any(line.split()[1] == "complaint" and "foodpanda" in line for line in rows))


def gate_answers(risk=0.0, kind="read_only", on_goal=0.9, tricked=0.05):
    return {"risk": score_answer(risk), "kind": choice_answer(kind), "on_goal": noul_answer(on_goal),
            "tricked": noul_answer(tricked)}


class Level2Portfolio(unittest.TestCase):
    """The challenge: the participant writes the buckets, the question and describe()."""

    def setUp(self):
        add_path("level2-pick-and-rate")
        self.p = load("level2-pick-and-rate/portfolio.py", "portfolio_under_test")

    def test_starter_still_has_its_todos(self):
        self.assertIn("TODO", self.p.QUESTIONS["bucket"]["instructions"])
        self.assertTrue(all("TODO" in meaning for meaning in self.p.BUCKETS.values()))
        self.assertEqual(self.p.describe(self.p.STOCKS[0]), self.p.STOCKS[0]["name"])   # only the name, for now

    def test_questions_are_valid_for_the_api(self):
        jev.mock_decide({"model": "jev-latest", "state": "x", "questions": self.p.QUESTIONS})  # raises if invalid

    def test_sort_puts_each_company_in_its_bucket_and_unsure_ones_to_a_human(self):
        def fake(state, questions):
            box, conf = ("rocket", 0.9) if "Robotics" in state else ("shrinking", 0.8) if "Fax" in state else ("steady", 0.3)
            return response({"bucket": choice_answer(box, conf, [k for k in questions["bucket"]["criteria"] if k != box])})

        with mock.patch.object(self.p, "decide", side_effect=fake) as d:
            results, buckets = self.p.sort_portfolio()
        self.assertEqual([stock["name"] for stock, _ in results], [s["name"] for s in self.p.STOCKS])
        self.assertEqual(d.call_count, len(self.p.STOCKS))   # one call per company
        self.assertEqual([n for n, _ in buckets["rocket"]], ["Pearl Robotics"])
        self.assertEqual([n for n, _ in buckets["shrinking"]], ["Formosa Fax"])
        self.assertEqual(len(buckets["HUMAN?"]), 3)          # confidence 0.3 < MIN_CONFIDENCE
        self.assertEqual(buckets["steady"], [])

    def test_the_starter_invests_equally_and_the_market_scores_it(self):
        market = load("level2-pick-and-rate/market.py", "market_under_test")
        results = [(s, {"choice": "steady", "confidence": 0.9}) for s in self.p.STOCKS]
        allocation = self.p.invest(results)
        self.assertEqual(set(allocation), set(market.FUTURE))
        self.assertAlmostEqual(sum(allocation.values()), market.BUDGET)
        self.assertAlmostEqual(market.worth(allocation), 2_260_000)                 # the starter: x2.26
        self.assertAlmostEqual(market.worth({"Pearl Robotics": market.BUDGET}), 6_000_000)
        self.assertAlmostEqual(market.worth({}), market.BUDGET)                     # cash stays cash
        self.assertEqual(market.sorting_score({"rocket": [("Pearl Robotics", 0.9)], "HUMAN?": [("SkyDumpling Delivery", 0.3)]}), 2)


class Level3Console(unittest.TestCase):
    """The challenge: the participant writes the guard of an AI agent's console."""

    def setUp(self):
        add_path("level3-guardrail")
        self.g = load("level3-guardrail/console_guard.py", "console_guard_under_test")

    def test_starter_has_its_todos_and_runs_on_any_command(self):
        self.assertEqual(self.g.describe("rm -rf /"), "rm -rf /")          # TODO 2: only the command, for now
        self.assertEqual(set(self.g.QUESTIONS), {"dangerous"})             # TODO 1: one vague question
        jev.mock_decide({"model": "jev-latest", "state": "x", "questions": self.g.QUESTIONS})  # valid for the API

    def test_one_call_and_your_rules_decide(self):
        seen = []

        def fake(state, questions):
            seen.append(state)
            return response({"dangerous": noul_answer(0.9 if "rm" in state else 0.1)})

        with mock.patch.object(self.g, "decide", side_effect=fake):
            self.assertEqual(self.g.check("rm -rf /shop")[:2], ("BLOCK", "Jev thinks it is dangerous"))
            self.assertEqual(self.g.check("ls /shop")[0], "RUN")
        self.assertEqual(seen, ["rm -rf /shop", "ls /shop"])                # one call per command
        self.assertIn(self.g.guard({"dangerous": noul_answer(0.7)}, "x")[0], ("RUN", "ASK", "BLOCK"))


class Level3(unittest.TestCase):
    def setUp(self):
        add_path("level3-guardrail")
        self.gate = load("level3-guardrail/agent_gate.py", "agent_gate_under_test")

    def test_gate_rules(self):
        g = self.gate.gate
        self.assertEqual(g(gate_answers())[0], "ALLOW")
        self.assertEqual(g(gate_answers(tricked=0.8))[0], "BLOCK")
        self.assertEqual(g(gate_answers(on_goal=0.1))[0], "BLOCK")
        self.assertEqual(g(gate_answers(risk=2.7))[0], "ASK_HUMAN")
        for kind in ("spend_money", "delete_data", "message_people"):
            self.assertEqual(g(gate_answers(kind=kind))[0], "ASK_HUMAN", kind)
        # prompt injection wins over everything else
        self.assertEqual(g(gate_answers(risk=0, on_goal=1, tricked=0.9))[0], "BLOCK")

    def test_questions_are_valid_and_state_is_json(self):
        jev.mock_decide({"model": "jev-latest", "state": self.gate.TOOL_CALLS[0], "questions": self.gate.QUESTIONS})
        self.assertEqual(len(self.gate.QUESTIONS), 4)

    def test_one_call_per_tool_call(self):
        calls = []

        def fake_decide(state, questions):
            calls.append(state)
            return response(gate_answers(tricked=0.9 if "IGNORE" in str(state).upper() else 0.05))

        out = io.StringIO()
        with mock.patch.object(self.gate, "decide", fake_decide), contextlib.redirect_stdout(out):
            self.gate.main()
        self.assertEqual(len(calls), len(self.gate.TOOL_CALLS))
        self.assertIsInstance(calls[0], dict)
        self.assertIn("BLOCK      bank.transfer", out.getvalue())

    def test_solution_a_allows_only_small_clean_refunds(self):
        solution, _ = load_solutions("level3-guardrail")
        refund = {"tool": "pos.refund", "arguments": {"amount_twd": 85}}
        big = {"tool": "pos.refund", "arguments": {"amount_twd": 5000}}

        def check(call, **answers):
            with mock.patch.object(solution, "decide", lambda state, questions: response(gate_answers(**answers))):
                return solution.check(call)[0]

        self.assertEqual(check(refund, kind="spend_money", on_goal=0.95), "ALLOW")
        self.assertEqual(check(big, kind="spend_money", on_goal=0.95), "ASK_HUMAN")
        self.assertEqual(check(refund, kind="spend_money", on_goal=0.95, tricked=0.6), "BLOCK")
        self.assertEqual(check(refund, kind="spend_money", on_goal=0.5), "ASK_HUMAN")
        self.assertEqual(solution.RED_TEAM[0]["tool"], "website.update_page")

    def test_solution_b_lets_jev_decide_from_a_policy(self):
        _, solution = load_solutions("level3-guardrail")
        seen = []

        def fake(state, questions):
            seen.append(questions)
            return response({"decision": choice_answer("ASK_HUMAN", 0.8, ["ALLOW", "BLOCK"])})

        with mock.patch.object(solution, "decide", fake):
            decision, reason = solution.check({"tool": "pos.refund", "arguments": {"amount_twd": 85}})
        self.assertEqual((decision, reason), ("ASK_HUMAN", "confidence 0.80"))
        self.assertEqual(sorted(seen[0]["decision"]["criteria"]), ["ALLOW", "ASK_HUMAN", "BLOCK"])
        jev.mock_decide({"model": "jev-latest", "state": "x", "questions": seen[0]})  # a valid request

    def test_bonus_compares_models_with_criteria(self):
        def responder(path, body, headers):
            if path == "/v1/models":
                return FakeJev.default(path, body, headers)
            tricked = 0.9 if "IGNORE" in json.dumps(body["state"]).upper() else 0.05
            return 200, response(gate_answers(tricked=tricked)), {}

        with FakeJev(responder) as fake:
            r = run_script("level3-guardrail/bonus_models.py", JEV_BASE_URL=fake.url, JEV_API_KEY="k")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(fake.requests[0]["path"], "/v1/models")
        calls = fake.requests[1:]
        self.assertEqual(len(calls), 2 * len(self.gate.TOOL_CALLS))  # every tool call, both models
        self.assertEqual({c["body"]["model"] for c in calls}, {"jev-latest", "jev-preview"})
        self.assertIn("true", calls[0]["body"]["questions"]["tricked"]["criteria"])
        self.assertIn("Cost of this whole comparison", r.stdout)


if __name__ == "__main__":
    unittest.main()
