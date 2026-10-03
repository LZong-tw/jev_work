"""
Level 1 - Challenge: build a LINE spam filter.

Fill in the TODOs, then run:  python level1-yes-or-no/spam_filter.py
Goal: every message in MESSAGES gets the right label in EXPECTED.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev import decide, noul  # noqa: E402

MESSAGES = [
    "Hi Mom, I will be home late tonight, the MRT is very crowded.",
    "Congratulations!! You won an iPhone 17. Click http://bit.ly/xx to claim in 24 hours",
    "Your package from Shopee is at the 7-Eleven on Zhongshan Rd. Pick up before Friday.",
    "[Bank] Your account is locked. Send your password to unlock: 0912-xxx-xxx",
    "Team lunch at the beef noodle place at 12:30? 🍜",
    "Earn NT$30,000 a week from home!!! Add my LINE id to learn the secret",
]
EXPECTED = ["ok", "spam", "ok", "spam", "ok", "spam"]

# TODO 1: write a clear yes/no question. Tip: say what "spam" means for you.
QUESTION = noul("TODO: write your question here")

# TODO 2: choose a threshold. Higher = fewer false alarms, but more spam gets through.
THRESHOLD = 0.5

if __name__ == "__main__":
    correct = 0
    for msg, expected in zip(MESSAGES, EXPECTED):
        p = decide(state=msg, questions={"spam": QUESTION})["answers"]["spam"]["noul"]
        got = "spam" if p >= THRESHOLD else "ok"
        mark = "✓" if got == expected else "✗"
        correct += got == expected
        print(f"{mark} {got:<4} p={p:.2f}  {msg[:70]}")

    print(f"\nScore: {correct}/{len(MESSAGES)}")
