# Verify / verify

```json
{
  "claims": [
    {
      "claim": "The port (sim.py) and the JS oracle match tick for tick for the rule policy at seed 7, pre_ticks 1",
      "holds": true,
      "evidence": "Re-ran compare.py: 'pre=1 seed=7 oracle=468.8 port=468.8 first_state_diff=None first_tick_diff=None'. compare.py now runs only this one case, so the other cases claimed (other pre/seed values, 480 ticks, random policies) were not re-checked."
    },
    {
      "claim": "oracle.js is an unchanged copy of city.html lines 158-704, 969-975 and 1171-1294",
      "holds": true,
      "evidence": "Of 678 non-blank lines in that range, only one is missing from oracle.js, and it is a comment ('// warm up: ...')."
    },
    {
      "claim": "With pre_ticks=1 at seed 7, the sim's running score passes through the known browser results 468.8, 477.8 and 517.4",
      "holds": true,
      "evidence": "sim.run(current_rule, seed=7, pre_ticks=1) gives 468.8 at tick 270, 477.8 at 271 and 517.4 at 278. The browser results were logged at 271/272/278, so the tick labels are off by 0-1, which the report explains only as an INFERENCE."
    },
    {
      "claim": "With pre_ticks=0 the rule scores 358.8",
      "holds": true,
      "evidence": "Re-run printed 358.8."
    },
    {
      "claim": "Fidelity was checked against the real server logs",
      "holds": false,
      "evidence": "'ls /tmp/claude-501/jevtest' returns 'No such file or directory', so the logs are gone. The match with the browser rests only on the three remembered scores (which line up along one path), not on per-tick lane or lights data. The old rule's 316.8 is also unreproduced."
    },
    {
      "claim": "bridge.run_oracle accepts pre_ticks as a keyword, as the report's usage implies",
      "holds": false,
      "evidence": "Calling it with pre_ticks raised TypeError: run_oracle() got an unexpected keyword argument 'pre_ticks'. This is a minor API mismatch with the report."
    }
  ]
}
```
