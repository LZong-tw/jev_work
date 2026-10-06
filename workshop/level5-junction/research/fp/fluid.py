"""Fluid (Webster-style) estimate of minimum waiting cost per crossing, per half-hour, using
analytic vehicle lane rates (flow.py) and walker arrival rates measured in the relaxed run."""
import flow, collections
from sim import PHASES
# walker arrivals per tick per crossing per hour, relaxed seed7 (pplX / 20 ticks)
PX = {9:(18,16,15,10),10:(29,12,10,13),11:(21,11,19,12),12:(29,22,14,12),13:(40,26,22,14),14:(28,31,22,6),
      15:(23,11,20,13),16:(25,20,19,9),17:(32,17,19,21),18:(33,33,27,24),19:(46,41,25,27),20:(38,20,31,21),
      21:(14,27,22,9),22:(4,7,1,7)}
def best(lane, jid, lp):
    f = flow.util(lane, jid); F = sum(f.values())
    lanes = {}
    for ph, (heads, moves) in list(PHASES.items())[:4]:
        for h in heads:
            for l in (["L"] if moves == "L" else ["S", "B"]):
                lanes[(h, l)] = (ph, lane.get((jid, h, l), 0))
    out = None
    for k in range(2, 41):
        avail = k - 1                       # one W tick per cycle
        if F * k > avail: continue          # oversaturated at this cycle length
        g = {ph: avail * f[ph] / F if F else 0 for ph in f}
        veh = sum(lam * (k - g[ph]) ** 2 / (2 * k * max(1e-9, 1 - lam)) for ph, lam in lanes.values())
        ppl = lp * (k + 1) / 2              # walkers wait ~k/2 + the unavoidable partial tick
        c = 0.2 * (veh + ppl)
        if out is None or c < out[0]: out = (c, k, veh, ppl)
    return out, F
tot = 0; rows = []
for hh in range(9, 23):
    for half in (0, 30):
        if hh == 22 and half == 30: continue
        _, lane = flow.rates(hh * 60 + half + 1)
        cs = []
        for jid in range(4):
            o, F = best(lane, jid, PX[hh][jid] / 20)
            cs.append((o, F))
            tot += (o[0] if o else float("nan")) * 10
        print(f"{hh:02d}:{half:02d} " + "  ".join(f"J{j} rho{F:.2f} " + (f"k={o[1]:2d} cost/tick {o[0]:.2f}" if o else "OVERSAT") for j, (o, F) in enumerate(cs)))
print("fluid min waiting cost over 270 ticks (nan => oversaturated somewhere):", round(tot, 1))
