# Level 2 · Pick one, and rate it ⏱ 35 min

**You learn:** `choice` and `score` questions, confidence, and when to ask a human.

## Three question types

| Type | Use it for | You give | You get |
|---|---|---|---|
| `noul` | yes / no | instructions | `noul` (0–1) |
| `choice` | pick ONE label | instructions + `criteria` **object** `{label: meaning}` | `choice`, `confidence`, `probabilities` |
| `score` | rate on a scale | instructions + `criteria` **list** low → high (2–10 levels) | `score` (can be 2.4), `confidence`, `probabilities` |

```python
"box": choice("Which team should handle this message?", {
    "order":     "wants to buy drinks or make a group order",
    "complaint": "unhappy customer, problem with an order, wants a refund",
    "question":  "asks about the shop, menu, opening hours",
}),
"urgency": score("How fast must the shop reply?",
    ["no reply needed", "this week", "today", "within 1 hour"]),
```

```json
"box":     { "choice": "complaint", "confidence": 0.97,
             "probabilities": { "order": 0.01, "complaint": 0.97, "question": 0.02 } },
"urgency": { "score": 2.8, "confidence": 0.81 }
```

**Many questions → still ONE call.** Same price per input token, same speed.

## Good labels = good answers

- Labels are short, `snake_case`, stable. Your code uses them (`if box == "complaint"`).
- The **description** after each label is where you explain. Be concrete.
- Labels should not overlap. If two labels both fit, confidence goes down.

## Confidence: know when you don't know

```python
if conf < MIN_CONFIDENCE:
    box = "HUMAN?"   # do not guess, ask a person
```

Low confidence is not a failure. It is **useful information**:
the message is unusual, or your labels are missing something.

## Watch it in your browser 🖥️

```bash
python level2-pick-and-rate/server.py      # opens http://localhost:8002/
```

The inbox sorted into a column per box, with the urgency on every card and a **HUMAN?** column for the
messages Jev is not sure about: move the confidence slider and watch them move. Click a message to see
how sure Jev was about every box. It reads `inbox.py`: add a box there and reload. Click any item: the **Jev editor** shows the exact JSON Jev gets for it. Change it and **Send to Jev**, or
change Jev's answer and **Apply** (no call, no cost) to see what the page does with it. "What this page
expects from Jev" lists the questions and answers it needs; a payload that does not fit gets a clear error.

## Do it

1. `python level2-pick-and-rate/inbox.py`
2. Do the TRY IT tasks. (The umbrella message has no good box yet!)
3. Compare with the two solutions below when you are done.

## Challenge: the portfolio sorter 📈

`portfolio.py` has five (made-up) companies. Jev puts each one in a bucket: how much will its revenue and
earnings grow in the next 10 years? **You write the code**:

1. **TODO 1:** say what each bucket means (`rocket`, `grower`, `steady`, `shrinking`). Use numbers.
2. **TODO 2:** the question. Growth of what, over how long?
3. **TODO 3:** `describe(stock)`: what Jev reads about a company. The starter sends only the name, so Jev
   is never sure and everything goes to **HUMAN?**. Give it the facts.
4. **TODO 4:** `invest(results, budget)`: share out NT$1,000,000. Then **fast-forward 10 years**
   (`market.py` has what really happened: no peeking!). The starter shares it out equally: x2.26. Use the
   buckets and Jev's confidence: can you reach **x4**?

Two scores: your buckets against an expert's (x/5), and your money after 10 years. The inbox tab is
scored too (x/7): add the missing box for the umbrella message.

```bash
python level2-pick-and-rate/portfolio.py
python level2-pick-and-rate/server.py      # the "Portfolio" tab: add as many companies as you like
```

In the browser, every company you add goes through **your** `describe()` and **your** question, one Jev call
each, into a column per bucket (low confidence: HUMAN?). Click a company: the Jev editor shows exactly what
your code sent. Not investment advice: Jev only knows what you write.

## Two example solutions

| File | Idea | Real result: 21 messages (7 workshop + 14 new) |
|---|---|---|
| (starter) `inbox.py` | five boxes, confidence < 0.70 → human | 16 right, 1 to a human, **4 in the wrong box** |
| `solution_a.py` | **Add the missing box** (`lost_item`), sort by urgency | 19 right, **2 in the wrong box** |
| `solution_b.py` | **Let Jev say "none of these"**: add `other`, and send it to a human | 16 right, 5 to a human, **0 in the wrong box** |

The big lesson: Jev was *confident* that a lost umbrella is a "question". A missing box is a
**silent** mistake, and the confidence check does not catch it. A gets more right; B never
routes a message to the wrong team. Which one is better depends on what a mistake costs.
Full numbers and chart: [results, Level 2](../results/RESULTS.md#level-2--inbox-sorter-choice--score--confidence).

## Quick quiz

1. `choice` criteria is an object `{}`. `score` criteria is a list `[]`. Why is the score one a list?
2. A `score` with 4 levels returns `2.6`. Between which two levels is it?
3. Confidence is 0.41 for a message. Give two possible reasons.
4. You need "box" and "urgency" for 1,000 messages. How many API calls?
