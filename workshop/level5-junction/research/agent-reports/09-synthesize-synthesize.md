# Synthesize / synthesize

# First-principles strategy for level5-junction

Evidence tags: **[V]** means a subagent reported it and the verifier reran it. **[V-agent]** means a subagent's command output that was not rerun. **[I]** means inference. I did not edit any project files. Analysis files are in `/private/tmp/claude-501/-Users-untionglim-projects-jev-work-workshop-level5-junction/37ba1b1e-9f11-4930-b535-e2eb29c3a1ab/scratchpad/fp/`.

## 1. What the problem physically is

- **The simulation is deterministic but chaotic.**
  - One `mulberry32(seed)` stream drives everything (city.html:165-168).
  - The stream is consumed in an order that depends on decisions (:319, :647). One different light changes all later traffic.
  - The rule's score depends heavily on `pre_ticks`: 358.8 at pre 0 and 468.8 at pre 1 [V]. Over seeds 1-10 × pre 0/1/2 it averages 298.2 [V].
  - So one browser run tells you very little about a policy.
- **The port is trustworthy.**
  - `sim.py` matches the JS oracle tick for tick on seed 7 / pre 1 [V]. The other cases were checked only by the original agent [V-agent].
  - The oracle's path passes through all three known browser scores: 468.8, 477.8 and 517.4 [V].
  - It was not checked against per-tick server logs, because `/tmp/claude-501/jevtest/` no longer exists [V].
- **Capacity works like this.**
  - At most one vehicle per lane per tick, and only when that lane is green (city.html:561, :323).
  - Crossing a junction takes exactly 1 tick.
  - W (walk) lets every waiting walker cross in one tick.
- **Score:** +1 per crossing, minus 0.2 × (every stopped vehicle on the map + every waiting walker) per tick (:1355).
- **Waiting costs points; throughput does not.**
  - The rule's throughput is already at the relaxed level: 1,794 vehicles against 1,778, and 1,156 walkers against 1,149 [V].
  - The rule loses about 2,380 points to the relaxed upper bound of 2,679 ± 23 [V]. That bound is statistical, not a strict per-seed limit.
  - About 85% of the loss is cars waiting: 10,224 stopped-car ticks against 90 [V].
- **Saturation by time of day** [V]:
  - Oversaturated at 09:00-09:30, 17:00-18:00 and 19:00-19:30 (load 1.1-1.6).
  - The rush axis is near capacity in the other rush hours (0.91).
  - Off-peak load is light (0.26-0.45).
- **The 17:00 rush leaves a backlog.** Hours 18, 19 and 20 net -26.0, -30.8 and -39.0 points [V].

## 2. Best verified controller

`best_policy.py` is the current rule with three changed settings, plus a downstream penalty:

