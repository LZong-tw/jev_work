# Level 5 · Jev runs the traffic lights 🚦 ⏱ 30 min

**You learn:** Jev as a smart state machine, decisions in a long stream, what to put in the context
(raw history or digested lessons), limited vision, the cost of context (tokens), and fair evaluation.

## Start simple: one junction, one officer

Before the three-junction city, try `one_junction.py`. Four roads (top, right, bottom, left), each
**20 blocks x 4 lanes** `[left-turn, straight, straight, right-turn]`; a number = cars on that block.
Every tick every car moves 1 block; on red they add up at the stop line (`[3,0,0,0,1]` -> `[0,3,0,0,1]`
-> ... -> 4 waiting); on green 1 car per lane crosses. So the officer can see the cars coming.

The officer sets every road: `"left": {"light": [1,0,0,0], "people": 0}` = only the left-turn lane is
green. Nothing stops a bad plan: conflicting moves crash (**-20**), a car through walking people **-50**.
Every car stuck at a stop line costs **-1** per tick (**-2** in the rush hours: people are late for work);
in the rush hours 5 people cross per tick (4 in the rain), otherwise 3 (2).
One tick is 10 minutes; a run is 3 days (432 ticks) from 00:00, scored per day. Cars drive on the right; morning and evening peaks, quiet nights, rain (2 people cross per tick, not 3).

**The traffic light** runs a fixed cycle of safe phases (top/bottom straight -> top/bottom left turns
-> right/left straight -> right/left left turns -> people walk). Jev only decides the **timing**: every
tick one yes/no question, "switch to the next phase now?", with the cars waiting in the green phase,
in the next phase and in the others. Min green 1 tick, max 6 (in code), so nothing can crash.

```bash
python level5-junction/one_junction.py --officer fixed  --ticks 200   # every phase 3 ticks
python level5-junction/one_junction.py --officer timing --ticks 200   # simple timing rules
python level5-junction/one_junction.py --officer jev    --ticks 200 --show 50   # Jev decides when to switch
python level5-junction/one_junction.py --officer random               # every road on its own: crashes
```

Then open `level5-junction/one_junction.html`: cars glide block by block, turn through the junction,
people walk across, crashes flash.

## Four Crossings: a rich city to control

Open `level5-junction/city.html` in a browser (a 3D city by default; **2D map** switches): 4 signalised crossings with zebras, cars, taxis, buses,
scooters and bikes (green bike lanes), and people walking on the sidewalks. Cars drive on the right.
Each crossing has 5 phases: **A** N–S straight + right, **B** N–S left, **C** E–W straight + right,
**D** E–W left, **W** everyone walks (all four zebras). Per crossing pick *Fixed timer*, *Smart* or
*Manual* (click A–W). Yellow, all-red and "turn green only when the crossing is empty" are in code,
so nothing can crash. Rush hours 07:00–09:30 and 17:00–19:30, quiet nights.

The city moves in **ticks** (`1 tick =` 4 s, 2 s, 1 s, 500 ms or 250 ms, in the top bar). At the start of
a tick, per lane, the first vehicle at the stop line goes if its light is green, and it is across the
crossing at the end of that tick: **a vehicle crosses in exactly 1 tick**, so the crossings are empty
whenever a tick ends. People too: on **W**, the people waiting at a zebra go when a tick starts and are
across at its end, so the zebras are empty whenever a tick ends. 1 tick = 3 clock minutes.

**Rush hours** (the `WAVES` table in `city.html`): for one clock hour, one side of the map, or the people,
get much busier. 09:00 cars from left to right · 10:00 bottom to top · 11:00 left to right · 12:00 a huge
crowd walks (lunch) · 13:00 right to left · 14:00 top to bottom · 15:00 school is out · 16:00 left to right ·
17:00 home time (to the left and the bottom) · 18:00 a crowd walks · 19:00 bottom to top. The top bar shows
the one now. Every crossing shows its id (**#0** top left, **#1** top right, **#2** bottom left, **#3** bottom
right): the keys of `decide()`'s answer. Lit lanes and turns show what each crossing's lights let go.

