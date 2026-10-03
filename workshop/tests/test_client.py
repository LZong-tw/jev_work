"""Tests for jev.py: question builders, the HTTP call, retries, errors, mock mode."""
import contextlib
import io
import json
import os
import time
import unittest

from helpers import FakeJev, patched_env, response, run_script

import jev


class BuildersTest(unittest.TestCase):
    def test_builders_make_plain_protocol_dicts(self):
        self.assertEqual(jev.noul("Spam?"), {"type": "noul", "instructions": "Spam?"})
        self.assertEqual(
            jev.choice("Team?", {"a": "x", "b": "y"}),
            {"type": "choice", "instructions": "Team?", "criteria": {"a": "x", "b": "y"}},
        )
        self.assertEqual(
            jev.score("Urgent?", ["low", "high"]),
            {"type": "score", "instructions": "Urgent?", "criteria": ["low", "high"]},
        )

    def test_bar_is_clamped(self):
        self.assertEqual(jev.bar(0, 10), "." * 10)
        self.assertEqual(jev.bar(1, 10), "#" * 10)
        self.assertEqual(jev.bar(2, 10), "#" * 10)
        self.assertEqual(jev.bar(-1, 10), "." * 10)
        self.assertEqual(jev.bar(0.5, 10), "#####.....")


class MockDecideTest(unittest.TestCase):
    def test_answers_all_types_in_jev_shape(self):
        r = jev.mock_decide({
            "model": "jev-latest",
            "state": "Customer: I was charged twice and want a refund NOW. This is urgent!",
            "questions": {
                "route": jev.choice("Where?", {"billing": "money, charged, refund", "bug": "broken", "account": "login"}),
                "urgency": jev.score("How urgent?", ["routine", "today", "urgent", "critical"]),
                "escalate": jev.noul("Is this urgent? Escalate?"),
            },
        })
        a = r["answers"]
        self.assertEqual(r["model"], "jev-mock")
        self.assertEqual(a["route"]["choice"], "billing")
        self.assertAlmostEqual(sum(a["route"]["probabilities"].values()), 1, delta=0.03)
        self.assertEqual(a["route"]["confidence"], max(a["route"]["probabilities"].values()))
        self.assertTrue(0 <= a["urgency"]["score"] <= 3)
        self.assertEqual(set(a["urgency"]["probabilities"]), {"0", "1", "2", "3"})
        self.assertGreater(a["escalate"]["noul"], 0.5)
        self.assertGreater(r["usage"]["input_tokens"], 0)

    def test_sentiment_direction(self):
        q = {"happy": jev.noul("Is the customer happy?")}
        good = jev.mock_decide({"model": "jev-latest", "state": "I love it, great and delicious, thank you!", "questions": q})
        bad = jev.mock_decide({"model": "jev-latest", "state": "Terrible, cold and late. The worst.", "questions": q})
        self.assertGreater(good["answers"]["happy"]["noul"], bad["answers"]["happy"]["noul"])

    def test_deterministic(self):
        body = {"model": "jev-latest", "state": {"any": "json"}, "questions": {"q": jev.noul("Yes?")}}
        self.assertEqual(jev.mock_decide(body), jev.mock_decide(body))

    def test_validates_like_the_api(self):
        ok = {"model": "jev-latest", "state": "", "questions": {"q": jev.choice("x", {"only": None})}}
        self.assertEqual(jev.mock_decide(ok)["answers"]["q"]["choice"], "only")  # empty state, one option: fine
        with self.assertRaises(jev.JevError) as e:
            jev.mock_decide({"state": "x", "questions": {"q": jev.noul("x")}})
        self.assertEqual((e.exception.status, e.exception.message), (422, "model: Field required"))
        with self.assertRaises(jev.JevError) as e:
            jev.mock_decide({"model": "jev-latest", "state": "x", "questions": {"q": {"type": "maybe"}}})
        self.assertEqual((e.exception.status, e.exception.message), (400, "Invalid request."))
        with self.assertRaises(jev.JevError) as e:
            jev.mock_decide({"model": "jev-latest", "state": "x", "questions": {"q": jev.score("x", [str(i) for i in range(11)])}})
        self.assertEqual((e.exception.status, e.exception.message), (400, "Too many score levels. Must have at most 10 levels."))


