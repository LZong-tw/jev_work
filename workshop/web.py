"""
web.py - the small local web server behind the level simulators (Levels 1-4). Python 3.8+, no pip.

    python level1-yes-or-no/server.py        # then open the URL it prints (it opens by itself)

Every level has a server.py that calls serve(). It serves the level's page (sim.html) and the shared
page files in web/, and answers the page:

    GET  /api/level        the level: its items, questions and settings, read fresh from YOUR code
    POST /api/jev          {"state": ..., "questions": {...}}: one Jev call, the full JSON answer
    POST /api/code         the challenge files of the level (the ones the page may edit), as text
    POST /api/save         {"file", "source"}: the page's code editor saves one of them, only if it compiles
    POST /api/<action>     the level's own actions (Level 3: your gate(), Level 4: the shop)

Your key stays here: the page asks this server, this server asks Jev. Only this server's own page may
call it: a request from another website, or for another host name, is refused, so no website you
visit can spend your key. Edit your level's code while it runs: the next request uses the new code.
"""
import argparse
import importlib
import json
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import jev  # noqa: E402

UI = HERE / "web"
LOCAL_HOSTS = ("localhost", "127.0.0.1")
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8"}
LOCK = threading.Lock()  # one level action at a time (Level 4 keeps one shop)


class BadRequest(Exception):
    """The page sent something this level cannot use: answered with HTTP 400 and the message."""


def fresh(name):
    """The level's module, re-read from disk: edit your code while the server runs."""
    with LOCK:
        module = sys.modules.get(name)
        return importlib.reload(module) if module else importlib.import_module(name)


def ask_jev(body):
    """POST /api/jev: one Jev call with the page's state and questions, plus its cost and time."""
    if not isinstance(body, dict) or "state" not in body or not isinstance(body.get("questions"), dict) \
            or not body["questions"]:
        raise BadRequest('send {"state": ..., "questions": {"your_id": {"type": ..., ...}, ...}}')
    t0 = time.time()
    result = jev.decide(state=body["state"], questions=body["questions"], model=body.get("model"))
    return {**result, "cost_usd": jev.cost_usd(result), "latency_ms": round((time.time() - t0) * 1000)}


def code_routes(files):
    """The page's code editor: files = {"spam_filter.py": Path}, the only files it may read and save."""
    def code(_body):
        return {name: path.read_text(encoding="utf-8") for name, path in files.items()}

    def save(body):
        name, source = (body.get("file"), body.get("source")) if isinstance(body, dict) else (None, None)
        if name not in files:
            raise BadRequest(f"only {', '.join(files)} can be saved here")
        if not isinstance(source, str) or not source.strip() or len(source) > 200_000:
            raise BadRequest(f'send {{"file": "{name}", "source": "the whole file"}}')
        try:
            compile(source, name, "exec")
        except SyntaxError as e:
            raise BadRequest(f"not saved: line {e.lineno}: {e.msg}") from None
        files[name].write_text(source, encoding="utf-8")
        return {"saved": name, "lines": source.count("\n") + 1}
    return {"code": code, "save": save}


def _host_ok(host, port):
    name, _, p = (host or "").rpartition(":")
    return name in LOCAL_HOSTS and p == str(port)


def make_handler(page, level, actions, port, files=None):
    routes = {"jev": ask_jev, **(code_routes(files) if files else {}), **(actions or {})}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")                          # no other site may frame these pages
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")  # (a framed code editor + Save = clickjacking)
            self.end_headers()
            self.wfile.write(data)

        def refused(self):
            """Only this server's own page, on this machine (no other website, no other host name)."""
            if not _host_ok(self.headers.get("Host"), port):
                return "wrong host"
            origin = self.headers.get("Origin")
            if origin is not None and origin not in (f"http://{h}:{port}" for h in LOCAL_HOSTS):
                return "requests from other websites are not allowed"
            return None

        def run(self, fn, *args):
            try:
                return self.send(200, fn(*args))
            except BadRequest as e:
                return self.send(400, {"error": str(e)})
            except jev.JevError as e:
                return self.send(502, {"error": f"Jev API: {e}"})
            except Exception as e:  # a bug in the level's code: show it, keep the server running
                traceback.print_exc()
                return self.send(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self):
            why = self.refused()
            if why:
                return self.send(403, {"error": why})
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                return self.send(200, page.read_bytes(), CONTENT_TYPES[".html"])
            if path == "/api/level":
                return self.run(lambda: {**level(), "jev": _jev_info()})
            name = path[len("/ui/"):] if path.startswith("/ui/") else ""
            if name and "/" not in name and (UI / name).is_file() and (UI / name).suffix in CONTENT_TYPES:
                return self.send(200, (UI / name).read_bytes(), CONTENT_TYPES[(UI / name).suffix])
            self.send(404, {"error": "not found"})

        def do_POST(self):
            why = self.refused()
            if why:
                return self.send(403, {"error": why})
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self.send(415, {"error": "send JSON (Content-Type: application/json)"})
            name = self.path[len("/api/"):] if self.path.startswith("/api/") else ""
            if name not in routes:
                return self.send(404, {"error": "not found"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError as e:
                return self.send(400, {"error": f"not JSON: {e}"})
            self.run(routes[name], body)

    return Handler


def _jev_info():
    c = jev.config()
    return {"mock": c["mock"], "model": c["model"], "price_per_million_input_tokens": jev.PRICE_PER_MILLION_INPUT_TOKENS}


def serve(page, title, level, actions=None, port=8001, files=None):
    """Run a level's simulator. page: its sim.html. level(): the data for GET /api/level (read your
    code fresh each time). actions: {"name": fn(body) -> dict}, answered at POST /api/name.
    files: {"name.py": Path}: the challenge files the page's code editor may show and save."""
    ap = argparse.ArgumentParser(description=f"{title}: the simulator in your browser")
    ap.add_argument("--port", type=int, default=port)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = ap.parse_args()
    c = jev.config()
    if not c["mock"] and (not c["base_url"] or not c["api_key"]):
        sys.exit("Set JEV_BASE_URL and JEV_API_KEY in workshop/.env (or JEV_MOCK=1 to try).")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(Path(page), level, actions, args.port, files))
    url = f"http://localhost:{args.port}/"
    print(f"{title} is running: {url}")
    print(f"Jev: {'MOCK (fake answers)' if c['mock'] else c['base_url']} (model {c['model']}). Ctrl+C to stop.", flush=True)
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
