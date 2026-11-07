"""Build lookup tables: PT[pair_id, triple_id] -> 5-card score (0 if overlapping)."""
import os, sys, time, numpy as np
from itertools import combinations
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evaluator import get_table
t=time.time()
tab = get_table()
pairs = list(combinations(range(36),2)); triples=list(combinations(range(36),3))
PID = np.full((36,36), -1, np.int16)
for i,(a,b) in enumerate(pairs): PID[a,b]=PID[b,a]=i
TID = np.full((36,36,36), -1, np.int16)
from itertools import permutations
for i,t3 in enumerate(triples):
    for p in permutations(t3): TID[p]=i
pm = np.array([(1<<a)|(1<<b) for a,b in pairs], dtype=object)
PT = np.zeros((len(pairs), len(triples)), np.int32)
tmasks = [(1<<a)|(1<<b)|(1<<c) for a,b,c in triples]
for i,(a,b) in enumerate(pairs):
    m=(1<<a)|(1<<b)
    row = PT[i]
    for j,tm in enumerate(tmasks):
        if not (m & tm): row[j]=tab[m|tm]
np.savez("tables_raw.npz", PT=PT, PID=PID, TID=TID)
print(PT.shape, time.time()-t)
