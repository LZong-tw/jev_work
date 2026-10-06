# Verify / verify

```json
{
  "claims": [
    {
      "claim": "Current rule averages 298.2 over seeds 1-10 x pre_ticks 0/1/2 and scores 468.8 on seed 7 / pre 1",
      "holds": true,
      "evidence": "Rerun via sim.run(policies.current_rule): mean 298.17 over n=30; seed7/pre1 = 468.8 [VERIFIED]"
    },
    {
      "claim": "Relaxed upper bound is about 2,679 +/- 23 (car crossings 1,778, walker crossings 1,149, stopped-car ticks 90)",
      "holds": true,
      "evidence": "multi3.txt matches. I reran instr.run with relaxed.Relaxed: seed1 2653.2, seed7 2650.8, both within 1-1.2 sd of the stated mean [VERIFIED]. Caveat: relaxed.py credits walkers instantly every tick and turns off box/zebra conflicts. It is a statistical relaxation, not a strict per-seed bound, as the report says."
    },
    {
      "claim": "Demand/capacity table: 1.52/1.11 at 09:00, 1.44/1.54/1.24/1.44 at 17:00, 1.17/1.60 at 19:00, 0.91 on the rush axis, 0.26-0.45 off-peak; 2.00 crossings per vehicle",
      "holds": true,
      "evidence": "flow.py rerun prints exactly these numbers [VERIFIED]. Note that 2.00/veh comes out of the analytic flow model's own routing, not from a measurement on the sim, so it confirms the model and not the sim [INFERENCE]."
    },
    {
      "claim": "Rule loses about 2,370 points, mostly to car waiting (10,224 stopped-car ticks, i.e. -2,027 or 85%), and throughput matches relaxed (1,794 vs 1,778 vehicles)",
      "holds": true,
      "evidence": "agg_rule.txt totals vx 1794.3, px 1156.4, wv 10223.9, wp 2996.7; 0.2*10224 = 2045. Stated -2027 is close (difference likely from per-tick rounding), and the relaxed gap 2679-298 = about 2380 [VERIFIED from file]"
    },
    {
      "claim": "18:00-21:00 hourly net is negative (-26, -31, -39)",
      "holds": true,
      "evidence": "agg_rule.txt rows 18/19/20 show -26.0, -30.8, -39.0 [VERIFIED from file]"
    },
    {
      "claim": "Realistic reachable score of about 1,400-1,650 (fluid model)",
      "holds": false,
      "evidence": "Not reproduced. The report labels it INFERENCE, it ignores spillback, and no policy that was run gets above ~430 on average. Unverified."
    },
    {
      "claim": "Information-value table (roll_clair +178 se 47.3, roll_blind +106.4, far_stopped +13.9, near_moving -1484.7, tie_random +26.1, tie_oracle +40.3, tie_blind +81.3)",
      "holds": true,
      "evidence": "summary.txt matches the report. The paired roll_clair diffs listed recompute to 1423.8/8 = 177.98. I reran info.py roll_clair 5 1 and got 519.6, and tie_random 3 0 and got 353.6; both are identical to all.jsonl [VERIFIED]"
    },
    {
      "claim": "A perfect tie-breaker is no better than a random one, so Jev's value is about 0",
      "holds": false,
      "evidence": "The numbers reproduce, but the conclusion is over-stated. The 'perfect' tie-break is only a 3-tick greedy lookahead, n=8, and it scored worse than the blind version (+40 vs +81, se ~65). That shows the proxy is noisy, not that perfect tie-breaking is worth 0. 'Jev value about 0' is INFERENCE: it was never measured with Jev itself."
    },
    {
      "claim": "Simulating ahead without knowing the future recovers about +106 of the gain",
      "holds": false,
      "evidence": "Reproducible but not statistically resolved: +106.4 with se 69.6, n=8, all pre=1, wins 5/8. That is about 1.5 se, so it cannot be stated as an established gain."
    }
  ]
}
```
