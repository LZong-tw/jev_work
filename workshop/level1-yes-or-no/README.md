# Level 1 · Yes or No? ⏱ 25 min

**You learn:** the three parts of every Jev call, and the `noul` question.

## The idea

A chatbot writes long text. You must read it, or parse it.
A **decision API** gives you one clean answer your code can use right away.

```
STATE      "Waited 40 minutes. Tea was cold."
QUESTION   noul: "Is the customer happy?"
ANSWER     { "noul": 0.04 }      ← 4% chance of YES
```

`noul` = a calibrated **yes/no**. The number is the probability of YES (0.0 to 1.0).
"Calibrated" means: when Jev says 0.8, it is right about 8 times out of 10.

## The JSON (this is all of it)

```json
POST /v1/systemone
{
  "model": "jev-latest",
  "state": "Waited 40 minutes at the Ximending shop. Tea was cold.",
  "questions": {
    "happy": { "type": "noul", "instructions": "Is the customer happy?" }
  }
}
```

```json
{
  "model": "jev-1.13.0",
  "answers": { "happy": { "type": "noul", "noul": 0.03 } },
  "usage": { "input_tokens": 290, "output_tokens": 20 }
}
```

(Real answer from the API. Price: US$42 per billion input tokens, so this call cost US$0.000012.
`jev.py` sends `"model": "jev-latest"` for you.)

`"happy"` is **your** name for the question. You read the answer with the same name.

## Watch it in your browser 🖥️

```bash
python level1-yes-or-no/server.py          # opens http://localhost:8001/
```

The reviews and the spam messages as cards, every answer as a dot on the line from 0 to 1, and the
threshold as a slider: move it and watch YES/NO change, with no new call. **Your score**: how many of the
6 your question gets right (`EXPECTED`), with lives, stars and your best so far. Get 6/6! It reads
`reviews.py` and `spam_filter.py`: edit them and reload the page. Click any item: the **Jev editor** shows the exact JSON Jev gets for it. Change it and **Send to Jev**, or
change Jev's answer and **Apply** (no call, no cost) to see what the page does with it. "What this page
expects from Jev" lists the questions and answers it needs; a payload that does not fit gets a clear error.

## Do it

1. `python level1-yes-or-no/reviews.py`
2. Do the 4 TRY IT tasks at the bottom of the file.
3. **Challenge:** open `spam_filter.py`, fill in the TODOs. Get 6/6.

## Key point: the threshold is YOUR decision

Jev gives a probability. **You** choose where to draw the line.

| Threshold | Effect |
|---|---|
| 0.3 | Catches almost all spam. Some good messages get blocked. |
| 0.5 | Balanced. |
| 0.9 | Only blocks when very sure. Some spam gets through. |

Ask: *"What is worse here: a false alarm, or a miss?"*

## Two example solutions

Try it yourself first! Then compare.

| File | Idea | Real result (jev-latest, 3 repeats) |
|---|---|---|
| `solution_a.py` | **One clear question**, with `yes=` and `no=` criteria: say what counts as spam and what does not. | 6/6, and 20/20 on new messages |
| `solution_b.py` | **Three small questions** in one call (prize? password? stranger's link?). Code says spam if any is YES, and tells you **why**. | 6/6, and 20/20 (one false alarm in one of 3 runs) |

Surprise from the real test: spam is easy for Jev. Even the naive *"Is this message spam?"* was always right.
So the real decision is yours: **the threshold**. Full numbers: [results, Level 1](../results/RESULTS.md#level-1--spam-filter-noul).

## Quick quiz

1. In `{"noul": 0.92}`, what does 0.92 mean?
2. Who decides the threshold: Jev or your code?
3. A hospital uses Jev to flag "Is this patient report urgent?". High or low threshold? Why?
4. Name the three parts of a `/v1/systemone` request.
