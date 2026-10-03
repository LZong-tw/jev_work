"""
Level 1 in your browser: watch Jev answer yes/no, and move the threshold.

    python level1-yes-or-no/server.py          # opens http://localhost:8001/

The page reads REVIEWS, QUESTION and THRESHOLD from reviews.py, and MESSAGES, EXPECTED, QUESTION and
THRESHOLD from spam_filter.py. Edit them (in your editor, or in the page: it saves the file), and the page
uses your new code. Your score: how many of the 6 messages your spam filter gets right. Click a card to
see the exact JSON Jev gets, change it, and send it.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import web  # noqa: E402


def level():
    reviews, spam = web.fresh("reviews"), web.fresh("spam_filter")
    return {
        "reviews": {"file": "reviews.py", "id": "happy", "items": reviews.REVIEWS, "expected": getattr(reviews, "EXPECTED", None),
                    "question": reviews.QUESTION, "threshold": reviews.THRESHOLD},
        "spam": {"file": "spam_filter.py", "id": "spam", "items": spam.MESSAGES, "expected": spam.EXPECTED,
                 "question": spam.QUESTION, "threshold": spam.THRESHOLD},
    }


if __name__ == "__main__":
    web.serve(HERE / "sim.html", "Level 1 · Yes or No?", level, port=8001,
              files={"reviews.py": HERE / "reviews.py", "spam_filter.py": HERE / "spam_filter.py"})