| Knob | Current rule | Best |
|---|---|---|
| `qw` (queue weight) | 0.3 | **0.1** |
| `walk_starve` | 6 | **12** |
| `down_w` (for A/C, subtract down_w × cars queued at the next crossing's entry) | 0 | **0.15** |

- **The copy is faithful.** With the old settings it reproduces 468.8 at seed 7 / pre 1, the same as `policies.current_rule` [V].
- **Validation, untuned, seeds 11-30 × pre 0/1, paired (n=40):** 425.8 against 356.6, a gain of **+69.1 ± 25.5 se** [V-agent].
- **Independent fresh check, seeds 41-45, pre 2:** a gain of +259.9 ± 76.1. It was better on 5 of 5 runs [V].
  - The size depends on the mix of seeds and `pre_ticks`. The direction is solid; the size is not [V].
- **Nearby settings did about as well.** (qw .12, starve 11, down .18) and (.08, 13, .12) both beat the rule, so this is a good region, not a single knife-edge point [V].
- **Browser case (seed 7 / pre 1):** 512.6 against 468.8 [V].

## 3. Jev's role

**Recommendation:** Jev should not make the per-tick phase choice. Use it only as an optional, guarded demo.

- **Jev has no information the program lacks.**
  - It classifies a text that `decide()` builds from the state (my_jev.py:216-262; jev.py:83-97, 203) [V-agent].
  - Rush timing is a fixed table (city.html:488) that the program can already read.
  - The mechanics are deterministic code.
- **The tie-breaks Jev handles are not worth anything measurable.** In hybrid mode Jev decides 25.6% of crossing-ticks [V-agent]. In those cases:
  - A random choice gained +26.1 ± 34.4.
  - A 3-tick look-ahead with the real future gained +40.3 ± 63.5.
  - A look-ahead with new randomness gained +81.3 ± 70.7.
  - None of these can be told apart from zero [V numbers].
- **This does not prove that Jev's value is zero.** It shows that the value of tie-breaking is too small to measure at n=8. Jev itself was never tested. So "about 0" is [I].
- **Jev adds noise and cost.** Its answers vary between identical calls (jev.py:207-209), which is harmful in a chaotic system. It also costs one network call per tick.
- **If Jev must stay in the loop (for teaching), use this setup:**
  - **Question:** one `choice` among the phases `best_policy` scores within the tie margin of the best phase. Never ask it to choose among all phases.
  - **Frequency:** at most once per tick, and only when there is a tie.
  - **Guardrails:**
    - Accept Jev's answer only if its probability is at least 0.6 and the answer is in the allowed set.
    - On a timeout or exception, fall back to the deterministic choice.
    - Never let Jev override walk-starvation or spillback (`down_w`) vetoes.
    - Never ask Jev during the oversaturated windows (09:00-09:30, 17:00-18:00, 19:00-19:30).

## 4. Implementation plan for my_jev.py (one change)

1. Change the rule-mode constants to `qw=0.1`, `walk_starve=12` and `down_w=0.15`.
2. Add the downstream term to the A/C scores. Copy it exactly as it is in `best_policy.decide_sync`: subtract `down_w` × the queue on the entry side of the next crossing.
3. Make sure crossing ids in `lights_chosen` work as both strings and ints.
4. Make rule mode, with these settings, the default. Keep `JEV_MODE=hybrid` with the guardrails from section 3.
5. Leave out `hold`; it lowered the mean in the sweep [V-agent].

## 5. Evaluation protocol

1. **Equivalence check:** run the new my_jev.py through `policies` and `sim.run`. It must give exactly 512.6 at seed 7 / pre 1, matching `best_policy`.
2. **Paired test:** seeds 1-30 × pre 0/1/2 (90 runs), comparing the new policy with the old rule on the same runs. Report the mean difference, se, wins/losses and the minimum.
   - Accept only if the gain is positive and greater than 2 se.
   - Run time is about 2.2 s per run in Python, or about 0.4 s with the node oracle. Note that `bridge.run_oracle` does not take `pre_ticks` [V].
3. **Hybrid check, only if it is kept:** run the same 90 runs with Jev, or with a random tie-break stand-in. Hybrid must not be significantly worse than rule mode.
4. **Live check:** restart `city_server.py` with `JEV_MODE=rule` and load city.html with default seed 7. The expected score at tick 270 is about **512.6**. The tick counter may be one ahead of the score [I].
   - A mismatch means the browser has drifted, for example a different number of pre-ticks before connecting. It does not mean the policy is worse.

## 6. Still uncertain

- **The real size of the gain** is anywhere from about +69 to about +260 depending on the seed and `pre_ticks` mix. Only the direction is established.
- **Fidelity against per-tick server logs** was not checked, because the logs are gone. The old rule's 316.8 was never reproduced.
- **How much is reachable** is unknown:
  - The fluid-model estimate of 1,400-1,650 is [I], unreproduced, and ignores spillback.
  - No policy that was actually run averages above about 430.
- **Look-ahead** (+106 ± 70, n=8) is suggestive but not resolved. It can't run from `decide()` anyway, because `decide()` receives only stopped-vehicle counts within 80 m [I].
- **Clearing the 17:00 backlog and green-wave coordination** have not been tried. They are the biggest untested levers [I].