class DecideHttpTest(unittest.TestCase):
    def test_posts_protocol_request_and_returns_json(self):
        with FakeJev() as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="jvp_test", JEV_MOCK="0", JEV_MODEL="jev-latest"):
            r = jev.decide("hello", {"ok": jev.noul("Ok?")})
        self.assertEqual(r["answers"]["ok"]["noul"], 0.5)
        req = fake.requests[0]
        self.assertEqual(req["path"], "/v1/systemone")
        self.assertEqual(req["headers"]["authorization"], "Bearer jvp_test")
        self.assertEqual(req["headers"]["content-type"], "application/json")
        self.assertEqual(req["body"], {"model": "jev-latest", "state": "hello", "questions": {"ok": jev.noul("Ok?")}})

    def test_model_defaults_to_jev_latest_and_can_be_changed(self):
        with FakeJev() as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="k", JEV_MOCK="0", JEV_MODEL=None):
            jev.decide("x", {"q": jev.noul("?")})
            jev.decide("x", {"q": jev.noul("?")}, model="jev-preview")
            with patched_env(JEV_MODEL="jev-preview"):
                jev.decide("x", {"q": jev.noul("?")})
        self.assertEqual([r["body"]["model"] for r in fake.requests], ["jev-latest", "jev-preview", "jev-preview"])

    def test_models_list(self):
        with FakeJev() as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="k", JEV_MOCK="0"):
            names = [m["name"] for m in jev.models()["models"]]
        self.assertEqual(names, ["jev-latest", "jev-preview"])
        self.assertEqual(fake.requests[0]["path"], "/v1/models")

    def test_noul_criteria_and_cost(self):
        self.assertEqual(jev.noul("Spam?", yes="ads", no="friends"),
                         {"type": "noul", "instructions": "Spam?", "criteria": {"true": "ads", "false": "friends"}})
        self.assertAlmostEqual(jev.cost_usd({"usage": {"input_tokens": 1_000_000}}), 0.042)

    def test_validation_errors_are_readable(self):
        def responder(path, body, headers):
            return 422, {"detail": [{"type": "missing", "loc": ["body", "model"], "msg": "Field required"}]}, {}

        with FakeJev(responder) as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="k", JEV_MOCK="0"):
            with self.assertRaises(jev.JevError) as e:
                jev.decide("x", {"q": jev.noul("?")})
        self.assertEqual((e.exception.status, e.exception.code, e.exception.message), (422, "missing", "model: Field required"))

    def test_retries_after_429_then_succeeds(self):
        calls = []

        def responder(path, body, headers):
            calls.append(1)
            if len(calls) == 1:
                return 429, {"detail": {"error_type": "rate_limit_error", "message": "Too many requests."}}, {"Retry-After": "0"}
            return 200, response({"q": {"type": "noul", "noul": 0.9}}), {}

        with FakeJev(responder) as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="k", JEV_MOCK="0"):
            r = jev.decide("x", {"q": jev.noul("?")})
        self.assertEqual(r["answers"]["q"]["noul"], 0.9)
        self.assertEqual(len(fake.requests), 2)

    def test_errors_raise_jev_error_without_retry(self):
        def responder(path, body, headers):
            return 402, {"detail": {"error_type": "budget_exceeded_error", "message": "This key has used its full budget."}}, {}

        with FakeJev(responder) as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="k", JEV_MOCK="0"):
            with self.assertRaises(jev.JevError) as e:
                jev.decide("x", {"q": jev.noul("?")})
        self.assertEqual((e.exception.status, e.exception.code), (402, "budget_exceeded_error"))
        self.assertIn("full budget", str(e.exception))
        self.assertEqual(len(fake.requests), 1)

    def test_gives_up_after_retries(self):
        def responder(path, body, headers):
            return 502, {"detail": {"error_type": "api_error", "message": "Upstream error."}}, {"Retry-After": "0"}

        with FakeJev(responder) as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="k", JEV_MOCK="0"):
            with self.assertRaises(jev.JevError) as e:
                jev.decide("x", {"q": jev.noul("?")}, retries=2)
        self.assertEqual(e.exception.status, 502)
        self.assertEqual(len(fake.requests), 3)

    def test_retries_529_overloaded_and_honors_retry_after_ms(self):
        calls = []

        def responder(path, body, headers):
            calls.append(1)
            if len(calls) == 1:
                return 529, {"detail": "Overloaded"}, {"retry-after-ms": "10", "Retry-After": "30"}
            return 200, response({"q": {"type": "noul", "noul": 0.9}}), {}

        with FakeJev(responder) as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="k", JEV_MOCK="0"):
            start = time.time()
            r = jev.decide("x", {"q": jev.noul("?")})
        self.assertEqual(r["answers"]["q"]["noul"], 0.9)
        self.assertLess(time.time() - start, 5)  # waited 10 ms, not 30 s
        self.assertEqual(len(fake.requests), 2)

    def test_error_keeps_the_typesafe_request_id(self):
        def responder(path, body, headers):
            return 400, {"detail": "Too many score levels. Must have at most 10 levels."}, {"x-typesafe-request-id": "req_abc"}

        with FakeJev(responder) as fake, patched_env(JEV_BASE_URL=fake.url, JEV_API_KEY="k", JEV_MOCK="0"):
            with self.assertRaises(jev.JevError) as e:
                jev.decide("x", {"q": jev.score("?", ["a", "b"])})
        self.assertEqual((e.exception.status, e.exception.request_id), (400, "req_abc"))
        self.assertIn("at most 10 levels", e.exception.message)

    def test_official_sdk_env_names_work_too(self):
        with FakeJev() as fake, patched_env(JEV_BASE_URL=None, JEV_API_KEY=None, JEV_MODEL=None, JEV_MOCK="0",
                                            TYPESAFE_BASE_URL=fake.url, TYPESAFE_API_KEY="ts_key",
                                            TYPESAFE_DEFAULT_MODEL="jev-preview"):
            jev.decide("x", {"q": jev.noul("?")})
        self.assertEqual(fake.requests[0]["headers"]["authorization"], "Bearer ts_key")
        self.assertEqual(fake.requests[0]["body"]["model"], "jev-preview")

    def test_unreachable_server(self):
        with patched_env(JEV_BASE_URL="http://127.0.0.1:9/api", JEV_API_KEY="k", JEV_MOCK="0"):
            with self.assertRaises(jev.JevError) as e:
                jev.decide("x", {"q": jev.noul("?")}, retries=0, timeout=2)
        self.assertEqual(e.exception.status, 0)
        self.assertIn("Cannot reach", str(e.exception))

    def test_missing_settings(self):
        with patched_env(JEV_BASE_URL=None, JEV_API_KEY=None, JEV_MOCK="0"):
            with self.assertRaises(jev.JevError) as e:
                jev.decide("x", {"q": jev.noul("?")})
        self.assertIn("JEV_BASE_URL", str(e.exception))

    def test_mock_mode_needs_no_network_and_warns_once(self):
        jev._mock_warned = False
        err = io.StringIO()
        with patched_env(JEV_MOCK="1", JEV_BASE_URL=None, JEV_API_KEY=None), contextlib.redirect_stderr(err):
            jev.decide("I love it", {"q": jev.noul("Happy?")})
            jev.decide("I love it", {"q": jev.noul("Happy?")})
        self.assertEqual(err.getvalue().count("MOCK MODE"), 1)


