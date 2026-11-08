"""Idea #9: bucketed preflop CFR+ for heads-up short-deck PLO5 (80-chip stacks, 1/2 blinds).

    python tools/build_cfr.py --buckets 30 --deals 300000 --iters 3000 --real 1.05 --out sparring/v8/cfr.npz

1. Buckets: the 376,992 starting hands split into B equal-mass buckets by PRE percentile.
2. Monte Carlo deals give the joint bucket frequency P[b_btn, b_bb] (keeps card removal)
   and the showdown equity E[b_btn, b_bb] for the button.
3. Preflop tree is generated with game.Game itself (exact pot-limit sizes, 4-raise cap).
   Terminals: fold -> chips; all-in -> raw equity x pot; flop seen -> pot x realised share,
   button (in position postflop) share = clip(E * real), big blind gets the rest.
4. Vectorised CFR+ (regret floor 0, linear strategy averaging) over (node, bucket).
Output: bucket edges, node keys (preflop action strings), average strategies.
"""
import argparse
import copy
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from game import Action, Game, Street, make_deal  # noqa: E402
import strategy as S  # noqa: E402

ACTS = [Action.FOLD, Action.CHECK_CALL, Action.RAISE_HALF, Action.RAISE_POT]
CH = "fchp"   # history characters


def bucket_edges(B):
    return np.quantile(S.PRE, np.linspace(0, 1, B + 1)[1:-1])


def joint_tables(B, edges, deals, seed):
    rng = np.random.default_rng(seed)
    P = np.zeros((B, B))
    W = np.zeros((B, B))
    chunk = 50000
    done = 0
    while done < deals:
        n = min(chunk, deals - done)
        d = rng.random((n, 36)).argsort(1)[:, :15]
        h0, h1, bd = d[:, :5], d[:, 5:10], d[:, 10:]
        b0 = np.searchsorted(edges, S.preflop_eq_many(h0), side="right")
        b1 = np.searchsorted(edges, S.preflop_eq_many(h1), side="right")
        s0, s1 = S.score_many(h0, bd), S.score_many(h1, bd)
        w = (s0 > s1) + 0.5 * (s0 == s1)
        np.add.at(P, (b0, b1), 1)
        np.add.at(W, (b0, b1), w)
        done += n
    E = W / np.maximum(P, 1)
    E = np.where(P > 0, E, 0.5)
    return P / P.sum(), E


class Node:
    __slots__ = ("key", "player", "acts", "kids", "term", "pot", "contrib")


def build_tree(game, key, nodes):
    nd = Node()
    nd.key = key
    if game.is_terminal or game.street != Street.PREFLOP:
        nd.term = True
        r = game._result
        nd.contrib = tuple(game.contributed)
        nd.pot = game.pot
        if r is not None and not r.went_to_showdown:
            nd.player = ("fold", r.winner_seat)
        elif r is not None:                  # all-in preflop: ran out
            nd.player = ("allin", None)
        else:
            nd.player = ("flop", None)
        return nd
    nd.term = False
    nd.player = game.to_act
    nd.acts = [a for a in ACTS if a in game.legal_actions()]
    nd.kids = []
    for a in nd.acts:
        g = copy.deepcopy(game)
        g.apply(a)
        nd.kids.append(build_tree(g, key + CH[a], nodes))
    nodes.append(nd)
    return nd