**Live with Jev:** the city runs, but its traffic lights do nothing until **your function** answers.
Write it in `level5-junction/my_jev.py`:

```python
async def decide(history, current):          # history: earlier states, oldest first; current: the state now
    ...                                       # call Jev
    return {0: "A", 1: "C", 2: "W", 3: "B"}   # the new lights: one phase per crossing
```

`current` is small: the tick, the clock, and per crossing its lights and who waits.

```python
{"tick": 3, "clock": "09:09", "crossings": [
    {"id": 0, "name": "Fuxing × Zhongxiao", "lights": "A", "ticks": 2,         # None = all red; on for 2 ticks
     "cars": {"north": {"left": 0, "straight_right": 2, "bikes": 0}, "east": {...}, "south": {...}, "west": {...}},
     "people": {"north": 4, "east": 0, "south": 0, "west": 2}},                 # waiting at each zebra
    ...]}
```

Then `python level5-junction/city_server.py` prints a URL (and opens it): the 3D city, live.
**One tick = one `decide()` call**: before every tick the server calls `decide()`, the lights become
exactly what it returned (all red before the first answer), then the tick runs; nothing else changes
them. `--tick 1` or `--tick 0.5` makes a tick 1 s or 500 ms (default 2 s). The city runs a whole tick at
once and the screen plays it over the tick length (smooth, step by step), so `decide()` for the next
tick already thinks while this one plays: no pause as long as Jev answers within a tick. A late answer
makes the city glide to a stop and wait; a tick is never skipped or cut short. A live panel lists every
decision (the newest on top, a changed light highlighted, and its points) and shows Jev's calls, input
tokens, cost, response time and charts. **The live score**: every tick, +1 for each vehicle or person that
got across a crossing, −0.2 for each one still waiting. "Per tick" is your average, next to your best.
Edit `my_jev.py` while it runs: the next call uses the new code. Set
`JEV_BASE_URL=https://api.typesafe.ai` and `JEV_API_KEY` in `workshop/.env` (or `JEV_MOCK=1`).

Your own controller (for example Jev) reads the stats and sets a **schedule** per crossing, through
the page's JavaScript API:

```js
city.state()                 // now: clock, totals, and per crossing: phase, stage, demand per phase,
                             // per approach (north/east/south/west) and lane: queue, approaching,
                             // max wait, vehicle types, turns; people waiting per zebra
city.history(8)              // the last 8 x 15 minutes, per crossing: vehicles per approach and turn,
                             // avg wait, max queue, people crossed + avg wait, green seconds per phase
city.setSchedule(0, [{ phase: "A", seconds: 25 }, { phase: "B", seconds: 6 },
                     { phase: "C", seconds: 20 }, { phase: "W", seconds: 10 }])   // one cycle; D skipped
city.setSchedule(1, { "00:00": [...], "07:00": [...], "09:30": [...] })        // a day plan by the clock
city.getSchedule(1)          // the plan running now
city.onSecond(state => { ... })   // called once per simulated second
```

Phases left out of a schedule are skipped; seconds are 3–180 per phase. Yellow, all-red and the
empty-crossing check always run in between, so a schedule cannot cause a crash.

## The city

Three junctions on Zhongxiao E. Rd, Da'an District, Taipei:

```
              Fuxing S. Rd       Dunhua S. Rd       Guangfu S. Rd
                   |                  |                  |
 Zhongxiao E. Rd --+------------------+------------------+---
                   |                  |                  |
```

**One run = one stream of 200 ticks.** No days, no restart: Jev keeps going and can learn from
everything that happened so far. The traffic comes in **waves** that repeat every 40 ticks:
side streets busy, then Zhongxiao busy, then both normal, and again. Sometimes a rain shower
(40 ticks) makes everybody slower. (`--ticks 100` for a shorter stream; other maps: `--map single`,
`corridor`, `grid`.)

**Roads.** One lane per direction, 10 cells long. A full road blocks the junction before it,
so a jam can spread along Zhongxiao (**spillback**).

**Vehicles have their own speed** (cells per tick). Every tick each vehicle:

1. speeds up (scooters fast, buses slowly),
2. brakes for the vehicle ahead and for red lights,
3. sometimes slows down for no reason (more often in rain),
4. moves. Turning vehicles slow down at the junction.

