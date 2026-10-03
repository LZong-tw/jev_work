"""
Four Crossings, live: the city runs, YOUR function sets the traffic lights.

    python level5-junction/city_server.py                 # then open the URL it prints
    python level5-junction/city_server.py --tick 1        # 1 tick = 1 second (default 2)
    python level5-junction/city_server.py --tick 0.5      # 1 tick = 500 ms
    python level5-junction/city_server.py --port 8080

The city moves in ticks. A vehicle that goes crosses its crossing in exactly 1 tick, so the
crossings are empty when a tick ends. The page runs a whole tick at once and plays it on screen
over the tick length; meanwhile it sends the state at the end of that tick here. The server calls
    new_lights = await decide(history, current)          # in my_jev.py: your code, your Jev call
with all earlier states as history (oldest first), keeps current for next time, and sends the
new lights back: the next tick runs with them. So Jev thinks while a tick plays. One tick = one
decide() call: a late answer makes the city glide to a stop and wait, it never skips a tick.
Jev's calls, tokens and cost are shown in the page.
Your API key stays here, never in the browser.

Needs JEV_BASE_URL=https://api.typesafe.ai and JEV_API_KEY in workshop/.env (or JEV_MOCK=1).
"""
import argparse
import asyncio
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
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import jev  # noqa: E402

LOCK = threading.Lock()  # one decision at a time
HISTORY = []             # every state decide() has seen, oldest first
USAGE = {"calls": 0, "tokens": 0}


def _metered(real):
    """Count every Jev call made inside decide(), so the page can show calls, tokens and cost."""
    def call(*args, **kwargs):
        result = real(*args, **kwargs)
        USAGE["calls"] += 1
        USAGE["tokens"] += result.get("usage", {}).get("input_tokens", 0)
        return result
    return call


jev.decide = _metered(jev.decide)   # before my_jev.py imports it


def make_handler(cfg, controller):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html") or self.path.startswith("/?"):
                return self.send(200, (HERE / "city.html").read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/config":
                return self.send(200, cfg)
            if self.path in ("/vendor/three.min.js", "/vendor/OrbitControls.js"):
                return self.send(200, (HERE / self.path.lstrip("/")).read_bytes(), "text/javascript; charset=utf-8")
            self.send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/decide":
                return self.send(404, {"error": "not found"})
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            with LOCK:
                try:
                    importlib.reload(controller)  # edit my_jev.py while it runs: the next call uses it
                    current = body["state"]
                    USAGE.update(calls=0, tokens=0)
                    t0 = time.time()
                    lights = controller.decide(list(HISTORY[-cfg["history"]:]), current)
                    if asyncio.iscoroutine(lights):
                        lights = asyncio.run(lights)
                    lights = {str(k): v for k, v in (lights or {}).items()}
                    bad = {k: v for k, v in lights.items() if v not in "ABCDW" or len(v) != 1}
                    if bad:
                        raise ValueError(f"decide() must return phases A, B, C, D or W per crossing, got {bad}")
                    current["lights_chosen"] = lights
                    HISTORY.append(current)
                    del HISTORY[:-500]
                    print(f"[decide] tick {current.get('tick', '?')}  {current['clock']}  " + "  ".join(f"#{k}: {v}" for k, v in lights.items())
                          + f"   ({USAGE['calls']} Jev calls, {USAGE['tokens']} tokens)", flush=True)
                    self.send(200, {"lights": lights, "calls": USAGE["calls"], "tokens": USAGE["tokens"],
                                    "cost_usd": USAGE["tokens"] * jev.PRICE_PER_MILLION_INPUT_TOKENS / 1e6,
                                    "latency_ms": round((time.time() - t0) * 1000)})
                except jev.JevError as e:
                    print(f"[jev] error: {e}", flush=True)
                    self.send(200, {"error": f"Jev API: {e}"})
                except Exception as e:  # a bug in my_jev.py: show it, keep the city running
                    traceback.print_exc()
                    self.send(200, {"error": f"{type(e).__name__}: {e}"})
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tick", type=float, default=2, help="real seconds per tick, one decide() call each (default 2; 1, 0.5 ...)")
    ap.add_argument("--history", type=int, default=50, help="how many earlier states decide() gets (default 50)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--controller", default="my_jev", help="the Python module with async decide(history, current)")
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = ap.parse_args()

    c = jev.config()
    if not c["mock"] and (not c["base_url"] or not c["api_key"]):
        sys.exit("Set JEV_BASE_URL=https://api.typesafe.ai and JEV_API_KEY in workshop/.env (or JEV_MOCK=1 to try).")
    controller = importlib.import_module(args.controller)
    if not 0.1 <= args.tick <= 60:
        sys.exit("--tick is real seconds per tick: 0.1 .. 60")
    cfg = {"tick": args.tick, "controller": args.controller, "history": args.history,
           "jev": "mock" if c["mock"] else c["base_url"]}
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(cfg, controller))
    url = f"http://localhost:{args.port}/"
    print(f"Four Crossings is running: {url}")
    print(f"Jev: {cfg['jev']} (model {c['model']}). 1 tick = {args.tick:g} s: one decide() call, every vehicle that goes crosses in it")
    print(f"Controller: {HERE / (args.controller + '.py')}  (edit it any time; Ctrl+C to stop)", flush=True)
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
