# Model / build-sim

Built and checked: `sim.py` and the JS oracle (`oracle.js`) agree exactly, tick by tick (VERIFIED). Comparing against the server logs wasn't possible because both are gone after the crash (`/tmp/claude-501/jevtest/` returns "No such file or directory").

**Files** (all in `/private/tmp/claude-501/-Users-untionglim-projects-jev-work-workshop-level5-junction/37ba1b1e-9f11-4930-b535-e2eb29c3a1ab/scratchpad/fp/`; no project files were edited)
- `sim.py`: the port. `run(policy, ticks=270, seed=7, pre_ticks=1, history_len=50, keep_states=True)` returns `{score, states, ticks}`. Each `ticks` entry has `pts`, `score`, `across`, `wv` and `wp`. The states have the same shape as `decideState()` (city.html:1281). `history` follows city_server.py: the last 50 states, each with `lights_chosen` using string keys.
- `policies.py`: `current_rule` loads my_jev.py with `JEV_MODE=rule`, makes no network call, and wraps the async `decide` with `asyncio.run`. There is also a `fixed(...)` helper.
- `oracle.js` + `bridge.py`: city.html lines 158-704, 969-975 and 1171-1294 copied unchanged and run in node. `bridge.py` drives it from a Python policy over stdin/stdout.
- `compare.py`: compares the port with the oracle.

**Fidelity**
- **Oracle vs port:** all 4 crossings match tick for tick, with identical states, points and score [VERIFIED: compare.py]. Cases checked: the rule policy with pre 0/1/2/5, seeds 1/42/1234, 480 ticks, fixed lights, 3 random policies and 2 "sticky" random policies over 480 ticks.
- **Oracle vs browser:** with `pre_ticks=1` (seed 7), the oracle's running score is 468.8 at tick 270, 477.8 at 271 and 517.4 at 278. All three known browser results appear on that one path [VERIFIED: bridge output]. Their tick labels are off by 0 to 1 tick, probably because the log's tick counter runs one ahead of the score [INFERENCE]. So `pre_ticks=1` is the default. With `pre_ticks=0` the score is 358.8.
- **Not checked:** the old rule's 316.8. That code isn't in git (HEAD my_jev.py has a Jev-only decide) and its log is gone.
- **Exact floats:** a 200,000-value test against node showed:
  - V8's `Math.hypot` differs from Python's `math.hypot` (66,192 of 200,000 values differ), so the port copies V8's algorithm.
  - `Math.pow(x,2)` equals `x*x`, not Python's `x**2`.
  - `Math.pow(x,4)` equals `x**4`.
  - `Math.round` is `floor(x+0.5)`.

**Runtime:** about 2.2 s per 270-tick run in Python. The node oracle takes about 0.4 s and can be used through `bridge.run_oracle` if speed matters.

**Randomness:** the simulation uses one seeded `mulberry32(seed)` stream (`?seed=`, default 7; city.html:165-168), so it is fully deterministic. `Math.random` only affects 3D helmet colours. The stream is drawn on in an order that depends on the control decisions:
- `planFor` draws the next turn when a vehicle first gets green (:319).
- A blocked vehicle at the map edge redraws its turn every 0.05 s step (:647).
- People and vehicles also draw rnd values that are only used for drawing, and these still advance the stream.

As a result, any change in policy or timing changes all later traffic, and the score is chaotic:
- Rule score by `pre_ticks` 0-8: 358.8 / 468.8 / 136 / 135.2 / 156.6 / 170.6 / 316 / 113 / 315.
- Rule score over seeds 1-10: mean 306.6, sd 140.9.
- So a policy has to be scored over many seeds and `pre_ticks` values, not one run.

**Mechanics that affect control** (city.html lines)
- **Timeline:** the clock starts at 07:30, and a 90 s warm-up (1800 steps, :1294) under the built-in "smart" controller brings it to 09:00. One step is 0.05 s and one tick is 60 steps (3 clock minutes). Because of float drift, tick 1 reads 08:59 with pre 0 and 09:02 with pre 1. Tick 270 reads 22:29, so the run covers 09:00-22:30.
- **Before connecting:** the page runs one tick in "smart" mode before `/api/config` answers (:1144-1150). This race is why `pre_ticks=1` matches the browser. All lights are then red until the first `decide` (:1337).
- **Score (:1355):** each tick, +1 per vehicle or person that started across any crossing, minus 0.2 × (all vehicles on the map with v<0.3 plus all people waiting at a zebra). Both the tick's points and the running total are rounded to 0.1. The waiting count includes vehicles queued more than 80 m back, which `decide` never sees. Vehicles still waiting at the map edge (backlog) are not counted.
- **Vehicle spawning (:633):**
  - Rate is 0.95 × busy × (2 during a car rush) vehicles per second, or 2.85 × busy × mult per tick.
  - busy (:479) is 1.0 for 07-09:30, 1.05 for 17-19:30, 0.18 for 23-06 and 0.6 otherwise.
  - There are 8 entry roads, equally likely; during a rush each road heading the rush direction gets weight 6 (:628). For "E" that is 2/3 of spawns, for "WS" 24/28.
  - Rush hours (:488): 9 E, 10 N, 11 E, 12 people ×4, 13 W, 14 S, 15 N + people ×2.5, 16 E, 17 W+S, 18 people ×3, 19 N.
  - Vehicle types (:266): car 0.44, taxi 0.11, bus 0.05, scooter 0.27, bike 0.13. Scooters and bikes (40%) use the bike lane.
  - Turns (:282): cars go 20% left, 60% straight, 20% right. Bikes go 78% straight, 22% right, and never turn left. A vehicle uses the L lane only to turn left.
  - New vehicles queue at the map edge (backlog) when there's no room.
- **Release rule (:561, :323):** at the start of each tick, the first vehicle in each lane goes if it is within 12 m of the stop line and its light is green, so at most 1 per lane per tick.
  - Phase A or C can release up to 4 (2 straight/right lanes + 2 bike lanes); B or D up to 2. Bikes only move in A or C.
  - A vehicle is held if there is no room past the crossing (`tailRoom`, :309). A straight-going car may switch lanes to get through.
  - It is also held if people are on the zebra, or if the crossing still has a vehicle from another phase.
  - A right-turning car waits once for bikes, and after that the bikes wait for it. Bikes are held while a car turning right from the S lane is crossing.
  - Crossing takes exactly 1 tick, so every crossing is empty when a tick starts.
- **Moving between crossings:** a vehicle lands on the next road at the end of its crossing tick. Roads between crossings are 107.8 m east-west and 73.8 m north-south; entry and exit roads are 144.9 m and 111.9 m. At free speed (about 14 m/s) the next crossing is roughly 2-3 ticks away [INFERENCE]. The state only counts stopped vehicles within 80 m, so on the north-south links the whole road is visible.
- **People (:452, :611, :656):**
  - They spawn at 0.8 × busy × crowd per second, with at most 260 × crowd on the map.
  - They walk at 1.1-1.6 m/s along shortest routes, with each zebra costing an extra 12 m so they avoid crossings.
  - On W, everyone waiting at that crossing goes at the start of the tick and is across by its end, each scoring +1.
- **Lights:** in direct mode there is no yellow or all-red (:1302). Re-sending the same phase does not reset the `ticks` counter. A crossing left out of the answer keeps its lights.
