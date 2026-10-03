"""
Level 1 - Solution A: ONE clear question, with yes/no criteria.

Say exactly what counts as YES and what counts as NO. Jev reads both.

Run:  python level1-yes-or-no/solution_a.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev import decide, noul  # noqa: E402
from spam_filter import EXPECTED, MESSAGES  # noqa: E402

QUESTION = noul(
    "Is this message spam or a scam?",
    yes="prizes, easy money, links or LINE ids from strangers, or it asks for a password or code",
    no="a normal message from family, friends, a shop, a bank notice or a delivery service",
)
THRESHOLD = 0.5


def is_spam(message):
    """Returns (True/False, the probability)."""
    p = decide(state=message, questions={"spam": QUESTION})["answers"]["spam"]["noul"]
    return p >= THRESHOLD, p


def main():
    correct = 0
    for message, expected in zip(MESSAGES, EXPECTED):
        spam, p = is_spam(message)
        got = "spam" if spam else "ok"
        correct += got == expected
        print(f"{'✓' if got == expected else '✗'} {got:<4} p={p:.2f}  {message[:70]}")
    print(f"\nScore: {correct}/{len(MESSAGES)}")


if __name__ == "__main__":
    main()
