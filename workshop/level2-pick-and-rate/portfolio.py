"""
Level 2 - Challenge: sort a stock portfolio into buckets.

Every company gets ONE choice from Jev: how much will its revenue and earnings grow in the next
10 years? Then you invest NT$1,000,000, and fast-forward 10 years. Your job is the code: the question,
what each bucket means, what Jev reads about a company (describe()), and how you share out the money
(invest()). Jev only knows what you write. Two scores: your buckets against an expert's, and your money.

Fill in the TODOs, then run:
    python level2-pick-and-rate/portfolio.py
Watch it (and add as many companies as you like):
    python level2-pick-and-rate/server.py      # the "Portfolio" tab

The companies below are made up. This is a workshop exercise, not investment advice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev import choice, decide  # noqa: E402

import market  # noqa: E402  (what really happens in 10 years: no peeking!)

STOCKS = [
    {"name": "Pearl Robotics", "notes": "Builds robot arms that make bubble tea. Sales doubled three years in a row; "
                                        "400 shops use them, 20,000 shops in Taiwan do not yet."},
    {"name": "Formosa Fax", "notes": "Sells fax machines and paper to offices. Sales fall about 15% every year; "
                                     "no new products planned."},
    {"name": "Island Power Grid", "notes": "The electricity company for the whole island. Prices are set by the "
                                           "government; demand grows about 2% a year."},
    {"name": "SkyDumpling Delivery", "notes": "Delivers dumplings by drone in one city. Loses money on every order; "
                                              "raised money twice this year; a big rival just copied it."},
    {"name": "Taipei Chip Design", "notes": "Designs AI chips. Orders booked for the next 3 years; "
                                            "one customer is 60% of sales."},
]

# TODO 1: the buckets. Say what each one MEANS: Jev picks the label whose meaning fits best.
BUCKETS = {
    "rocket": "TODO: what does this bucket mean?",
    "grower": "TODO: what does this bucket mean?",
    "steady": "TODO: what does this bucket mean?",
    "shrinking": "TODO: what does this bucket mean?",
}

# TODO 2: the question. Be exact: growth of what, over how long? (Keep the id "bucket": the browser reads it.)
QUESTIONS = {"bucket": choice("TODO: write your question here", BUCKETS)}

# Ask a human when Jev is less sure than this.
MIN_CONFIDENCE = 0.6


def describe(stock):
    """TODO 3: what Jev reads about one company. Now it only gets the name: give it the facts (the notes)."""
    return stock["name"]


def invest(results, budget=market.BUDGET):
    """TODO 4: share out the money. results: [(stock, answer)], answer = Jev's answer for its bucket:
    {"choice": "rocket", "confidence": 0.82, "probabilities": {...}}. Return {company name: NT$}.
    What you do not invest stays cash. Now: the same for every company. Better: more for "rocket" and
    "grower", nothing for "shrinking", and more when Jev is sure (confidence)."""
    names = [stock["name"] for stock, answer in results]
    return {name: budget / len(names) for name in names} if names else {}


def bucket_of(answer):
    """Jev's bucket, or "HUMAN?" when it is less sure than MIN_CONFIDENCE."""
    return answer["choice"] if answer["confidence"] >= MIN_CONFIDENCE else "HUMAN?"


def sort_portfolio(stocks=STOCKS):
    """One Jev call per company. Returns (results, buckets): [(stock, answer)] and {bucket: [(name, confidence)]}."""
    results = [(stock, decide(state=describe(stock), questions=QUESTIONS)["answers"]["bucket"]) for stock in stocks]
    buckets = {label: [] for label in [*QUESTIONS["bucket"]["criteria"], "HUMAN?"]}
    for stock, answer in results:
        buckets.setdefault(bucket_of(answer), []).append((stock["name"], answer["confidence"]))
    return results, buckets


if __name__ == "__main__":
    results, buckets = sort_portfolio()
    for bucket, names in buckets.items():
        print(f"{bucket:<10} " + ", ".join(f"{name} ({conf:.2f})" for name, conf in names))
    allocation = invest(results)
    final = market.worth(allocation)
    print("\nYou invest: " + ", ".join(f"{name} NT${amount:,.0f}" for name, amount in allocation.items()))
    print(f"10 years later: NT${market.BUDGET:,} -> NT${final:,.0f} (x{final / market.BUDGET:.2f})")
    print(f"Sorting score: {market.sorting_score(buckets)}/{len(market.EXPERT)} like the expert")

# ---------------------------------------------------------------------------
# TRY IT
# 1. Run it as it is: Jev only reads the names. Then fill in describe(). What changes?
# 2. Make the buckets exact: "rocket" = revenue at least 5x in 10 years? Write numbers.
# 3. SkyDumpling: growing fast but losing money. Which bucket? Add a second question
#    (a score: "How risky is this company?") and show it next to the bucket.
# 4. In the browser, add a real company you know, with your own notes. Does Jev agree with you?
# 5. TODO 4: invest by confidence. Can you turn NT$1,000,000 into more than NT$4,000,000?
# ---------------------------------------------------------------------------
