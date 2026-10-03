"""
Level 4 in your browser: run the bubble tea shop for a day, round by round, and watch it happen.

    python level4-tea-shop/server.py           # opens http://localhost:8004/

The page plays one day of shop.py: your Shop rules, and a manager: Jev, the simple rules
(rules_policy), or you. Every round it shows what Jev reads (describe() and QUESTIONS); open it in
the Jev editor to change it. Edit shop.py, then start a new day: the new day uses your new code.
"""
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import web  # noqa: E402

DAY = {"shop": None, "module": None}   # the day being played (one at a time: this is your own server)
LOCK = threading.Lock()


def level():
    shop = web.fresh("shop")
    return {"file": "shop.py", "actions": shop.ACTIONS, "questions": shop.QUESTIONS, "rounds": shop.ROUNDS}


def view(shop, m):
    return {"round": shop.round, "rounds": m.ROUNDS, "clock": shop.clock(), "weather": shop.weather, "mode": shop.mode,
            "queue": list(shop.queue), "max_wait": m.MAX_WAIT, "pearls": shop.pearls, "tea": shop.tea, "energy": shop.energy,
            "cap": m.CAP, "points": shop.points, "served": shop.served, "angry": shop.angry, "done": shop.round >= m.ROUNDS}


def round_start(shop, m):
    """Customers walk in, the state machine moves; then the manager decides (what Jev reads: decision)."""
    before = len(shop.queue)
    shop.open_round()
    transition = shop.update_mode()
    return {"arrived": len(shop.queue) - before, "transition": transition, "view": view(shop, m),
            "decision": {"state": shop.describe(), "questions": m.QUESTIONS}}


def the_day():
    if DAY["shop"] is None:
        raise web.BadRequest("start a day first (POST /api/new)")
    return DAY["shop"], DAY["module"]


def new_day(body):
    """POST /api/new {"seed": 1}: a new day with the code in shop.py now."""
    seed = body.get("seed", 1)
    if not isinstance(seed, int):
        raise web.BadRequest('"seed" is a whole number')
    with LOCK:
        m = web.fresh("shop")
        DAY.update(shop=m.Shop(seed), module=m)
        return {"seed": seed, "actions": m.ACTIONS, "best": best_possible(seed), **round_start(DAY["shop"], m)}


def best_possible(seed):
    """The best score any plan can get on this day (best_possible.py tries them all): your target."""
    try:
        return web.fresh("best_possible").best_possible(seed)
    except Exception:  # e.g. you changed the shop's rules in a way the planner does not know
        return None


def rules(body):
    """POST /api/rules: what the simple if/else manager (rules_policy) would do now."""
    with LOCK:
        shop, m = the_day()
        return {"action": m.rules_policy(shop)[0]}


def step(body):
    """POST /api/step {"action": "make_drinks"}: play the round; then the next round starts."""
    with LOCK:
        shop, m = the_day()
        action = body.get("action")
        if action not in m.ACTIONS:
            raise web.BadRequest(f"action must be one of {', '.join(m.ACTIONS)}, got {action!r}")
        if shop.round >= m.ROUNDS:
            raise web.BadRequest("the day is over: start a new day")
        served, left, gained = shop.step(action)
        result = {"action": action, "served": served, "left": left, "gained": gained}
        if shop.round >= m.ROUNDS:
            return {"result": result, "view": view(shop, m), "decision": None}
        return {"result": result, **round_start(shop, m)}


if __name__ == "__main__":
    web.serve(HERE / "sim.html", "Level 4 · Run the tea shop", level,
              actions={"new": new_day, "rules": rules, "step": step}, port=8004, files={"shop.py": HERE / "shop.py"})