|  | speed up | top speed | points when it crosses |
|---|---|---|---|
| scooter `s` | +2 | 3 | +1 |
| car `c` | +1 | 3 | +1 |
| bus `B` | +1 | 2 | +3 (many people inside) |
| ambulance `A` | +2 | 4 | +5, and everybody makes way for it |

Vehicles go straight (60%), turn right (25%) or turn left (15%). People arrive at every corner.

## The decision, every tick, for every junction

| Action | Meaning |
|---|---|
| `north_south` | green for Fuxing / Dunhua / Guangfu S. Rd |
| `east_west` | green for Zhongxiao E. Rd |
| `walk` | all vehicles stop, every waiting person crosses |

**The light is a state machine.** Changing it costs one **YELLOW** tick where nothing crosses.
Then the new light stays at least 1 tick (**minimum green**); during that locked tick nobody is asked.

```
 NS ──switch──► YELLOW ──► EW (locked 1 tick) ──► EW (you choose again)
```

**Limited vision.** At each junction you see only **6 cells (about 6 cars) down each road** from the
stop line. Cars further away and the queue at the city edge are out of sight. An ambulance is the
exception: you hear its siren. (`VISION` in `city.py`; the simple rules have the same eyes.)

**Points per junction per tick**

| | |
|---|---|
| vehicle crosses | +1 / +3 bus / +5 ambulance |
| each stopped vehicle (also cars waiting to enter the city) | −0.05 |
| each waiting pedestrian | −0.1 |
| vehicle stopped more than 10 ticks (angry honking) | −1 |
| **ambulance stopped at a red light** | **−10** |

**Energy per junction per tick:** 1 for every idling (stopped) vehicle. Fuel burned while waiting.
The goal: the **highest score** with the **least energy**.

**Two safety rules (in code).** Jev is not asked when (1) an ambulance is waiting: green for its road,
or (2) people have just crossed: walk lasts one tick, then green for the busier road. Easy rules that
must never fail belong in code (Level 3 and 4 again). See what happens without them: `--no-safety`.

## What Jev reads: the whole story so far

**One call per tick** with one `choice` question per junction. The state is the whole story:

```
TRAFFIC CONTROL on Zhongxiao E. Rd, junctions from west to east: FZ = Fuxing S. Rd x Zhongxiao E. Rd, ...
Tick 57 of 200. Weather: rain. Score so far: 104.2. Energy used so far: 812.
GOAL / POINTS / ENERGY / LIGHTS: the rules above, in a few lines
Last 20 ticks: +18.3 points, 260 energy. The 20 before: +9.1 points, 301 energy.
HISTORY, one line per tick:
t1 | FZ NS0 N0/0 S1/0 E2/0 W0/0 p0 >NS +0.0 e0 | DZ ... | GZ ... | tick +0.4 e2 | score 0.4 energy 2
...
t56 | FZ EW3 N2/2 S1/1 E0/0 W3/1 p5 >EW +0.8 e3 | ...
NOW (tick 57):
  FZ: EW3 N2/2 S1/1 E0/0 W3/1 p5 | free space after the junction NS=6 EW=4 | longest wait 7 ticks |
      costing now: pedestrians -0.5, stopped vehicles -0.15 points per tick
```

`EW3` = east-west green for 3 ticks, `N2/2` = 2 vehicles from the north, 2 of them stopped,
`p5` = 5 people waiting, `>EW` = the decision, `+0.8` = the points of that junction in that tick,
`e3` = its energy. Jev itself never changes between calls: the history in the state is its memory.

See the state as data: `python level5-junction/show_state.py --format map` (or `array`, `text`).
Send Jev the story as JSON or numbers: `run.py --state-format map` (or `array`).

## Can Jev learn from its own history?

That is the experiment of this level. In theory: every tick Jev sees more of what worked.
In practice, see the results below: **raw history alone did not help**. Jev answers one question
at a time; it does not work out *"my points are falling BECAUSE nobody walked"* from 200 lines of log.

