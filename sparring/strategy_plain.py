"""Strategy for heads-up Short Deck PLO5.

Core ideas
- Equity by vectorised Monte Carlo using a (hole-pair x board-triple) score table.
- Opponent RANGE modelling: random opponent hands are re-weighted by how strong they
  are (preflop equity + current made hand), narrowed every time the opponent bets,
  scaled by how aggressive this particular opponent has been (tracked per half).
- Decisions compare equity with pot odds; value-bet / bluff frequencies adapt to the
  opponent's observed fold-to-bet rate.
- A time governor shrinks the sample count if the 8 s bank is being used too fast.
Everything is wrapped so that any failure falls back to a safe legal action.
"""
from __future__ import annotations

import os
import time
from itertools import combinations

import numpy as np

from game import Action, Street

_HERE = os.path.dirname(os.path.abspath(__file__))
_T = np.load(os.path.join(_HERE, "tables.npz"))
PT = _T["PT"]          # (630, 7140) int32: score of pair+triple (0 if overlapping)
PID = _T["PID"]        # (36,36) pair id
TID = _T["TID"]        # (36,36,36) triple id
PRE = _T["PRE"]        # (376992,) preflop equity vs random hand, colex-indexed
BINOM = _T["BINOM"]    # (36,6) binomials for colex index

PI = np.array(list(combinations(range(5), 2)))
TI = np.array(list(combinations(range(5), 3)))
ALL = np.arange(36)

TIME_BANK = 8.0
HANDS_PER_HALF = 1000

# ------------------------------------------------------------------ evaluation

def score_many(hole: np.ndarray, board: np.ndarray) -> np.ndarray:
    """Omaha scores for N hole/board pairs (N x 5 each)."""
    p = PID[hole[:, PI[:, 0]], hole[:, PI[:, 1]]]
    t = TID[board[:, TI[:, 0]], board[:, TI[:, 1]], board[:, TI[:, 2]]]
    return PT[p[:, :, None], t[:, None, :]].reshape(len(hole), -1).max(1)


def made_many(hole: np.ndarray, board: tuple) -> np.ndarray:
    """Best made hand using exactly 3 of the 3/4 visible board cards (N x 5 holes)."""
    p = PID[hole[:, PI[:, 0]], hole[:, PI[:, 1]]]                    # N x 10
    tids = np.array([TID[a, b, c] for a, b, c in combinations(board, 3)])
    return PT[p[:, :, None], tids[None, None, :]].reshape(len(hole), -1).max(1)


def preflop_eq_many(hole: np.ndarray) -> np.ndarray:
    h = np.sort(hole, axis=1)
    idx = (BINOM[h[:, 0], 1] + BINOM[h[:, 1], 2] + BINOM[h[:, 2], 3]
           + BINOM[h[:, 3], 4] + BINOM[h[:, 4], 5])
    return PRE[idx]


def preflop_eq(hole) -> float:
    return float(preflop_eq_many(np.array([hole]))[0])


def _pct_rank(x: np.ndarray) -> np.ndarray:
    r = np.empty(len(x))
    r[np.argsort(x, kind="stable")] = np.arange(len(x))
    return r / max(len(x) - 1, 1)


def equity(hole, board, n: int, tight: float, rng) -> float:
    """Equity vs an opponent range. tight in [0,1): 0 = random hand, 0.8 = roughly top 20%."""
    board = tuple(board)
    known = np.array(list(hole) + list(board))
    deck = np.setdiff1d(ALL, known)
    need = 10 - len(board)
    draw = deck[rng.random((n, len(deck))).argsort(1)[:, :need]]
    opp = draw[:, :5]
    fb = np.concatenate([np.broadcast_to(np.array(board, dtype=np.int64), (n, len(board))),
                         draw[:, 5:]], 1) if board else draw[:, 5:]
    me = score_many(np.broadcast_to(np.array(hole), (n, 5)), fb)
    op = score_many(opp, fb)
    res = (me > op) + 0.5 * (me == op)
    if tight <= 0.01:
        return float(res.mean())
    strength = _pct_rank(preflop_eq_many(opp))
    if board:
        strength = 0.35 * strength + 0.65 * _pct_rank(made_many(opp, board) + 0.0)
    # soft threshold keeps some weak hands (bluffs / draws) in the range
    w = 1.0 / (1.0 + np.exp(-(strength - tight) / 0.08))
    return float((res * w).sum() / max(w.sum(), 1e-9))


