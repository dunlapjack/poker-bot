"""Chunked, cached paired testing (Session 6, item 0).

Every (bot spec, opponent, deals, seed) match is one job whose per-deal all-in-EV list
is cached in results/<key>.json, so runs can be split across calls / restarts and the
baseline (e.g. v7) is never re-played for a new candidate.

  python tools/runpool.py run    NEW OLD [--pool 1001-1008] [--h2h 2001-2015] [--deals 1000]
  python tools/runpool.py report NEW OLD  (same args)  -> compare.py-style table

A bot spec is 'path' or 'path::KEY=VAL,KEY=VAL' (env knobs, see gauntlet.load_spec).
The cache key includes a hash of the bot folder's agent.py + strategy.py, so editing
a bot invalidates its old results automatically.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
import gauntlet  # noqa: E402

PANEL = [
    "sparring/plain_agent.py", "baseline-bots/baseline_random.py", "baseline-bots/baseline_always_pot.py",
    "baseline-bots/baseline_always_half.py", "baseline-bots/baseline_calling_station.py",
    "sparring/checkfold_agent.py", "sparring/students/tag.py", "sparring/students/lag.py",
    "sparring/students/nit.py", "sparring/students/potodds.py", "sparring/students/aggro_reg.py",
    "sparring/students/maniac.py", "sparring/students/profiler.py", "sparring/students/ctx_flop.py",
    "sparring/students/ctx_size.py", "sparring/v1/agent.py", "sparring/v5/agent.py", "sparring/v6/agent.py",
]
RES = os.path.join(ROOT, "results")


def bot_hash(spec):
    path, _, env = spec.partition("::")
    d = os.path.dirname(path)
    h = hashlib.md5()
    for f in (path, os.path.join(d, "strategy.py")):
        if os.path.exists(f):
            h.update(open(f, "rb").read())
    h.update(env.encode())
    return h.hexdigest()[:10]


def key(a, b, deals, seed):
    nm = lambda s: s.split("::")[0].replace("/", "_").replace(".py", "")
    bank = os.environ.get("BANK", "20")
    return f"{nm(a)}-{bot_hash(a)}__{nm(b)}-{bot_hash(b)}__{deals}_{seed}_B{bank}"


def job(args):
    a, b, deals, seed = args
    f = os.path.join(RES, key(a, b, deals, seed) + ".json")
    if os.path.exists(f):
        return f
    raw, ev, t, err = gauntlet.match(a, b, deals, seed)
    tmp = f + ".tmp"
    json.dump({"a": a, "b": b, "ev": ev, "raw": raw, "t": t, "err": err}, open(tmp, "w"))
    os.replace(tmp, f)
    return f


def load(a, b, deals, seed):
    f = os.path.join(RES, key(a, b, deals, seed) + ".json")
    return json.load(open(f)) if os.path.exists(f) else None


def rng(s):
    if "-" in s:
        x, y = map(int, s.split("-"))
        return list(range(x, y + 1))
    return [int(v) for v in s.split(",")]


def plan(a):
    jobs = []
    for s in a.h2h:
        jobs.append((a.new, a.old, a.deals, s))
    for s in a.pool:          # seed-major so partial runs cover every opponent evenly
        for o in a.opps:
            for c in (a.new, a.old):
                jobs.append((c, o, a.deals, s))
    seen, out = set(), []
    for j in jobs:
        if key(*j) not in seen:
            seen.add(key(*j)); out.append(j)
    return out


def stats(x):
    if len(x) < 2:
        return (x[0] if x else 0.0), float("nan")
    m = sum(x) / len(x)
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))
    return m, 1.96 * sd / math.sqrt(len(x))


def report(a):
    print(f"NEW={a.new}\nOLD={a.old}\n{a.deals}-deal halves, pool seeds {a.pool[0]}..{a.pool[-1]}, "
          f"h2h seeds {a.h2h[0] if a.h2h else '-'}..{a.h2h[-1] if a.h2h else '-'}")
    h = [load(a.new, a.old, a.deals, s) for s in a.h2h]
    h = [r for r in h if r]
    if h:
        m, ci = stats(sum((r["ev"] for r in h), []))
        print(f"{'HEAD-TO-HEAD new vs old':<24}{m:+8.3f} ±{ci:5.3f}   ({len(h)}/{len(a.h2h)} seeds, "
              f"{sum(len(r['ev']) for r in h)} deals)")
    print(f"{'opponent':<24}{'new':>8}{'old':>8}{'diff':>9}{'±':>7}  seeds")
    tot, tmax, errs, worse, opp_means = [], {a.new: 0, a.old: 0}, 0, [], []
    for o in a.opps:
        n, d, k = [], [], 0
        for s in a.pool:
            rn, ro = load(a.new, o, a.deals, s), load(a.old, o, a.deals, s)
            for r, c in ((rn, a.new), (ro, a.old)):
                if r:
                    tmax[c] = max(tmax[c], r["t"]); errs += r["err"]
            if rn and ro:
                n += rn["ev"]; d += [x - y for x, y in zip(rn["ev"], ro["ev"])]; k += 1
        if not d:
            continue
        tot += d
        m, ci = stats(d)
        opp_means.append(m)
        flag = "  WORSE" if m + ci < 0 else ("  better" if m - ci > 0 else "")
        if flag == "  WORSE":
            worse.append(os.path.basename(o))
        nm = stats(n)[0]
        print(f"{os.path.basename(o)[:23]:<24}{nm:+8.2f}{nm - m:+8.2f}{m:+9.3f}{ci:7.3f}  {k}{flag}")
    if tot:
        m, ci = stats(tot)
        print(f"{'POOL AVERAGE diff':<24}{'':16}{m:+9.3f}{ci:7.3f}")
    print(f"max time/half (s): new {tmax[a.new]:.2f}  old {tmax[a.old]:.2f}   errors {errs}   WORSE: {worse or 'none'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("new")
    ap.add_argument("old")
    ap.add_argument("--opps", nargs="*", default=PANEL)
    ap.add_argument("--deals", type=int, default=1000)
    ap.add_argument("--pool", type=rng, default=rng("1001-1008"))
    ap.add_argument("--h2h", type=lambda v: [] if v == "none" else rng(v), default=rng("2001-2015"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--budget", type=float, default=0, help="stop launching new jobs after this many seconds")
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    if a.cmd == "report":
        report(a)
        sys.exit()
    jobs = [j for j in plan(a) if not os.path.exists(os.path.join(RES, key(*j) + ".json"))]
    print(f"{len(jobs)} jobs to run", flush=True)
    t0 = time.time()
    with Pool(a.workers, maxtasksperchild=3) as p:
        for i, f in enumerate(p.imap_unordered(job, jobs), 1):
            print(f"[{time.time() - t0:6.0f}s] {i}/{len(jobs)} {os.path.basename(f)}", flush=True)
            if a.budget and time.time() - t0 > a.budget:
                p.terminate()
                break
    report(a)
