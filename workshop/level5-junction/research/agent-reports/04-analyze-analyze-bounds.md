# Analyze / analyze-bounds

**Capacity and score bounds for the 2x2 crossing sim (current rule, 270 ticks)**

The current rule loses about 2,370 points to waiting, not to throughput. About 85% of that is cars waiting. The network is oversaturated in only three rush windows, and the worst hours (18:00–21:00) come from the 17:00 rush backlog not clearing.

All runs use `sim.py` with `pre_ticks=1`, 270 ticks, seeds 1–10. No project files were edited. Analysis files are in `/private/tmp/claude-501/-Users-untionglim-projects-jev-work-workshop-level5-junction/37ba1b1e-9f11-4930-b535-e2eb29c3a1ab/scratchpad/fp/`:
- **Demand and saturation:** `flow.py` (traffic demand per crossing), `fluid.py` (estimate of the smallest possible waiting cost), `zebra.py` (zebras crossed per walker).
- **Runs:** `instr.py` (logs points by crossing and hour), `relaxed.py` (the upper-bound setup), `agg.py` (averages over seeds), plus the baselines `greedy.py` and `cyc.py`.
- **Saved output:** `agg_rule.txt`, `agg_relaxed.txt`, `rule_seed7.txt`, `relaxed_seed7.txt`, `multi.txt`, `multi3.txt`.

### 1. Demand compared with capacity
`flow.py` computes how much traffic each lane gets, using the spawn, rush and turn rules in the sim.

- **Crossings per car:** every vehicle passes exactly 2.00 crossings on average [VERIFIED: flow.py]. Each walker passes 1.64 zebras on average; 0 to 4 zebras is 12/34/35/16/3%. Walker load is uneven: J0 0.52, J1 0.45, J2 0.36, J3 0.32 per walker [VERIFIED: zebra.py].
- **Capacity:** at most one vehicle per lane per tick, only when that lane is green (`sim.start_tick`, matching city.html :561).
- **How I measured load:** for each crossing, I took the busiest lane in each of A/B/C/D and added the four. This is the share of ticks the crossing must spend on cars. It must stay below 1 minus the share of ticks spent on W (walkers).

| Time | Load per crossing (J0/J1/J2/J3) | State |
|---|---|---|
| 09:00–09:30 (busy=1.0 × E rush) | 1.52 / 1.11 / 1.52 / 1.11 | Oversaturated |
| 17:00–18:00 (busy=1.05 × W+S rush) | 1.44 / 1.54 / 1.24 / 1.44 | Oversaturated |
| 19:00–19:30 (busy=1.05 × N rush) | 1.17 / 1.17 / 1.60 / 1.60 | Oversaturated |
| Other rush hours | 0.91 on the rush axis, 0.67 elsewhere | Close to full |
| Off-peak (12, 18, 20–22) | 0.26–0.45 | Light |

At 0.91, only about 9% of ticks are left for W, so walkers get served about once every 11–12 ticks. The current rule spends 18–23% of ticks on W (51–63 of 270 per crossing, averaged over seeds). That alone pushes the 0.91 crossings over their limit [INFERENCE from the load numbers + VERIFIED phase counts in `agg_rule.txt`].

### 2. Score bounds

**Upper bound, measured with `relaxed.py`.** I relaxed the sim so every car movement is always green, with no conflicts inside the crossing or with walkers, and W is served every tick at no cost to cars. Car physics, the room needed past the crossing, and the one-car-per-lane release rule are unchanged.
- Score: **2,679 ± 23** over 10 seeds [VERIFIED: multi3.txt].
- Car crossings 1,778, walker crossings 1,149, stopped-car ticks only 90, walker wait ticks 1,149 (exactly one tick per walker, the part of a tick they wait before release).
- So almost no car waiting is unavoidable; nearly all of it comes from the signals.
- This is a statistical bound, not a strict one per seed, because traffic changes with policy. No real policy should come near it.

**Realistic estimate (rough fluid model, `fluid.py`).**
- **Assumptions:** standard queue formulas, one W tick per cycle, cycle length optimised per crossing and half hour.
- **Cost:** the smallest waiting cost outside the rush peaks is about 1,077 points. The three oversaturated windows (16 crossing–half-hours) add roughly 200–400 more [INFERENCE].
- **Result:** a reachable score of about **1,400–1,650** [INFERENCE].
- **Caveat:** this ignores spillback. That is a real risk: fixed cycles without B/D phases score about −5,400, and a fixed ABCD+W cycle scores −1,196 [VERIFIED: cyc.py], because cars that cannot turn left fill their lane and block the crossing.

**Lower bound (best policy actually run).**
- Current rule: **306.6 ± 140.9** over seeds 1–10; 468.8 on seed 7 [VERIFIED: multi.txt].
- A greedy "release the most this tick" policy did much worse: −807 to −1,345 [VERIFIED: greedy.py run].

The current rule is about 2,370 below the relaxed bound and roughly 1,100–1,350 below the realistic estimate.

### 3. Where the score is lost
Averaged over 10 seeds, from `agg_rule.txt` compared with `agg_relaxed.txt`:

**What the rule gets wrong:**
- **Throughput is fine:** car crossings are 1,794 (relaxed 1,778) and walker crossings 1,156 (relaxed 1,149). The rule loses no throughput.
- **Car waiting: −2,027 points (85%).** Stopped-car ticks are 10,224 compared with 90. That is an average of 38 cars stopped every tick.
- **Walker waiting: −370 points (15%).** Wait ticks are 2,997 compared with 1,149.

**By crossing** (extra stopped-car ticks / extra walker wait ticks):

| Crossing | Extra car wait ticks | Extra walker wait ticks |
|---|---|---|
| J0 | 3,036 | 507 |
| J2 | 2,717 | 465 |
| J1 | 2,336 | 463 |
| J3 | 2,048 | 413 |

**By hour:**
- **18:00–21:00 are net negative** (−26, −31, −39 points per hour, against +250 to +285 in the relaxed run). In this period the rule clears fewer cars than arrive at 17:00 (144 vs 192), then is still clearing the leftover queue at 20:00 (140 vs 102 in the relaxed run). That leftover queue, plus the 18:00 walker rush (×3) and the 19:00 N rush, adds 50–80 stopped-car ticks per tick.
- **Low-demand hours also lose a lot:** at 12:00 the load is only 0.26, yet the rule still has about 33 stopped cars per tick and nets +20, against +157 in the relaxed run. The fluid model expects under 2 points per tick of cost here. So the rule wastes a lot even when traffic is light [INFERENCE: likely too many phase switches with one-tick greens; not traced].
- **Mid-day rush hours (10:00–16:00)** net +14 to +61 points per hour, against +157 to +214 relaxed. The 0.91-load crossing on the rush axis is always among the worst. For example, J2 has 246–261 stopped-car ticks per hour during the 10:00 N and 11:00 E rushes.

### 4. What this means for a better policy
1. Car waiting is where the score is. Long greens on the rush axis, few phase switches, and avoiding spillback matter far more than walker timing.
2. During car rushes, serve W at most about once every 10–12 ticks on the busy crossings. During the walker-only hours (12:00, 18:00) car load is 0.26–0.45, so W can be served often.
3. Clear the 17:00 queue by around 18:00; a large share of the gap to the bound sits in the 18:00–21:00 carry-over.

**Not checked:**
- The old rule's 316.8 (the code and log were lost).
- The fluid estimate ignores travel time between crossings and green-wave timing. Coordinating greens between crossings could beat it.
