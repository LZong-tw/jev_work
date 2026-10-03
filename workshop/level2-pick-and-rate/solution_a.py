"""
Level 2 - Solution A: add the missing box.

The umbrella message did not fit any box, so Jev was unsure. Give it a box: lost_item.
Then sort the inbox, most urgent first. Unsure answers still go to a human.

Run:  python level2-pick-and-rate/solution_a.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev import choice, decide  # noqa: E402
from inbox import INBOX, MIN_CONFIDENCE, QUESTIONS  # noqa: E402

BOXES = {
    "order": "wants to buy drinks or make a group order",
    "complaint": "unhappy customer, problem with an order, wants a refund",
    "question": "asks about the shop, menu, opening hours, ingredients",
    "job": "wants to work at the shop",
    "lost_item": "customer forgot or lost something at the shop",
    "spam": "scam, phishing link, advertising",
}
MY_QUESTIONS = {
    "box": choice("Which team should handle this message?", BOXES),
    "urgency": QUESTIONS["urgency"],
}


def sort_message(message):
    """Returns (box, urgency, confidence). box is "HUMAN" when Jev is not sure."""
    a = decide(state=message, questions=MY_QUESTIONS)["answers"]
    box = a["box"]["choice"] if a["box"]["confidence"] >= MIN_CONFIDENCE else "HUMAN"
    return box, a["urgency"]["score"], a["box"]["confidence"]


def main():
    rows = [(*sort_message(m), m) for m in INBOX]
    print("Most urgent first:")
    for box, urgency, conf, message in sorted(rows, key=lambda r: -r[1]):
        print(f"{urgency:>4.1f}  {box:<10} {conf:.2f}  {message[:60]}")


if __name__ == "__main__":
    main()
