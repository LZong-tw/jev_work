import multiprocessing as mp, statistics as st, sim, best_policy as bp
B=dict(qw=0.1,walk_starve=12,down_w=0.15); R=dict(qw=0.3,walk_starve=6,down_w=0)
P1=dict(qw=0.12,walk_starve=11,down_w=0.18); P2=dict(qw=0.08,walk_starve=13,down_w=0.12)
def one(a):
    prm,s,p=a; return sim.run(bp.policy(**prm),seed=s,pre_ticks=p,keep_states=False)["score"]
if __name__=="__main__":
    seeds=[(s,2) for s in (41,42,43,44,45)]
    jobs=[(B,7,1),(R,7,1)]+[(c,s,p) for c in (B,R,P1,P2) for s,p in seeds]
    with mp.Pool(10) as pool: r=pool.map(one,jobs)
    print("seed7 best",r[0],"rule",r[1])
    g=[r[2+i*5:7+i*5] for i in range(4)]
    for n,x in zip("best rule pert1 pert2".split(),g): print(n,x,round(st.mean(x),1))
    d=[a-b for a,b in zip(g[0],g[1])]; print("best-rule",d,round(st.mean(d),1),round(st.stdev(d)/5**.5,1))