class ShowTest(unittest.TestCase):
    def test_prints_every_answer_type(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            jev.show(response({
                "a": {"type": "noul", "noul": 0.25},
                "b": {"type": "choice", "choice": "x", "confidence": 0.8, "probabilities": {"x": 0.8, "y": 0.2}},
                "c": {"type": "score", "score": 2.4, "confidence": 0.7},
            }), title="T")
        text = out.getvalue()
        for needle in ("=== T ===", "noul   0.25", "choice 'x'", "score  2.40", "input tokens"):
            self.assertIn(needle, text)


class SetupCheckTest(unittest.TestCase):
    def test_self_check_in_mock_mode(self):
        r = run_script("jev.py", JEV_MOCK=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("You are ready.", r.stdout)

    def test_self_check_reports_failure(self):
        r = run_script("jev.py", JEV_MOCK=0, JEV_BASE_URL="http://127.0.0.1:9/api", JEV_API_KEY="jvp_abcdefghijklmnop")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAILED", r.stdout)
        self.assertIn("jvp_abcd...mnop", r.stdout)  # key is masked

    def test_self_check_against_fake_server(self):
        with FakeJev() as fake:
            r = run_script("jev.py", JEV_MOCK=0, JEV_BASE_URL=fake.url, JEV_API_KEY="jvp_abcdefghijklmnop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("model jev-test", r.stdout)


if __name__ == "__main__":
    unittest.main()


class MatchesTheRealApiTest(unittest.TestCase):
    """Requests recorded from the real TypeSafe API; the offline mock must answer the same way."""

    def test_mock_matches_every_recorded_case(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "proxy", "test", "fixtures", "systemone-cases.json")
        with open(path, encoding="utf-8") as f:
            cases = json.load(f)["cases"]
        self.assertGreaterEqual(len(cases), 35)
        for case in cases:
            req, expect = case["request"], case["expect"]
            with self.subTest(case["name"]):
                invalid = jev.mock_validate(req)
                if expect["status"] == 200:
                    self.assertIsNone(invalid)
                    result = jev.mock_decide(req)
                    answer = result["answers"]["q"]
                    self.assertEqual(list(result), expect["top_keys"])
                    self.assertEqual(list(result["usage"]), expect["usage_keys"])
                    self.assertEqual(list(answer), expect["answer_keys"])  # same fields, same order
                    if "legend" in expect:
                        self.assertEqual(answer["legend"], expect["legend"])
                    if "probability_keys" in expect:
                        self.assertEqual(sorted(answer["probabilities"]), expect["probability_keys"])
                else:
                    status, body = invalid
                    if isinstance(body["detail"], list):
                        body = {"detail": [{k: e[k] for k in ("type", "loc", "msg")} for e in body["detail"]]}
                    self.assertEqual((status, body), (expect["status"], expect["body"]))

    def test_mock_errors_raise_like_real_ones(self):
        with self.assertRaises(jev.JevError) as e:
            jev.mock_decide({"model": "jev-latest", "state": "x", "questions": {}})
        self.assertEqual((e.exception.status, e.exception.code), (422, "too_short"))
        with self.assertRaises(jev.JevError) as e:
            jev.mock_decide({"model": "gpt-4", "state": "x", "questions": {"q": jev.noul("?")}})
        self.assertEqual((e.exception.status, e.exception.code, e.exception.message), (400, "api_usage_error", "Unknown model: gpt-4"))

    def test_mock_models_lists_both_aliases(self):
        with patched_env(JEV_MOCK="1"):
            self.assertEqual([m["name"] for m in jev.models()["models"]], ["jev-latest", "jev-preview"])
