# Level 4 · Decisions in a loop: run the tea shop ⏱ 25 min

**You learn:** the decision loop, state machines, points (reward), and comparing with a baseline.

## From one decision to many

```
        ┌──────────────────────────────────────────────┐
        ▼                                              │
   STATE ──► Jev decides ──► code applies the action ──► NEW STATE + points
```

Every round (30 minutes of shop time), Jev picks **one** action:

| Action | Effect |
|---|---|
| `make_drinks` | serve up to 5 customers (uses pearls, tea, energy) |
| `cook_pearls` | +15 pearls, nobody served this round |
| `brew_tea` | +15 tea, nobody served this round |
| `rest` | +4 staff energy, nobody served this round |

**Points:** +2 per drink served, −3 per customer who leaves angry.

## The state machine

The shop has a **mode**. Code computes it from the state, every round:

```
          queue >= 8                      pearls = 0 or tea = 0
  OPEN ─────────────► RUSH       any ─────────────────────────► SOLD_OUT
   ▲                    │        any ─── energy <= 2 ─────────► TIRED
   └──── queue < 8 ─────┘        (back to OPEN when fixed)
```

Jev never breaks the rules of the shop. It only chooses what to do **inside** the rules.

## Watch it in your browser 🖥️

```bash
python level4-tea-shop/server.py           # opens http://localhost:8004/
```

The shop day, round by round: the customers in the queue (their faces get impatient), the pearls, tea
and energy, the **state machine** moving before every decision, the points per round, and a log. Pick
the manager: Jev, the simple rules, or **you** (click the action). Same seed = same customers: the
scoreboard compares the managers. It plays `shop.py`: edit it, then start a new day. Every round's JSON
(what Jev reads) is in the **Jev editor**: change it and Send, or write the answer yourself and Apply,
then play the round. **Your score**: your points out of the best possible day for that seed
(`best_possible.py` tries every plan: 72 on seed 1; the simple rules get 47). Edit `shop.py` in the page
(describe(), QUESTIONS): a new day starts with your code.

## Do it

1. `python level4-tea-shop/shop.py --rules` (simple if/else manager)
2. `python level4-tea-shop/shop.py` (Jev manager)
3. Try seeds 1, 2, 3. Fill in the table:

| Seed | Rules | Jev | Jev + your fixes | Best possible |
|---|---|---|---|---|
| 1 | 47 | | | 72 |
| 2 | 30 | | | 60 |
| 3 | 41 | | | 51 |

Hint: customers wait up to 2 rounds before they leave. What can you do in those 2 rounds?

4. Make Jev better. Three ideas, try them one by one:
   - **The question.** It says "best action for this round". Jev takes it literally and serves
     until the pearls run out. Ask for the most points by the **end of the day**.
   - **The state.** Improve `describe()`: tell Jev when the lunch rush comes; "restock when it is quiet".
   - **Guard rules.** Some decisions are easy and must never go wrong (pearls < 5 → cook). Keep them in code.
5. Bonus: add a `call_friend` action.

## Two example solutions

| File | Idea |
|---|---|
| `solution_a.py` | **Better words only**: ask for the most points by the END of the day, and add the rush advice to `describe()`. |
| `solution_b.py` | **A + guard rules in code**: easy decisions (pearls < 5 → cook) are made by code; Jev chooses only between sensible actions. |
| `best_possible.py` | How we know the best score: try every plan (with memoization, under 1 second). |

Real results (jev-latest), 10 different days × 3 repeats:

| Manager | Mean points per day | Days 1 / 2 / 3 |
|---|---|---|
| Rules (if/else) | 41.0 | 47 / 30 / 41 |
| Starter Jev | −17.2 | 7 / −30 / −14 |
| A: better words | 41.6 | 51 / 45 / 36 |
| B: A + guard rules | **54.7** | **66 / 60 / 51** |
| Best possible | 56.1 | 72 / 60 / 51 |

The starter loses to plain if/else: the question says "this round" and Jev answers exactly that.
B reaches 97% of the best possible. Chart: [results, Level 4](../results/RESULTS.md#level-4--tea-shop-decisions-in-a-loop).

## What to notice

- The **baseline** (`--rules`) is important. Without it you do not know if Jev is good.
- Better **state description** → better decisions. You are the teacher.
- Jev answers **exactly the question you ask**. "This round" and "today" give different shops.
- Jev also predicts: `pearls_soon_empty`. Predictions help you plan ahead.

## Quick quiz

1. In this loop, what is the "state", the "action" and the "reward"?
2. Who changes the mode from OPEN to RUSH: Jev or the code?
3. Jev scores 40, the rules score 47. Is Jev useless? What would you try next?
4. Why does `cook_pearls` give 0 points this round, but can still be the best action?
