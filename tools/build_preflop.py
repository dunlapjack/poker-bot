"""Rebuild the preflop equity table (~2 min). Run tools/build_tables.py first, from the repo root."""
import numpy as np, time
from itertools import combinations, permutations
from math import comb
t0=time.time()
d=np.load("tables_raw.npz"); PT,PID,TID=d["PT"],d["PID"],d["TID"]
PI=np.array(list(combinations(range(5),2))); TI=np.array(list(combinations(range(5),3)))
def score_np(hole,board):
    p = PID[hole[:,PI[:,0]], hole[:,PI[:,1]]]
    t = TID[board[:,TI[:,0]], board[:,TI[:,1]], board[:,TI[:,2]]]
    return PT[p[:,:,None], t[:,None,:]].reshape(len(hole),-1).max(1)
hands=list(combinations(range(36),5))
perms=list(permutations(range(4)))
canon={}; cls_of=np.empty(len(hands),np.int32); reps=[]
for i,h in enumerate(hands):
    best=min(tuple(sorted((c&~3)|p[c&3] for c in h)) for p in perms)
    k=canon.get(best)
    if k is None: k=canon[best]=len(reps); reps.append(best)
    cls_of[i]=k
print("classes",len(reps), time.time()-t0)
rng=np.random.default_rng(1)
N=3000
eq=np.empty(len(reps),np.float32)
for k,h in enumerate(reps):
    deck=np.setdiff1d(np.arange(36),h)
    idx=rng.random((N,31)).argsort(1)[:,:10]; dr=deck[idx]
    me=score_np(np.broadcast_to(np.array(h),(N,5)),dr[:,5:]); op=score_np(dr[:,:5],dr[:,5:])
    eq[k]=((me>op)+0.5*(me==op)).mean()
    if k%2000==0: print(k, time.time()-t0, flush=True)
PRE=eq[cls_of]   # indexed by colex rank of sorted 5-card hand = position in combinations order
# verify colex ordering = combinations lexicographic? build lex index function instead
np.save("preflop_eq.npy", PRE)
print("done", time.time()-t0, PRE.min(), PRE.max(), np.percentile(PRE,[10,50,90]))
