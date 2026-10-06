"""Baseline: per crossing, pick the phase that releases the most this tick (W counts every waiting walker)."""
def make(wW=1.0, hold=0.5):
    def pol(history, cur):
        out = {}
        prev = history[-1]["lights_chosen"] if history else {}
        for c in cur["crossings"]:
            car, ppl = c["cars"], c["people"]
            ns, ew = ("north", "south"), ("east", "west")
            v = {"A": sum((car[s]["straight_right"] > 0) + (car[s]["bikes"] > 0) for s in ns),
                 "B": sum(car[s]["left"] > 0 for s in ns),
                 "C": sum((car[s]["straight_right"] > 0) + (car[s]["bikes"] > 0) for s in ew),
                 "D": sum(car[s]["left"] > 0 for s in ew),
                 "W": wW * sum(ppl.values())}
            p = prev.get(str(c["id"]))
            if p in v and p != "W": v[p] += hold   # vehicles already rolling toward a green
            out[c["id"]] = max(v, key=v.get)
        return out
    return pol
