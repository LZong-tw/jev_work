"""Analytic arrival rates per crossing/lane/phase vs capacity (1 veh/lane/tick)."""
import sim, math
from sim import busy, WAVES, WAVE_CARS, WAVE_SIDE, TURN, PHASES
c = sim.City(7)
J = {(j.r, j.c): j.id for j in c.J}
def nxt(jid, head):
    j = c.J[jid]; r, cc = j.r, j.c
    dr, dc = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1)}[head]
    return J.get((r+dr, cc+dc))
CARM = {"L": .2, "S": .6, "R": .2}; BIKEM = {"S": .78, "R": .22}
def rates(minute):
    b = busy(minute); w = WAVES.get(int(minute // 60) % 24)
    mult = WAVE_CARS if w and w[0] else 1
    tot = 2.85 * b * mult                      # vehicles per tick
    ws = [WAVE_SIDE if w and w[0] and s.head in w[0] else 1 for s in c.ENTRIES]
    lane = {}                                  # (j, head, lane) -> rate/tick
    def go(jid, head, bike, p):
        if jid is None or p < 1e-9: return
        for m, q in (BIKEM if bike else CARM).items():
            ln = "B" if bike else ("L" if m == "L" else "S")
            lane[(jid, head, ln)] = lane.get((jid, head, ln), 0) + p*q
            h2 = TURN[head][m]; go(nxt(jid, h2), h2, bike, p*q)
    for s, wt in zip(c.ENTRIES, ws):
        r = tot * wt / sum(ws)
        go(s.to, s.head, False, r*0.6); go(s.to, s.head, True, r*0.4)
    return tot, lane
def util(lane, jid):
    need = {}
    for ph, (heads, moves) in list(PHASES.items())[:4]:
        lanes = ["L"] if moves == "L" else ["S", "B"]
        need[ph] = max(lane.get((jid, h, l), 0) for h in heads for l in lanes)
    return need
if __name__ == "__main__":
    print("hour  veh/tick  per-crossing rho=sum_phase max_lane_rate (A,B,C,D)  | veh-crossings/tick")
    for hh in range(9, 23):
        for half in (0, 30):
            m = hh*60 + half; tot, lane = rates(m + 1)
            row = []
            for jid in range(4):
                n = util(lane, jid); row.append(f"J{jid} {sum(n.values()):.2f}({n['A']:.2f},{n['B']:.2f},{n['C']:.2f},{n['D']:.2f})")
            vc = sum(lane.values())
            print(f"{hh:02d}:{half:02d} {tot:5.2f}  " + "  ".join(row) + f" | {vc:.2f} ({vc/tot:.2f}/veh)")
