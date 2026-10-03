# Jev · Decision API proxy + workshop

Two projects in one repo:

| Folder | What it is |
|---|---|
| [`proxy/`](proxy/) | **Jev proxy.** Share your Jev Decision API access without sharing your key. Same endpoints, same JSON. You hand out `jvp_` keys with limits and budgets. Node 18+, zero dependencies. |
| [`workshop/`](workshop/) | **Decision AI workshop, Level 1 → 5.** 3 hours hands-on (11:00 – 15:00 with a 1 h lunch). Python, no pip install. Ends with Jev running three Taipei traffic lights as one smart state machine through a 200-tick stream (dynamic speeds, jams that spread, limited vision, score and energy), reading its own history and a coach's hindsight lessons. |
| [`slides/`](slides/) | **The workshop slides** as PDF (`jev-workshop-slides.pdf`) and the HTML they are built from. |

Every level has two example solutions, measured with the real API: **[workshop/results/RESULTS.md](workshop/results/RESULTS.md)**.
Level 5 replays as a 3D city in the browser: `workshop/level5-junction/viewer3d.html`.

```
 participants (Python, curl, browser)
        │  Authorization: Bearer jvp_...
        ▼
 ┌──────────────┐   Authorization: Bearer <your TypeSafe key> (secret)
 │  jev-proxy   │ ─────────────────────────────────────────────►  Jev API
 │ limits, logs │ ◄─────────────────────────────────────────────  same JSON back
 └──────────────┘
```

## 5-minute start

```bash
# 1. proxy
cd proxy
cp .env.example .env                       # add your JEV_API_KEY
npm run keys -- --count 3 --prefix demo    # prints keys to keys-handout.csv
npm start                                  # http://localhost:8787

# 2. workshop
cd ../workshop
cp .env.example .env                       # JEV_BASE_URL=http://localhost:8787, JEV_API_KEY=jvp_...
python jev.py                              # "You are ready."
python level5-junction/run.py --runs 3
```

No Jev key yet? `npm run mock` (proxy) or `JEV_MOCK=1` (workshop) gives fake answers in the real format.

## Tests

```bash
./test.sh
```

Everything is tested **without a Jev key**: Jev is replaced by mocks and fake servers.

| Suite | What it checks |
|---|---|
| `proxy/test/` (Node, 33 tests) | key swap, limits, budgets across restarts, expiry, body limit, timeouts, CORS, admin, key generator, private logs, mock upstream |
| `workshop/tests/` (Python, 96 tests) | the client (HTTP, retries, errors, mock), every level's script and logic with scripted Jev answers, the Level 4 optimum, the Level 5 city (speeds, turns, spillback, ambulances, lights, points), state as map/array, coach, memory, officers, CLI |
| Learning experiment | a fake Jev that only follows the coach's LESSONS in its prompt goes from random play (≈ −240 to −690) to better than the fixed timer on the exam: the coach + memory work |
| Integration | Python client → real Node proxy → fake Jev; all levels through the proxy; the replay viewer in headless Chromium; every slide fits (no cut-off code) |

Works on Python 3.8 – 3.13 and Node 18+. CI: `.github/workflows/test.yml`.

## Rebuild the slides

```bash
cd slides && node build.mjs     # needs Playwright + Chromium
```
