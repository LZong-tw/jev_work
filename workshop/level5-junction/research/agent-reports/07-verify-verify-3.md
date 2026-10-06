# Verify / verify

```json
{
  "claims": [
    {
      "claim": "Best policy (qw .1, starve 12, down .15) scores 512.6 vs the rule's 468.8 at seed 7 / pre_ticks 1",
      "holds": true,
      "evidence": "[VERIFIED: fp/adv.py output: 'seed7 best 512.6 rule 468.8'] Reproduced exactly."
    },
    {
      "claim": "Best policy beats the current rule on fresh, untuned runs (not overfit to one deterministic run)",
      "holds": true,
      "evidence": "[VERIFIED: adv.py] On seeds 41-45 with pre_ticks 2 (outside the tuning set seeds 1-7 and the validation set seeds 11-30 x pre 0/1): best 390.0 mean vs rule 130.1. Paired diffs were +512.8, +195.6, +62.8, +198.0, +330.4, i.e. +259.9 +/- 76.1 se, positive in 5 of 5 runs. The size is larger than the claimed +69 because pre 2 is a bad case for the rule (n=5); the direction holds."
    },
    {
      "claim": "The result is robust to small parameter perturbations, so it is not a knife-edge optimum",
      "holds": true,
      "evidence": "[VERIFIED: adv.py] On the same 5 runs, (qw .12, starve 11, down .18) averaged 447.8 and (qw .08, starve 13, down .12) averaged 416.4. Both beat the rule's 130.1 and are about as good as the best setting's 390.0. [INFERENCE] The gain comes from the region of lower qw, longer walk starve and a small downstream penalty, not from one exact point."
    },
    {
      "claim": "The size of the improvement (+69 +/- 25) is precisely established",
      "holds": false,
      "evidence": "[INFERENCE] My 5 fresh runs gave +260 +/- 76, and the sd per run is about 140. The effect size depends heavily on the seed and pre_ticks mix. Only the direction (best > rule) is solid. I did not independently check sim fidelity against the browser here: the original logs are gone, and only the seed-7 468.8 match was reproduced. Total: 22 runs, 12 s wall."
    }
  ]
}
```
