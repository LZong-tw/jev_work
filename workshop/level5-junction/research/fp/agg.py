import instr, policies, relaxed, collections, sys
from sim import City
name = sys.argv[1]
pol, cls = (policies.current_rule, City) if name == "rule" else ((lambda h, c: {}), relaxed.Relaxed)
A = collections.Counter(); N = 10
for sd in range(1, N + 1):
    s, log = instr.run(pol, seed=sd, cls=cls)
    for k, v in log.items(): A[k] += v / N
instr.summarize(0, A, open(f"agg_{name}.txt", "w"))
