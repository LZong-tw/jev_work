# Analyze / analyze-info

## Information value in the junction simulator

**Bottom line:** across 8 seeds, a controller that knew the exact future scored about +178 points over 270 ticks above the current rule (se 47). That is a ceiling, and it is noisy. Simulating ahead without knowing the future already recovers about +106 of it (se 70), and plain code can do that. An LLM that only breaks ties between close options, which is Jev's role in hybrid mode, adds nothing measurable: a perfect tie-breaker scored no better than a random one. Jev's real value in this task is about 0.

All results come from runs in `fp/` [VERIFIED: `info.py`, `all.jsonl`, `summary.txt`]. The harness reproduces the rule's 468.8 on seed 7 with pre_ticks=1, the same as the browser. No project files were edited.

### Results
The rule averages 298.2 over 30 runs (seeds 1-10, pre_ticks 0/1/2). Each row below is compared run-for-run against the rule on the same seed. Runs differ a lot from each other, so the standard error (se) matters as much as the mean.

| What the policy gets | Runs | Gain vs rule | se | Better than rule |
|---|---|---|---|---|
| Stopped vehicles more than 80 m back, which the state hides | 30 | +13.9 | 12.5 | 7/30; identical in most runs |
| Moving vehicles within 80 m, fed into the same rule | 30 | **-1484.7** | 35.8 | 0/30 |
| Random tie-break among the phases hybrid mode sends to Jev | 30 | +26.1 | 34.4 | 20/30 |
| Look ahead 3 ticks on a copy of the sim with **real** future randomness (knows the future) | 8 | **+178.0** | 47.3 | 7/8 |
| Same look-ahead with **new** randomness (accurate model, unknown future) | 8 | +106.4 | 69.6 | 5/8 |
| Perfect tie-break (3-tick look-ahead with real randomness), only among Jev's options | 8 | +40.3 | 63.5 | 5/8 |
| Same tie-break with new randomness | 8 | +81.3 | 70.7 | 4/8 |

- **Look-ahead method:** it starts from the rule's choice. For each crossing it tries all 5 phases on a deep copy of the sim, plays 3 ticks with the rule after the first, and keeps the best. The copy uses a deep-copyable RNG (`info.py: RNG`), because the closure-based RNG in `sim.py` would be shared between the copy and the live run.
- **How often Jev gets asked:** in hybrid mode Jev breaks a tie on 276 of 1080 crossing-ticks (25.6%) on seed 7. Those are the ticks where `TIE_MARGIN` 0.5 leaves more than one car phase close to the best [VERIFIED: `close_sets` count].

### What the controller doesn't know, and what each piece is worth
1. **Future arrivals, turns and spawn randomness.** Nobody can know these. Knowing them is worth about 178 - 106 ≈ **+70 points**, but with se of 50-70 on 8 runs this is not statistically resolved [INFERENCE]. Also, the perfect tie-break did no better than the one with new randomness (+40 vs +81). So most of the gain comes from simulating ahead at all, not from knowing the actual random draws. Exact knowledge of the future doesn't help a 3-tick greedy controller much, because one decision changes every later random draw.
2. **Vehicles the state doesn't show.** Stopped vehicles more than 80 m back are worth about +14 (se 12.5), indistinguishable from zero; queues rarely reach that far. Moving vehicles are worth something only to a policy built to use them. Adding them to the current rule makes it collapse, because `served()` counts any non-empty lane as crossing this tick (my_jev.py:161-168). So the value of this information depends entirely on the policy using it.
3. **Rush-hour timing.** This is not hidden. The rush table is fixed by clock time (sim.py:78, city.html:488), and `rush_outlook` already puts it in the prompt (my_jev.py:206). I did not run a separate test for it. Any program can read the same table, so it gives an LLM no advantage.
4. **Downstream space** (room on the exit road, `tail_room` at sim.py:347). Each crossing's state doesn't include it, but the next crossing's queue counts in the same state partly reveal it, and a program can compute it. The look-ahead results already include it. I did not measure it on its own.
5. **Within-tick mechanics** (one vehicle per lane per tick, conflicts with people on the zebra, right turns yielding to bikes). These are deterministic rules in the code. A program can model them exactly; a text classifier only gets a rough description of them.

### What Jev could actually add
Jev, the LLM classifier in jev.py, reads a text description of the state and returns probabilities over the labels it is given (`choice`, jev.py:83-97, 203). Everything it reads is numbers that `decide()` itself built from the state (my_jev.py:216-262). Jev has no information the program lacks, and it cannot simulate. Each tick's question ("which phase earns the most points over the next few ticks?") is a short-horizon optimisation over known dynamics, and code does that better: the look-ahead gained about +106 with no Jev call at all.

Where Jev decides in hybrid mode, the choice is between phases the rule already scores as nearly equal. Even a perfect choice there is worth +40 ± 64, a random choice +26 ± 34, and neither can be told apart from 0.

There is nothing here that only judgment can supply: no ambiguous text, no human intent, no unstated preference. Jev's realistic value in this task is **about 0, and possibly negative**. Its answers vary between identical calls (jev.py:207-209), which adds noise to a system where any change in one decision changes all later traffic. It also costs one network call per tick. The only legitimate role I see is as a teaching device (showing an LLM in the loop), not as a way to raise the score [INFERENCE].

### Caveats
- The look-ahead and perfect tie-break rows have only n=8, all with pre_ticks=1, and their standard errors are large. Read the gaps between those rows as direction, not size.
- The rule's mean is 298.2 over 30 runs, and on seed 7 / pre 1 it scores 468.8. Any single browser run is mostly luck. Judge policy changes by run-for-run comparison over at least 30 seeds × pre_ticks.

Files are in `/private/tmp/claude-501/-Users-untionglim-projects-jev-work-workshop-level5-junction/37ba1b1e-9f11-4930-b535-e2eb29c3a1ab/scratchpad/fp/`:
- info.py
- all.jsonl
- summary.txt
