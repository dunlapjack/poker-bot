"""A/B gauntlet: candidate bot vs a set of opponents, duplicate format, several seeds.

    python tools/gauntlet.py agent.py                     # default gauntlet
    python tools/gauntlet.py agent.py --deals 400 --seeds 1 2 3
    python tools/gauntlet.py agent.py --opps sparring/v1/agent.py

Uses ALL-IN EV: when stacks go in before the river, the chips are paid out by
exact/MC equity instead of the actual runout. Same expected value, much lower
variance, so A/B differences show up in far fewer hands. Also reports raw results.
"""
import argparse
import itertools
import math
import os
import random
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from game import AgentConfig, Game, Street, make_deal, BOARD_CARDS_VISIBLE  # noqa: E402
from sim import load_bot  # noqa: E402
import strategy as S  # noqa: E402

DEFAULT_OPPS = [
    "sparring/v1/agent.py",
    "sparring/plain_agent.py",
    "baseline-bots/baseline_random.py",
    "baseline-bots/baseline_always_pot.py",
    "baseline-bots/baseline_always_half.py",
    "baseline-bots/baseline_calling_station.py",
    "sparring/checkfold_agent.py",
]
_rng = np.random.default_rng(12345)


def allin_equity(h0, h1, known_board, rng=None):
    """Seat-0 equity with both hands known: exact for flop/turn, MC preflop."""
    known = list(h0) + list(h1) + list(known_board)
    deck = np.setdiff1d(np.arange(36), known)
    need = 5 - len(known_board)
    if need <= 2:
        runs = np.array(list(itertools.combinations(deck, need))) if need else np.zeros((1, 0), int)
    else:
        runs = deck[(rng or _rng).random((4000, len(deck))).argsort(1)[:, :need]]
    n = len(runs)
    kb = np.broadcast_to(np.array(known_board, dtype=np.int64), (n, len(known_board)))
    boards = np.concatenate([kb, runs], 1)
    a = S.score_many(np.broadcast_to(np.array(h0), (n, 5)), boards)
    b = S.score_many(np.broadcast_to(np.array(h1), (n, 5)), boards)
    return float(((a > b) + 0.5 * (a == b)).mean())


def play_half(bots, seed, deals, cfg):
    mems = [{}, {}]
    for b, m in zip(bots, mems):
        b.new_half(cfg, m)
    raw, aiev, times, errors = [], [], [0.0, 0.0], [0, 0]
    for i in range(deals):
        deal = make_deal(seed, i)
        g = Game(deal, button_seat=i % 2, hand_index=i)
        street_at_last = Street.PREFLOP
        while not g.is_terminal:
            s = g.to_act
            obs = g.observation(s)
            # common random numbers: same state -> same random stream, so A/B
            # differences come from decisions, not from Monte Carlo / bluff dice
            k = len(obs.action_history)
            r = mems[s].get("rng")
            if isinstance(r, np.random.Generator):
                mems[s]["rng"] = np.random.default_rng([seed, i, s, k])
            elif isinstance(r, random.Random):
                r.seed(seed * 1_000_003 + i * 101 + s * 17 + k)
            random.seed(seed * 1_000_003 + i * 101 + s * 17 + k)
            t = time.perf_counter()
            try:
                a = bots[s].choose_action(obs, mems[s])
                if a not in obs.legal_actions:
                    raise ValueError(f"illegal {a}")
            except Exception as e:  # noqa: BLE001
                errors[s] += 1
                if errors[s] <= 3:
                    print(f"   ERROR seat {s}: {e!r}")
                a = obs.legal_actions[1] if obs.to_call == 0 else obs.legal_actions[0]
            times[s] += time.perf_counter() - t
            street_at_last = g.street
            g.apply(a)
        for s in (0, 1):
            bots[s].on_hand_end(g.hand_result(s), mems[s])
        res = g.result()
        raw.append(res.nets[0])
        if res.went_to_showdown and street_at_last != Street.RIVER and 0 in g.stacks:
            kb = deal.board[:BOARD_CARDS_VISIBLE[street_at_last]]
            eq = allin_equity(deal.hole_cards[0], deal.hole_cards[1], kb,
                              np.random.default_rng([seed, i, 99]))   # same deal -> same payout
            aiev.append((eq - 0.5) * res.pot)       # equal stacks -> equal contributions
        else:
            aiev.append(res.nets[0])
    return raw, aiev, times, errors


def load_spec(spec, tag):
    """'path' or 'path::KEY=VAL,KEY2=VAL': env knobs are set only while this bot's
    strategy module is imported (knobs are read at import time)."""
    path, _, env = spec.partition("::")
    kv = dict(x.split("=", 1) for x in env.split(",") if x) if env else {}
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update(kv)
    try:
        return load_bot(path, tag)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def match(cand, opp, deals, seed):
    a, b = load_spec(cand, f"a{seed}"), load_spec(opp, f"b{seed}")
    # container is ~2.5x slower than the real hardware: scale the bank so the time
    # governor behaves as it would in the tournament (set BANK=8 to test throttling)
    cfg = AgentConfig(num_hands=deals, time_bank_seconds=float(os.environ.get("BANK", "20")))
    r1, v1, t1, e1 = play_half([a, b], seed, deals, cfg)
    r2, v2, t2, e2 = play_half([b, a], seed, deals, cfg)
    raw = [(x - y) / 2 for x, y in zip(r1, r2)]
    ev = [(x - y) / 2 for x, y in zip(v1, v2)]
    tmax = max(t1[0], t2[1]) * 1000 / deals
    return raw, ev, tmax, e1[0] + e2[1]


def stats(x):
    m = sum(x) / len(x)
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))
    return m, 1.96 * sd / math.sqrt(len(x))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cand")
    ap.add_argument("--opps", nargs="*", default=DEFAULT_OPPS)
    ap.add_argument("--deals", type=int, default=400)
    ap.add_argument("--seeds", type=int, nargs="*", default=[101, 202])
    args = ap.parse_args()
    print(f"{args.cand}: {args.deals} deals x {len(args.seeds)} seeds per opponent (bb/deal, 95% CI)")
    print(f"{'opponent':<32}{'all-in EV':>22}{'raw':>22}{'time/half':>11}{'err':>5}")
    for opp in args.opps:
        raw, ev, tmax, err = [], [], 0, 0
        for s in args.seeds:
            r, v, t, e = match(args.cand, opp, args.deals, s)
            raw += r; ev += v; tmax = max(tmax, t); err += e
        mv, hv = stats(ev)
        mr, hr = stats(raw)
        print(f"{os.path.basename(os.path.dirname(opp)) + '/' + os.path.basename(opp):<32}"
              f"{mv:+8.3f} ±{hv:6.3f}      {mr:+8.3f} ±{hr:6.3f}{tmax:9.2f}s{err:5d}", flush=True)
