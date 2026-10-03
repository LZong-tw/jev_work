# Decision AI Workshop · Level 1 → 5

Build software that **decides**, with the Jev Decision API.
Hands-on, in Python. No AI experience needed. Basic Python is enough.

## Agenda · 11:00 – 15:00

| Time | Block | What you build |
|---|---|---|
| 11:00 – 11:20 | Welcome · What is decision AI? · Setup | `python jev.py` says "You are ready." |
| 11:20 – 11:45 | **Level 1** · Yes or No? | Review checker, LINE spam filter |
| 11:45 – 12:20 | **Level 2** · Pick one, and rate it | Tea shop inbox router |
| 12:20 – 12:30 | Quiz round 1 · Q&A | |
| 12:30 – 13:30 | 🍱 **Lunch break** | |
| 13:30 – 13:55 | **Level 3** · Guard the AI agent | Safety gate for tool calls |
| 13:55 – 14:20 | **Level 4** · Decisions in a loop | Bubble tea shop manager |
| 14:20 – 14:50 | **Level 5** · Jev runs the traffic lights | 3 junctions, a 200-tick stream, history + lessons + leaderboard |
| 14:50 – 15:00 | 🏆 Leaderboard · Final quiz · Wrap-up | |

3 hours of content + 1 hour lunch.

## Setup (5 minutes)

You need **Python 3.8+**. Nothing to install with pip.

```bash
git clone <this repo>
cd jev/workshop
cp .env.example .env        # Windows: copy .env.example .env
```

Open `.env` and paste the two values from your **key card**:

```
JEV_BASE_URL=https://...the URL on your card...
JEV_API_KEY=jvp_...your key...
```

Check:

```bash
python jev.py
```

You should see `You are ready.` 🎉

> **No internet?** Set `JEV_MOCK=1` in `.env`. You get fake answers (keyword matching) so you can still
> run and edit all the code. Switch back to `JEV_MOCK=0` for real answers.

## The whole API on one card

```python
from jev import decide, noul, choice, score

result = decide(
    state="any text, or a JSON object",
    questions={
        "is_spam": noul("Is this spam?"),                                   # yes/no  -> 0.0..1.0
        "team":    choice("Who handles it?", {"sales": "...", "help": "..."}), # one label
        "urgency": score("How urgent?", ["low", "medium", "high"]),         # 0..2, can be 1.4
    },
)
result["answers"]["is_spam"]["noul"]       # 0.03
result["answers"]["team"]["choice"]        # "help"
result["answers"]["team"]["confidence"]    # 0.94
result["answers"]["urgency"]["score"]      # 1.7
```

## Levels

| | Folder | Main idea |
|---|---|---|
| 1 | [`level1-yes-or-no`](level1-yes-or-no/) | `noul` + threshold |
| 2 | [`level2-pick-and-rate`](level2-pick-and-rate/) | `choice`, `score`, confidence → ask a human |
| 3 | [`level3-guardrail`](level3-guardrail/) | many questions, one call · Jev judges, code rules |
| 4 | [`level4-tea-shop`](level4-tea-shop/) | loop · state machine · points · baseline |
| 5 | [`level5-junction`](level5-junction/) | Jev as a state machine for 3 traffic lights · a 200-tick stream · history vs lessons · leaderboard |

**Play every level in your browser** 🕹️: each folder has a `server.py` with a little 16-bit game for that
task, built from **your** code. Every challenge has a **score** (a ring, stars, your best so far), so you see
at once whether your change made it better. Write the code in your editor or right in the page (a code
editor with highlighting; it saves the file, only if it compiles). The **Jev editor** next to it shows the
exact JSON of anything you click: send your own, or write Jev's answer yourself and see what happens (free).

```bash
python level1-yes-or-no/server.py       # :8001  spam filter: x/6          python level3-guardrail/server.py  # :8003  the gate x/5, the attack wave x/10
python level2-pick-and-rate/server.py   # :8002  inbox x/7, portfolio: x4?  python level4-tea-shop/server.py   # :8004  points / the best possible day
python level5-junction/city_server.py   # :8000  the 3D city, live: points per tick
python sandbox/server.py                # :8010  the Jev Sandbox: any request, every answer as a widget
```

**The Jev Sandbox** (`sandbox/`): build any request with a form (state as text or JSON, any number of
yes/no, choice and score questions) or paste the JSON, and see the answers as widgets: a gauge, bars, a
scale. "Ask 5×" shows how much the answers move. Templates include YOUR questions from Levels 1-4.

Each folder has a `README.md` (read it first), the code, `TRY IT` tasks, a quick quiz, and
**two example solutions** (`solution_a.py`, `solution_b.py`): two different ideas for the same problem.
Try it yourself first!

## Real results

How good is each solution with the real Jev? We measured all of them, 3 times, also on new data
they never saw: **[results/RESULTS.md](results/RESULTS.md)** (tables + charts, about US$0.27 to repeat).

## Errors you may see

| Error | Meaning | Fix |
|---|---|---|
| `[401] Invalid or revoked API key.` | key is wrong | check `.env`, no spaces |
| `[402] ... (insufficient_credits)` | your key's budget is used up | ask the instructor |
| `[429] Too many requests` | too fast | the client waits and retries; slow down loops |
| `[400] ...` | your JSON is wrong | read the message, check criteria format |
| `Cannot reach ...` | network | check Wi-Fi, or use `JEV_MOCK=1` |