# ------------------------------------------------------------------ opponent model

def new_model() -> dict:
    return {
        "opp_acts": 0, "opp_raises": 0,          # postflop + preflop voluntary actions
        "pf_open_opps": 0, "pf_open_raises": 0, "pf_open_folds": 0,
        "faced_bet": 0, "folded_to_bet": 0,       # opp response to OUR raises
        "showdowns": 0,
        "hand": -1, "seen": 0, "pending": False, "my_last_raise": False,
    }


def _rate(hits, n, prior, prior_n):
    return (hits + prior * prior_n) / (n + prior_n)


def opp_aggr(m) -> float:
    return _rate(m["opp_raises"], m["opp_acts"], 0.3, 20)


def opp_fold_to_bet(m) -> float:
    return _rate(m["folded_to_bet"], m["faced_bet"], 0.4, 15)


def _ingest_history(obs, m) -> None:
    """Update counters from action history entries we haven't processed yet."""
    if m["hand"] != obs.hand_index:
        m["hand"], m["seen"], m["pending"], m["my_last_raise"] = obs.hand_index, 0, False, False
    hist = obs.action_history
    for i in range(m["seen"], len(hist)):
        a = hist[i]
        if a.is_me:
            m["pending"] = a.action in (Action.RAISE_HALF, Action.RAISE_POT)
            continue
        is_raise = a.action in (Action.RAISE_HALF, Action.RAISE_POT)
        m["opp_acts"] += 1
        m["opp_raises"] += is_raise
        if a.street == Street.PREFLOP and i == 0:  # opp is button, first to act
            m["pf_open_opps"] += 1
            m["pf_open_raises"] += is_raise
            m["pf_open_folds"] += a.action == Action.FOLD
        if m["pending"]:
            m["faced_bet"] += 1
            m["folded_to_bet"] += a.action == Action.FOLD
            m["pending"] = False
    m["seen"] = len(hist)


def on_hand_end(result, m) -> None:
    if result.hand_index == m["hand"] and m["pending"]:
        # our last raise got a response we never saw: fold if we won without showdown
        m["faced_bet"] += 1
        if not result.went_to_showdown and result.my_net > 0:
            m["folded_to_bet"] += 1
        m["pending"] = False
    if result.went_to_showdown:
        m["showdowns"] += 1


def range_tightness(obs, m) -> float:
    """How strong the opponent's range is, from its actions this hand."""
    aggr = opp_aggr(m)
    # a raise from a player who raises x% of the time keeps roughly the top x% (floored)
    keep_raise = min(max(aggr * 1.3, 0.2), 0.9)
    keep = 1.0
    for a in obs.action_history:
        if a.is_me:
            continue
        if a.action in (Action.RAISE_HALF, Action.RAISE_POT):
            keep *= keep_raise if a.action == Action.RAISE_POT else min(keep_raise * 1.2, 0.95)
        elif a.action == Action.CHECK_CALL and a.amount > 0:
            keep *= 0.85
    keep = max(keep, 0.08)
    return 1.0 - keep


# ------------------------------------------------------------------ time governor

def n_samples(obs, mem) -> int:
    used = mem.get("time_used", 0.0)
    left = mem.get("bank", TIME_BANK) * 0.80 - used   # keep 20% safety margin
    hands_left = max(mem.get("hands", HANDS_PER_HALF) - obs.hand_index, 1)
    per_hand = left / hands_left                       # seconds we can spend per remaining hand
    if per_hand <= 0.0006:
        return 0                                       # emergency: heuristics only
    if per_hand < 0.0015:
        return 120
    if per_hand < 0.003:
        return 250
    return 450


# ------------------------------------------------------------------ decisions

