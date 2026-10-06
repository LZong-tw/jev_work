import sim, collections
c = sim.City(123)
N = 20000; z = collections.Counter(); perJ = collections.Counter()
for _ in range(N):
    c.spawn_person(); p = list(c.people)[-1]; del c.people[p]
    zs = [l[1] for l in p.legs if l[1] is not None]
    z[len(zs)] += 1
    for q in zs: perJ[q] += 1
print("zebras/person dist", sorted(z.items()), "mean", sum(k*v for k, v in z.items())/N)
print("per crossing share", {k: round(v/N, 3) for k, v in sorted(perJ.items())})
