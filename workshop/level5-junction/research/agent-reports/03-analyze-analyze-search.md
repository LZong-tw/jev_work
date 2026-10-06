# Analyze / analyze-search

I found a better controller: the current rule with three settings changed (queue weight, walk timing, and a penalty for a full next crossing). On 40 test runs it was not tuned on, it scores **+69 ± 25 (se) points** more than the current rule at tick 270. It is saved in `best_policy.py` and makes no network call. The score swings a lot from run to run, so any single run says little.

**What I checked first**
- `best_policy.decide_sync` with the old settings `qw=0.3, walk_starve=6, down_w=0` gives exactly 468.8 at seed 7, pre_ticks 1. That is the same as `policies.current_rule` and the known browser result, so the copy matches my_jev.py rule mode. [VERIFIED: search.py output]
- The policy family is the current rule plus a few knobs:
  - **Downstream penalty (`down_w`):** for phases A and C, subtract `down_w` × the cars already queued on the side where they enter the next crossing. This is a simple max-pressure term.
  - **`hold`:** a bonus for keeping the current phase.
  - **Walk settings:** `walk_batch`, `walk_starve`, `walk_min`, `walk_max_wait`.

**How I chose the settings**
- **Tuning set:** seeds 1-6 × pre_ticks 0/1/2, plus seed 7 / pre 1 (19 runs per setting). Results are in `sweep1.txt` (24 settings) and `sweep2.txt` (36 settings).
- **Holding a phase:** `hold=1` gave lower means in the sweep, so I dropped it.
- **Check on new data:** the top settings were run on seeds 11-30 × pre 0/1 (40 runs), paired against the current rule on the same runs [VERIFIED: `val1.txt`].

| Settings | Mean | sd | min | vs current rule |
|---|---|---|---|---|
| current rule (qw .3, starve 6, down 0) | 356.6 | 143.1 | 90.6 | — |
| **qw .1, starve 12, down .15 (best)** | **425.8** | 137.9 | 70.0 | **+69.1 ± 25.5** |
| qw .2, starve 9, down .15 | 390.8 | 165.6 | 106.2 | +34.1 ± 32.3 |
| qw .3, starve 18, down .3 | 390.9 | 144.4 | 81.4 | +34.3 ± 26.7 |
| qw .3, starve 9, down .3 | 380.1 | 124.7 | 64.4 | +23.5 ± 25.4 |

- **Browser case:** at seed 7 / pre 1 the best setting scores 512.6, against 468.8 for the current rule.
- **The 672.6 at seed 7 / pre 1** (qw .3, starve 9, down .3) does not hold up: on the 40 test runs that setting gains only +23.5. One run cannot rank settings because the score is chaotic.

**Sensitivity**
- The spread between runs (sd about 140) is larger than any difference between settings.
- Every setting still has some runs below 100.
- **Where points are lost** [VERIFIED: trajectories for seeds 1, 2, 3 and 7]:
  - Throughput stays at about 5-23 crossings per tick in every phase of the day.
  - The 17:00-19:30 rush pushes stopped vehicles to about 60-75.
  - The running score drops by roughly 30-130 over ticks 170-245.
  - [INFERENCE] The cap of one vehicle per lane per tick, plus queues spilling back, is the main limit. Phase choice only adds or loses a few tens of points on average.

**What I did not do**
- **Rollout / lookahead.** `decide` only receives stopped-vehicle counts within 80 m of each crossing. It does not get vehicle positions or the random-number state, and any change in decisions changes all later traffic. So a lookahead policy cannot run from my_jev.py. [INFERENCE from `sim.decide_state` and the shared mulberry32 random stream] I did not use it as an upper-bound experiment either, so the best achievable score is still unknown.
- **The old 316.8 rule.** Its code and log are gone, so it was not reproduced.

**Using it**
- `best_policy.decide_sync(history, current, **overrides)` is synchronous. `best_policy.decide` is an async drop-in for `my_jev.decide`.
- It works with string or int crossing ids in `lights_chosen`.
- A 270-tick run takes about 2.2 s, nearly all of it simulator time.
- No project files were edited.

Files are in /private/tmp/claude-501/-Users-untionglim-projects-jev-work-workshop-level5-junction/37ba1b1e-9f11-4930-b535-e2eb29c3a1ab/scratchpad/fp/:
- best_policy.py
- search.py
- validate.py
- sweep1.txt
- sweep2.txt
- val1.txt
