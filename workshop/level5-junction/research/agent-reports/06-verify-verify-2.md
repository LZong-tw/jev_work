# Verify / verify

```json
{
  "claims": [
    {
      "claim": "Current rule over seeds 1-10 (pre_ticks=1) averages 306.6 with sd 140.9, and scores 468.8 on seed 7",
      "holds": true,
      "evidence": "VERIFIED: I reran sim.run(policies.current_rule) independently and got [246.2,191.6,159.6,484.6,536.2,343.0,468.8,184.8,233.4,217.6], mean 306.58, sd 140.88"
    },
    {
      "claim": "Rule mean over 30 runs (seeds 1-10 x pre 0/1/2) is 298.2, the baseline the info table is measured against",
      "holds": true,
      "evidence": "VERIFIED: my rerun gives 298.17; summary.txt shows rule n=30 mean 298.2"
    },
    {
      "claim": "Relaxed upper bound is 2679 +/- 23 over 10 seeds, with 1778 car crossings, 1149 walker crossings and about 90 stopped-car ticks",
      "holds": true,
      "evidence": "VERIFIED that the saved file says this: multi3.txt gives mean 2678.8, sd 22.9, vehX 1777.8, pplX 1148.8, wv 89.9. NOT independently rerun, and I did not audit how relaxed.py relaxes the sim. It is a statistical bound, not a strict one."
    },
    {
      "claim": "Information-value table: look-ahead with the real future +178 (se 47.3, n=8), look-ahead with new randomness +106.4 (se 69.6), far stopped vehicles +13.9, near moving vehicles -1484.7, random tie-break +26.1, perfect tie-break +40.3",
      "holds": true,
      "evidence": "VERIFIED against summary.txt: every number matches, and the rule baselines per seed for n=8 (246.2...184.8) match my independent rerun. The rollout runs themselves were NOT rerun. With n=8 and se 47-70, the +178 vs +106 gap and the tie-break rows cannot be told apart statistically."
    },
    {
      "claim": "Jev (the LLM tie-breaker in hybrid mode) adds no measurable value, and a perfect tie-breaker is no better than a random one",
      "holds": true,
      "evidence": "INFERENCE supported by summary.txt: tie_oracle +40.3 se 63.5 (n=8) and tie_random +26.1 se 34.4 (n=30). Neither is distinguishable from 0. This says no detectable value; it does not show the value is zero."
    },
    {
      "claim": "Realistic reachable score is about 1400-1650 (fluid model)",
      "holds": false,
      "evidence": "INFERENCE only; not reproduced. The model ignores spillback, and the report itself says spillback is a real risk (cyc.py scores -1196 and -5400). The best policy actually run is 425.8 on the held-out set."
    },
    {
      "claim": "Demand loads (1.52/1.11 etc. at 09:00, oversaturated windows) and 2.00 crossings per vehicle",
      "holds": false,
      "evidence": "Not independently recomputed in this check; flow.py output was not rerun. Treat as unverified."
    }
  ]
}
```
