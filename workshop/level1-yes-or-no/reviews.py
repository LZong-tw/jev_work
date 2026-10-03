"""
Level 1 - Yes or No?

One state + one yes/no question -> a probability between 0 and 1.

Run:  python level1-yes-or-no/reviews.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev import decide, noul, bar  # noqa: E402

REVIEWS = [
    "Brown sugar milk tea was perfect. Pearls soft and warm. Will come back!",
    "Waited 40 minutes at the Ximending shop. Tea was cold when I got it.",
    "It's okay. A bit too sweet for me, next time I will order 30% sugar.",
    "Staff were so friendly, they gave my kid a free sticker :)",
    "The cup was leaking all over my scooter seat. Not happy.",
    "Price went up again. NT$85 for a small tea? Hmm.",
]

# What a person says: is this customer happy? (The browser scores your question against it.)
EXPECTED = ["yes", "no", "no", "yes", "no", "no"]

# The question we ask about every review.
QUESTION = noul("Is the customer happy with their visit?")

# Decide where to draw the line between YES and NO.
THRESHOLD = 0.5


def main():
    for review in REVIEWS:
        result = decide(state=review, questions={"happy": QUESTION})
        p = result["answers"]["happy"]["noul"]
        label = "YES" if p >= THRESHOLD else "NO "
        print(f"{label} {p:.2f} [{bar(p)}]  {review}")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# TRY IT
# 1. Change the question to: "Does the review talk about price?"
# 2. Change THRESHOLD to 0.8. Which reviews change from YES to NO?
# 3. Add your own review in Chinese (e.g. "珍珠很Q，好喝!"). Does it still work?
# 4. Print the full JSON: print(result). Find "answers", "usage", "model".
# ---------------------------------------------------------------------------
