"""Relaxation: every vehicle movement always green, no box/zebra conflicts, and every crossing
serves walkers every tick at zero vehicle cost. Physics (IDM, tail room, release at tick start,
1 head/lane/tick, right-turn/bike yielding) unchanged."""
from sim import City
class Relaxed(City):
    def signal(self, j, head, move): return "G"
    def may_go(self, v):
        saved = [(j.zebraPeds, j.box) for j in self.J]
        for j in self.J: j.zebraPeds = 0; j.box = {}
        try: return City.may_go(self, v)
        finally:
            for j, (z, b) in zip(self.J, saved): j.zebraPeds = z; j.box = b
    def start_tick(self):
        City.start_tick(self)          # vehicles (people skipped: stage is never "walk")
        for p in self.people:
            if p.waitJ is None: continue
            j = self.J[p.waitJ]
            self.crossed += 1
            p.waitJ = None; p.legWait = 0.0; p.onZebra = j.id; p.k = 0; j.zebraPeds += 1
