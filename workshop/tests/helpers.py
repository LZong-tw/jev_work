"""Shared test helpers: paths, a fake Jev HTTP server, and scripted Jev answers."""
import contextlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORKSHOP = Path(__file__).resolve().parents[1]
REPO = WORKSHOP.parent
if str(WORKSHOP) not in sys.path:
    sys.path.insert(0, str(WORKSHOP))


def add_path(folder):
    p = str(WORKSHOP / folder)
    if p not in sys.path:
        sys.path.insert(0, p)


def load(relpath, name):
    """Import a file under a unique module name (several levels have a solution.py)."""
    spec = importlib.util.spec_from_file_location(name, WORKSHOP / relpath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_solutions(folder):
    """(solution_a, solution_b) of one level. Every level has files with these names, and
    solution_b does "from solution_a import ...", so make sure it finds THIS level's file."""
    add_path(folder)
    for name in ("solution_a", "solution_b"):
        sys.modules.pop(name, None)
    a = load(f"{folder}/solution_a.py", "solution_a")
    sys.modules["solution_a"] = a
    b = load(f"{folder}/solution_b.py", f"{folder}_solution_b")
    sys.modules.pop("solution_a", None)
    return a, b


def clean_env(**extra):
    """Environment for running a workshop script: no real key, no .env surprises."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("JEV_") and k != "JUNCTION_RUNS_DIR"}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    env.update({k: str(v) for k, v in extra.items()})
    return env


def run_script(relpath, *args, timeout=120, **env):
    return subprocess.run(
        [sys.executable, str(WORKSHOP / relpath), *args],
        cwd=str(WORKSHOP), env=clean_env(**env), capture_output=True, text=True, timeout=timeout,
    )


@contextlib.contextmanager
def patched_env(**values):
    """Set JEV_* variables for in-process calls, restore afterwards."""
    old = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Scripted answers in the exact Jev response shape
# ---------------------------------------------------------------------------

def noul_answer(p):
    return {"type": "noul", "noul": p}


def choice_answer(label, confidence=0.9, others=()):
    probs = {label: confidence}
    rest = (1 - confidence) / max(1, len(others))
    probs.update({o: round(rest, 3) for o in others})
    return {"type": "choice", "choice": label, "confidence": confidence, "probabilities": probs}


def score_answer(value, confidence=0.9):
    return {"type": "score", "score": value, "confidence": confidence, "probabilities": {}}


def response(answers, tokens=42):
    return {"model": "jev-test", "answers": answers, "usage": {"input_tokens": tokens, "output_tokens": 20}}


# ---------------------------------------------------------------------------
# A fake Jev API server
# ---------------------------------------------------------------------------

class FakeJev:
    """HTTP server that records requests. `responder(path, body, headers)` returns
    (status, json_body, extra_headers). Default: answer every question with a fixed value."""

    def __init__(self, responder=None):
        self.requests = []
        self.responder = responder or self.default
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.do_POST()

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8")
                body = json.loads(raw) if raw else None
                headers = {k.lower(): v for k, v in self.headers.items()}  # header names are case-insensitive
                fake.requests.append({"path": self.path, "body": body, "headers": headers})
                status, payload, headers = fake.responder(self.path, body, headers)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @staticmethod
    def default(path, body, headers):
        if path == "/v1/models":
            return 200, {"models": [{"name": "jev-latest", "description": "fake", "release_date": "2026-09-10"},
                                    {"name": "jev-preview", "description": "fake", "release_date": "2026-09-10"}]}, {}
        answers = {}
        for qid, q in (body or {}).get("questions", {}).items():
            if q["type"] == "noul":
                answers[qid] = noul_answer(0.5)
            elif q["type"] == "choice":
                answers[qid] = choice_answer(next(iter(q["criteria"])))
            else:
                answers[qid] = score_answer(1.0)
        return 200, response(answers), {}

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