**The coach** turns history into something Jev can use. Ten ticks after each decision (when its
future is already past), the coach replays that moment on a copy of the city with each of the three
actions. The same cars arrive in every replay, so luck is removed. It writes down how much better
each action was than the average action, in a situation described in relative words:
`green=quieter | difference=big | ambulance=none | blocked=none | red_wait=long | pedestrians=few`.
Jev then reads short **LESSONS** for moments like now:

```
LESSONS from the coach, who replayed 412 past decisions with every action:
  FZ: walk +0.8 (23 tries), north_south +0.1 (23 tries), east_west -0.9 (23 tries)
```

The coach is ~70 lines of plain Python (`coach.py`), no API calls. This is reinforcement learning
done in the prompt: try, get points, review, do better, all inside one stream.

## Do it

```bash
python level5-junction/run.py --policy greedy         # simple rules: the opponent
python level5-junction/run.py --ticks 60              # Jev with the history (a short stream first)
python level5-junction/run.py --ticks 60 --lessons    # + the coach's lessons
python level5-junction/run.py --policy jev-no-history --ticks 60   # Jev with only the current tick
python level5-junction/run.py --watch                 # watch it live in the terminal
```

After every run you see the points and the energy per 50 ticks, and the simple rules on **the same
traffic**. Open `level5-junction/viewer3d.html` to replay any run as a **3D city** 🏙️: an officer on
every junction shows the decision (arms out along the road that may go, both arms up for walk), with
a bubble of Jev's probabilities. Click a junction in the side panel to fly to it.

**Cost:** a 200-tick run is about 190 calls. With the full history the context grows every tick:
about 2.5 million input tokens per run (US$0.10). `--history 20` (only the last 20 ticks) is about
4x cheaper. Without history it is about 0.2 million.

## Two example solutions

| File | Idea |
|---|---|
| `solution_a.py` | **Let the coach digest the history.** The full history plus the coach's LESSONS. |
| `solution_b.py` | **A short memory plus lessons.** Only the last 20 ticks + LESSONS: about 4x fewer tokens. |

Real results (jev-latest, exam traffic): see [results, Level 5](../results/RESULTS.md#level-5--jev-runs-three-traffic-lights-as-one-smart-state-machine).

## Same seed, same run

Jev's probabilities move a little between two identical calls, and in a busy city one flipped decision
changes the rest of the stream. So `run.py` saves every answer in `runs/answers.jsonl` and reuses it
for the same request: **the same seed gives exactly the same run**, and a repeat costs nothing.
`--no-cache` asks Jev again.

## The leaderboard 🏆

```bash
python level5-junction/run.py --exam            # seed 2026, 200 ticks: the same traffic for everyone
```

Post your `EXAM SCORE` (and the energy). Highest score wins; less energy breaks a tie.
To beat: the fixed timer scores **−317.6**, the simple rules score **165.3**.

**What you may change:** what Jev reads (`JevOfficer.state()`, `RULES`, `QUESTION` in `officers.py`),
how much history (`--history`), the lessons (`situation()` in `memory.py`, the coach's `HORIZON`).
**What you may NOT change:** the rules, points and traffic in `city.py`.

> In `JEV_MOCK=1` mode the fake keyword matcher plays badly here. Use the real API for Level 5.
> The learning machinery is tested with a scripted mock: see `tests/test_level5.py`. A fake Jev
> that only follows the coach's LESSONS beats random play by hundreds of points within one stream.

## Ideas to win

- Fewer, better lines: what does Jev really need from the history? Try `--history 10`.
- Add a line that connects cause and effect: "people waited 20 ticks at FZ: cost so far −34".
- Make `situation()` smarter (add the wave, or the rain).
- Ask a second question per junction (a `noul`: "will people wait too long?") and combine in code.

## Quick quiz

1. Between tick 10 and tick 190, what changes: Jev's model, or Jev's input?
2. Jev had the full history but almost never chose walk. Why can't it "see" the mistake?
3. Why does the coach wait 10 ticks before it reviews a decision?
4. Why are moves stored as "busier / quieter" and not "north_south / east_west"?
5. The full history costs about 12x the tokens of no history. When is that worth it?
6. Why must everyone use the same seed for the exam?
