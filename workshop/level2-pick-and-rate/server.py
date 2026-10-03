"""
Level 2 in your browser: watch Jev sort the inbox, rate the urgency, and ask a human when it is unsure.

    python level2-pick-and-rate/server.py      # opens http://localhost:8002/

Two tabs. Inbox: INBOX, QUESTIONS and MIN_CONFIDENCE from inbox.py (add a box!). Portfolio (the
challenge): STOCKS, QUESTIONS, MIN_CONFIDENCE and YOUR describe() from portfolio.py; add as many
companies as you like in the page, and describe() writes what Jev reads about each one. Edit the code,
reload the page: it uses your new code. Click a card to see the exact JSON Jev gets, change it, send it.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import web  # noqa: E402


def level():
    inbox, portfolio, market = web.fresh("inbox"), web.fresh("portfolio"), web.fresh("market")
    return {"file": "inbox.py", "items": inbox.INBOX, "questions": inbox.QUESTIONS, "min_confidence": inbox.MIN_CONFIDENCE,
            "expected": getattr(inbox, "EXPECTED", None),
            "portfolio": {"file": "portfolio.py", "stocks": portfolio.STOCKS, "questions": portfolio.QUESTIONS,
                          "min_confidence": portfolio.MIN_CONFIDENCE, "budget": market.BUDGET, "expert": market.EXPERT,
                          "future": market.FUTURE}}


def portfolio_request(body):
    """POST /api/portfolio_request {"stock": {"name": ..., "notes": ...}}: the request YOUR code makes for it."""
    stock = body.get("stock") if isinstance(body, dict) else None
    if not isinstance(stock, dict) or not isinstance(stock.get("name"), str) or not stock["name"].strip() \
            or not isinstance(stock.get("notes", ""), str):
        raise web.BadRequest('send {"stock": {"name": "a company", "notes": "what you know about it"}}')
    portfolio = web.fresh("portfolio")
    return {"state": portfolio.describe({"name": stock["name"].strip(), "notes": stock.get("notes", "").strip()}),
            "questions": portfolio.QUESTIONS}


def invest(body):
    """POST /api/invest {"results": [{"stock": {...}, "answer": {...}}]}: how YOUR invest() shares out the money."""
    rows = body.get("results") if isinstance(body, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("stock"), dict) and isinstance(r.get("answer"), dict) for r in rows):
        raise web.BadRequest('send {"results": [{"stock": {"name": ..., "notes": ...}, "answer": {"choice": ..., "confidence": ...}}]}')
    portfolio, budget = web.fresh("portfolio"), web.fresh("market").BUDGET
    try:
        allocation = portfolio.invest([(r["stock"], r["answer"]) for r in rows], budget)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        raise web.BadRequest(f"invest() could not use these results: {type(e).__name__}: {e}") from None
    names = {r["stock"].get("name") for r in rows}
    if not isinstance(allocation, dict) or not all(n in names and isinstance(a, (int, float)) and a >= 0 for n, a in allocation.items()):
        raise web.BadRequest("invest() must return {company name: NT$ (0 or more)} for the companies it was given")
    total = sum(allocation.values())
    if total > budget * 1.000001:
        raise web.BadRequest(f"invest() spends NT${total:,.0f}, but you only have NT${budget:,}")
    return {"allocation": {n: float(a) for n, a in allocation.items()}, "budget": budget, "cash": budget - total}


if __name__ == "__main__":
    web.serve(HERE / "sim.html", "Level 2 · Pick one, and rate it", level, actions={"portfolio_request": portfolio_request, "invest": invest},
              port=8002, files={"inbox.py": HERE / "inbox.py", "portfolio.py": HERE / "portfolio.py"})
