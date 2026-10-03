"""
Level 2 - Solution B: let Jev say "none of these".

You cannot think of every box. So add one more option: "other".
Code sends "other" AND unsure answers to a human. New kinds of messages are safe.

Run:  python level2-pick-and-rate/solution_b.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev import choice, decide  # noqa: E402
from inbox import INBOX, MIN_CONFIDENCE, QUESTIONS  # noqa: E402

BOXES = dict(QUESTIONS["box"]["criteria"])  # the five boxes from inbox.py
BOXES["other"] = "none of the boxes above fits this message"
MY_QUESTIONS = {
    "box": choice("Which team should handle this message?", BOXES),
    "urgency": QUESTIONS["urgency"],
}


def sort_message(message):
    """Returns (box, urgency, confidence). box is "HUMAN" for "other" or when Jev is not sure."""
    a = decide(state=message, questions=MY_QUESTIONS)["answers"]
    box = a["box"]["choice"]
    if box == "other" or a["box"]["confidence"] < MIN_CONFIDENCE:
        box = "HUMAN"
    return box, a["urgency"]["score"], a["box"]["confidence"]


def main():
    rows = [(*sort_message(m), m) for m in INBOX]
    print("Most urgent first:")
    for box, urgency, conf, message in sorted(rows, key=lambda r: -r[1]):
        print(f"{urgency:>4.1f}  {box:<10} {conf:.2f}  {message[:60]}")


if __name__ == "__main__":
    main()
