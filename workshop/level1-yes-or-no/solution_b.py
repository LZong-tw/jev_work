"""
Level 1 - Solution B: THREE small questions, code combines them.

Instead of one big question, ask three simple ones in the SAME call.
If any answer is a clear YES, it is spam. You also learn WHY.

Run:  python level1-yes-or-no/solution_b.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev import decide, noul  # noqa: E402
from spam_filter import EXPECTED, MESSAGES  # noqa: E402

QUESTIONS = {
    "prize_or_money": noul("Does the message promise a prize, a gift, or easy money?"),
    "asks_secret": noul("Does the message ask for a password, a code, or personal data?"),
    "stranger_link": noul("Does a stranger push you to click a link or add a contact?"),
}
THRESHOLD = 0.5


def is_spam(message):
    """Returns (True/False, the reason)."""
    answers = decide(state=message, questions=QUESTIONS)["answers"]
    reason, p = max(((name, a["noul"]) for name, a in answers.items()), key=lambda x: x[1])
    return p >= THRESHOLD, f"{reason} {p:.2f}"


def main():
    correct = 0
    for message, expected in zip(MESSAGES, EXPECTED):
        spam, why = is_spam(message)
        got = "spam" if spam else "ok"
        correct += got == expected
        print(f"{'✓' if got == expected else '✗'} {got:<4} ({why:<20})  {message[:60]}")
    print(f"\nScore: {correct}/{len(MESSAGES)}")


if __name__ == "__main__":
    main()
