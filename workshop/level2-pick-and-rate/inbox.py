"""
Level 2 - Pick one, and rate it.

The "Happy Pearl" tea shop gets many messages every day. We want software that:
  1. puts each message in the right box   (choice)
  2. says how urgent it is                 (score)
  3. asks a human when Jev is not sure     (confidence)

All three answers come from ONE call.

Run:  python level2-pick-and-rate/inbox.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev import choice, decide, score  # noqa: E402

INBOX = [
    "Hi, can I order 20 cups of oolong milk tea for our office party on Friday at 3pm? Xinyi district.",
    "My foodpanda order #8812 came with no pearls and the tea was spilled. I want a refund NOW.",
    "Are you open during the typhoon day tomorrow?",
    "Hello, I am a student at NTU. Are you hiring part-time staff on weekends?",
    "Dear user, your account will be closed. Verify here: http://hppy-pearl-login.xyz",
    "Do you have a sugar-free option? My father has diabetes.",
    "I think I left my umbrella at your Da'an shop yesterday, a blue one.",
]

# The box a person would choose (your score in the browser). The umbrella has no box yet (TRY IT 1):
# until you add "lost_item", sending it to a HUMAN counts as right.
EXPECTED = ["order", "complaint", "question", "job", "spam", "question", "lost_item"]

QUESTIONS = {
    "box": choice(
        "Which team should handle this message?",
        {
            "order": "wants to buy drinks or make a group order",
            "complaint": "unhappy customer, problem with an order, wants a refund",
            "question": "asks about the shop, menu, opening hours, ingredients",
            "job": "wants to work at the shop",
            "spam": "scam, phishing link, advertising",
        },
    ),
    "urgency": score(
        "How fast must the shop reply?",
        ["no reply needed", "this week", "today", "within 1 hour"],
    ),
}

# If Jev's confidence is below this, a human should check.
MIN_CONFIDENCE = 0.70


def main():
    print(f"{'BOX':<11} {'CONF':>5} {'URGENT':>6}  MESSAGE")
    for msg in INBOX:
        a = decide(state=msg, questions=QUESTIONS)["answers"]
        box, conf, urgency = a["box"]["choice"], a["box"]["confidence"], a["urgency"]["score"]

        if conf < MIN_CONFIDENCE:
            box = "HUMAN?"  # not sure -> do not guess, ask a person

        print(f"{box:<11} {conf:>5.2f} {urgency:>6.1f}  {msg[:60]}")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# TRY IT
# 1. The umbrella message has no good box. Add "lost_item" to the criteria.
#    What happens to its confidence?
# 2. Sort the inbox: most urgent first. (Hint: sorted(..., key=...))
# 3. Print a["box"]["probabilities"] for the typhoon message. Is Jev torn
#    between two boxes? That is useful information too!
# 4. Change the score levels to 5 levels. Does the score change a lot?
# ---------------------------------------------------------------------------