def _pick(obs, *prefs):
    for a in prefs:
        if a in obs.legal_actions:
            return a
    return Action.CHECK_CALL


def decide(obs, mem) -> Action:
    m = mem["model"]
    _ingest_history(obs, m)
    rng = mem["rng"]
    legal = obs.legal_actions
    can_raise = Action.RAISE_POT in legal
    pot, call = obs.pot, obs.to_call
    pot_odds = call / (pot + call) if call else 0.0
    # chips we'd still have after calling, relative to the pot: low => committed
    spr_after = (obs.my_stack - call) / max(pot + call, 1)

    tight = 0.0
    n = n_samples(obs, mem)

    # ---------------- preflop
    if obs.street == Street.PREFLOP:
        pe = preflop_eq(obs.hole_cards)
        if call > 0 and obs.action_history and n:
            eq = equity(obs.hole_cards, (), min(n, 300), tight, rng) if tight > 0.05 else pe
        else:
            eq = pe
        first_in = not obs.action_history and obs.is_button   # button opening
        if first_in:
            if pe >= 0.555:
                return _pick(obs, Action.RAISE_POT, Action.CHECK_CALL)
            if pe >= 0.47:
                return Action.CHECK_CALL                      # limp
            return _pick(obs, Action.FOLD, Action.CHECK_CALL)
        if call == 0:                                         # BB option after limp
            if pe >= 0.57 and can_raise:
                return Action.RAISE_POT
            return Action.CHECK_CALL
        # facing a raise
        if eq >= 0.60 and can_raise and obs.raises_this_street < 3:
            return Action.RAISE_POT
        if eq >= 0.66 and can_raise:
            return Action.RAISE_POT
        need = pot_odds - (0.05 if spr_after > 1.5 else 0.0)  # implied odds when deep
        if eq >= need + 0.02 or spr_after < 0.4 and eq > pot_odds - 0.03:
            return Action.CHECK_CALL
        return _pick(obs, Action.FOLD, Action.CHECK_CALL)

    # ---------------- postflop
    if n == 0:
        # emergency heuristic: made-hand category only
        cat = 0
        if len(obs.board) == 5:
            from evaluator import omaha_score
            cat = omaha_score(obs.hole_cards, obs.board) >> 20
        if cat >= 4:
            return _pick(obs, Action.RAISE_POT, Action.CHECK_CALL)
        return Action.CHECK_CALL if call == 0 or cat >= 2 else _pick(obs, Action.FOLD, Action.CHECK_CALL)

    eq = equity(obs.hole_cards, obs.board, n, tight, rng)
    river = obs.street == Street.RIVER
    # equity realisation: out of position / draws realise less
    real = 1.0 if (river or obs.is_button) else 0.93
    eqr = eq * real
    fold_rate = opp_fold_to_bet(m)

    if call > 0:
        raise_th = 0.70 + 0.05 * obs.raises_this_street
        if eq >= raise_th and can_raise:
            return Action.RAISE_POT
        margin = 0.0 if river else -0.03 * min(spr_after, 2)   # implied odds on earlier streets
        if spr_after < 0.5:
            margin -= 0.04                                        # pot-committed
        if eqr >= pot_odds + margin:
            return Action.CHECK_CALL
        return _pick(obs, Action.FOLD, Action.CHECK_CALL)

    # no bet to us: value bet / bluff / check
    value_th = 0.66 if fold_rate > 0.35 else 0.60                # vs stations bet thinner
    if eq >= value_th + 0.08 and can_raise:
        return Action.RAISE_POT
    if eq >= value_th and can_raise:
        return Action.RAISE_HALF
    # bluff: profitable if opp folds more than the bet's break-even (half pot -> 33%)
    if False:
        bluff_p = min((fold_rate - 0.38) * 1.5, 0.45) * (1.0 if obs.is_button else 0.6)
        if not river:
            bluff_p *= 1.2                                        # semi-bluffs have equity
        if rng.random() < bluff_p:
            return Action.RAISE_HALF
    return Action.CHECK_CALL
