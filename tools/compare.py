"""Paired A/B: NEW vs OLD, each played against the same opponents on the same deals.

    python tools/compare.py sparring/v2/agent.py sparring/v1/agent.py --deals 500 --seeds 1 2 3 4

For every opponent it reports NEW's all-in EV, OLD's, and the paired difference
(NEW - OLD per deal, 95% CI). Also plays NEW vs OLD head-to-head.
Runs matches in parallel (2 workers by default).
"""
import argparse
import math
import os
import sys
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gauntlet  # noqa: E402

POOL = gauntlet.DEFAULT_OPPS[1:] + [
    "sparring/students/tag.py", "sparring/students/lag.py", "sparring/students/nit.py",
    "sparring/students/potodds.py", "sparring/students/aggro_reg.py", "sparring/students/maniac.py", "sparring/students/profiler.py",
]


def _job(args):
    cand, opp, deals, seed = args
    raw, ev, t, err = gauntlet.match(cand, opp, deals, seed)
    return cand, opp, seed, ev, t, err


def stats(x):
    m = sum(x) / len(x)
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / max(len(x) - 1, 1))
    return m, 1.96 * sd / math.sqrt(len(x))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("new")
    ap.add_argument("old")
    ap.add_argument("--opps", nargs="*", default=POOL)
    ap.add_argument("--deals", type=int, default=500)
    ap.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3, 4])
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--no-h2h", action="store_true")
    a = ap.parse_args()
    jobs = []
    if not a.no_h2h:
        jobs += [(a.new, a.old, a.deals * 2, s) for s in a.seeds]
    for o in a.opps:
        for c in (a.new, a.old):
            jobs += [(c, o, a.deals, s) for s in a.seeds]
    with Pool(a.workers) as p:
        res = p.map(_job, jobs, chunksize=1)
    by = {}
    tmax = {a.new: 0, a.old: 0}
    for cand, opp, seed, ev, t, err in res:
        by[(cand, opp, seed)] = ev
        tmax[cand] = max(tmax[cand], t)
        if err:
            print("ERRORS", cand, opp, seed, err)
    print(f"NEW={a.new}  OLD={a.old}  {a.deals} deals x {len(a.seeds)} seeds")
    if not a.no_h2h:
        h = sum((by[(a.new, a.old, s)] for s in a.seeds), [])
        m, ci = stats(h)
        print(f"{'HEAD-TO-HEAD new vs old':<28}{m:+8.3f} ±{ci:5.3f}")
    print(f"{'opponent':<28}{'new':>9}{'old':>9}{'diff':>10}{'±':>7}")
    tot = []
    for o in a.opps:
        n = sum((by[(a.new, o, s)] for s in a.seeds), [])
        d = sum(([x - y for x, y in zip(by[(a.new, o, s)], by[(a.old, o, s)])] for s in a.seeds), [])
        tot += d
        m, ci = stats(d)
        flag = "  WORSE" if m + ci < 0 else ("  better" if m - ci > 0 else "")
        print(f"{os.path.basename(o):<28}{stats(n)[0]:+9.3f}{stats(n)[0]-m:+9.3f}{m:+10.3f}{ci:7.3f}{flag}")
    m, ci = stats(tot)
    print(f"{'POOL AVERAGE diff':<28}{'':18}{m:+10.3f}{ci:7.3f}")
    print(f"max time/half (s): new {tmax[a.new]:.2f}  old {tmax[a.old]:.2f}")
