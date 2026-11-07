"""Shared core for 'typical student' sparring bots (sim/gauntlet only, no HTTP server).

Each bot is a style: preflop percentile thresholds on the preflop-equity table and
postflop Monte Carlo equity vs a RANDOM hand (what most teams will build first).
"""
import os
import sys
from itertools import combinations

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from game import Action, Street  # noqa: E402

_T = np.load(os.path.join(ROOT, "tables.npz"))
PT, PID, TID, PRE, BINOM = _T["PT"], _T["PID"], _T["TID"], _T["PRE"], _T["BINOM"]
PI = np.array(list(combinations(range(5), 2)))
TI = np.array(list(combinations(range(5), 3)))
ALL = np.arange(36)
PRE_SORTED = np.sort(PRE)


def pre_pct(hole):
    h = sorted(hole)
    idx = BINOM[h[0], 1] + BINOM[h[1], 2] + BINOM[h[2], 3] + BINOM[h[3], 4] + BINOM[h[4], 5]
    return float(np.searchsorted(PRE_SORTED, PRE[idx]) / len(PRE_SORTED))   # 0..1 percentile


def _score(hole, board):
    p = PID[hole[:, PI[:, 0]], hole[:, PI[:, 1]]]
    t = TID[board[:, TI[:, 0]], board[:, TI[:, 1]], board[:, TI[:, 2]]]
    return PT[p[:, :, None], t[:, None, :]].reshape(len(hole), -1).max(1)


def eq_random(hole, board, rng, n=250):
    known = np.array(list(hole) + list(board))
    deck = np.setdiff1d(ALL, known)
    need = 10 - len(board)
    draw = deck[rng.random((n, len(deck))).argsort(1)[:, :need]]
    fb = np.concatenate([np.broadcast_to(np.array(board, dtype=np.int64), (n, len(board))), draw[:, 5:]], 1) \
        if board else draw[:, 5:]
    me = _score(np.broadcast_to(np.array(hole), (n, 5)), fb)
    op = _score(draw[:, :5], fb)
    return float(((me > op) + 0.5 * (me == op)).mean())


def pick(obs, *prefs):
    for a in prefs:
        if a in obs.legal_actions:
            return a
    return Action.CHECK_CALL


def make_bot(open_pct, call_pct, threebet_pct, bet_eq, pot_eq, raise_eq, call_slack, bluff, bluff_river=None):
    """Return (new_half, choose_action, on_hand_end) for a style.
    *_pct are 'top X%' preflop; *_eq are equity-vs-random thresholds postflop."""
    bluff_river = bluff if bluff_river is None else bluff_river

    def new_half(config, memory):
        memory["rng"] = np.random.default_rng()

    def choose_action(obs, memory):
        rng = memory.setdefault("rng", np.random.default_rng())
        top = 1.0 - pre_pct(obs.hole_cards)          # 0 = best hand
        can_raise = Action.RAISE_POT in obs.legal_actions
        call = obs.to_call
        if obs.street == Street.PREFLOP:
            if call == 0:
                return pick(obs, Action.RAISE_POT) if top < threebet_pct else Action.CHECK_CALL
            first_in = not obs.action_history
            if first_in:
                if top < open_pct:
                    return pick(obs, Action.RAISE_POT, Action.CHECK_CALL)
                return pick(obs, Action.FOLD)
            if top < threebet_pct * (0.6 ** max(obs.raises_this_street - 1, 0)) and can_raise:
                return Action.RAISE_POT
            return Action.CHECK_CALL if top < call_pct else pick(obs, Action.FOLD)
        eq = eq_random(obs.hole_cards, obs.board, rng)
        pot_odds = call / (obs.pot + call) if call else 0
        if call > 0:
            if eq >= raise_eq and can_raise:
                return Action.RAISE_POT
            if eq >= pot_odds + call_slack:
                return Action.CHECK_CALL
            return pick(obs, Action.FOLD)
        if eq >= pot_eq and can_raise:
            return Action.RAISE_POT
        if eq >= bet_eq and can_raise:
            return Action.RAISE_HALF
        b = bluff_river if obs.street == Street.RIVER else bluff
        if can_raise and rng.random() < b:
            return Action.RAISE_HALF
        return Action.CHECK_CALL

    def on_hand_end(result, memory):
        pass

    return new_half, choose_action, on_hand_end