def solve(root, nodes, P, E, real, iters, B):
    btn, bb = 0, 1                           # button = seat 0 in the tree
    idx = {nd.key: i for i, nd in enumerate(nodes)}
    regret = [np.zeros((B, len(nd.acts))) for nd in nodes]
    avg = [np.zeros((B, len(nd.acts))) for nd in nodes]
    # terminal utility matrices (button's chips, zero-sum), cached
    share_flop = np.clip(E * real, 0, 1)
    cache = {}

    def util(nd):
        k = nd.key
        if k not in cache:
            c0, c1 = nd.contrib
            kind, w = nd.player
            if kind == "fold":
                u = np.full((B, B), float(nd.pot - c0 if w == btn else -c0))
            elif kind == "allin":
                u = E * nd.pot - c0
            else:
                u = share_flop * nd.pot - c0
            cache[k] = u * P                 # weight by joint bucket probability
        return cache[k]

    def strat(i):
        r = regret[i]
        s = r.sum(1, keepdims=True)
        n = r.shape[1]
        return np.where(s > 0, r / np.where(s > 0, s, 1), 1.0 / n)

    def walk(nd, r0, r1, t):
        if nd.term:
            U = util(nd)
            return U @ r1, -(r0 @ U)          # cfv for button buckets, bb buckets
        i = idx[nd.key]
        sg = strat(i)
        p = nd.player
        v0 = np.zeros(B)
        v1 = np.zeros(B)
        kv = []
        for j, kid in enumerate(nd.kids):
            if p == btn:
                a0, a1 = walk(kid, r0 * sg[:, j], r1, t)
            else:
                a0, a1 = walk(kid, r0, r1 * sg[:, j], t)
            kv.append(a0 if p == btn else a1)
            v0 += a0
            v1 += a1
        kv = np.stack(kv, 1)                  # B x A (for acting player)
        mine = (kv * sg).sum(1)
        if p == btn:
            v0 = mine
            regret[i] = np.maximum(regret[i] + kv - mine[:, None], 0)
            avg[i] += t * r0[:, None] * sg
        else:
            v1 = mine
            regret[i] = np.maximum(regret[i] + kv - mine[:, None], 0)
            avg[i] += t * r1[:, None] * sg
        return v0, v1

    ones = np.ones(B)
    t0 = time.time()
    for t in range(1, iters + 1):
        v0, v1 = walk(root, ones, ones, t)
        if t % max(iters // 10, 1) == 0:
            print(f"iter {t}: button EV {v0.sum():+.4f} chips/hand  ({time.time()-t0:.0f}s)", flush=True)
    out = {}
    for i, nd in enumerate(nodes):
        a = avg[i]
        s = a.sum(1, keepdims=True)
        out[nd.key] = np.where(s > 0, a / np.where(s > 0, s, 1), 1.0 / a.shape[1])
    return out, v0.sum()


def best_response_value(root, nodes, strat, P, E, real, B):
    """Exploitability check: each player's best response EV vs the average strategy."""
    share_flop = np.clip(E * real, 0, 1)

    def util(nd):
        c0, c1 = nd.contrib
        kind, w = nd.player
        if kind == "fold":
            u = np.full((B, B), float(nd.pot - c0 if w == 0 else -c0))
        elif kind == "allin":
            u = E * nd.pot - c0
        else:
            u = share_flop * nd.pot - c0
        return u * P

    def br(nd, hero, r_opp):
        if nd.term:
            U = util(nd)
            return U @ r_opp if hero == 0 else -(r_opp @ U)
        sg = strat[nd.key]
        if nd.player == hero:
            return np.max(np.stack([br(k, hero, r_opp) for k in nd.kids], 1), 1)
        return sum(br(k, hero, r_opp * sg[:, j]) for j, k in enumerate(nd.kids))

    ones = np.ones(B)
    return br(root, 0, ones).sum(), br(root, 1, ones).sum()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", type=int, default=30)
    ap.add_argument("--deals", type=int, default=300000)
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--real", type=float, default=1.05)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tables", default="")
    ap.add_argument("--out", default="cfr.npz")
    a = ap.parse_args()
    B = a.buckets
    edges = bucket_edges(B)
    t0 = time.time()
    if a.tables and os.path.exists(a.tables):
        d = np.load(a.tables)
        P, E = d["P"], d["E"]
    else:
        P, E = joint_tables(B, edges, a.deals, a.seed)
        if a.tables:
            np.savez(a.tables, P=P, E=E)
    print(f"tables {time.time()-t0:.0f}s; E range {E.min():.3f}-{E.max():.3f}")
    nodes = []
    root = build_tree(Game(make_deal(0, 0), button_seat=0, hand_index=0), "", nodes)
    print(f"tree: {len(nodes)} decision nodes")
    strat, ev = solve(root, nodes, P, E, a.real, a.iters, B)
    b0, b1 = best_response_value(root, nodes, strat, P, E, a.real, B)
    print(f"button EV {ev:+.4f}; BR vs bb-strategy {b0:+.4f}, BR vs btn-strategy {b1:+.4f}; "
          f"exploitability {(b0 + b1) / 2:.4f} chips/hand")
    keys = sorted(strat)
    np.savez(a.out, edges=edges, keys=np.array(keys),
             **{f"s_{k or 'root'}": strat[k] for k in keys})
    r = strat[""]
    print("root (button) by bucket  fold/limp/half/pot:")
    for b in range(0, B, max(B // 10, 1)):
        print(f"  b{b:02d} " + " ".join(f"{x:.2f}" for x in r[b]))
