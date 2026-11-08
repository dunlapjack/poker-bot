"""Exploiter sparring bot: profiles ITS OPPONENT (us) and counter-adjusts.

What a smart student team might build to beat predictable bots:
- tracks how often we fold to its bets  -> bluffs more if we over-fold, never if we call
- tracks how strong our bets are at showdown (preflop percentile of our cards when we
  bet/raised) -> folds more to our bets if they are always strong, calls more if we bluff
- tracks our preflop raise frequency -> defends tighter vs a tight raiser
Base play = TAG-ish thresholds from student_core.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import student_core as C  # noqa: E402
from student_core import Action, Street  # noqa: E402

RAISES = (Action.RAISE_HALF, Action.RAISE_POT)


def new_half(config, memory):
    memory.update(rng=np.random.default_rng(), faced=0, folded=0, pending=False, hand=-1, seen=0,
                  opp_bet_hand=False, sd_bet_n=0, sd_bet_pct=0.0, pf_opps=0, pf_raises=0)


def _ingest(obs, m):
    if m["hand"] != obs.hand_index:
        m.update(hand=obs.hand_index, seen=0, pending=False, opp_bet_hand=False)
    h = obs.action_history
    for i in range(m["seen"], len(h)):
        a = h[i]
        if a.is_me:
            m["pending"] = a.action in RAISES
            continue
        if a.action in RAISES:
            m["opp_bet_hand"] = True
        if a.street == Street.PREFLOP and i == 0:
            m["pf_opps"] += 1
            m["pf_raises"] += a.action in RAISES
        if m["pending"]:
            m["faced"] += 1
            m["folded"] += a.action == Action.FOLD
            m["pending"] = False
    m["seen"] = len(h)


def choose_action(obs, m):
    if "faced" not in m:
        new_half(None, m)
    _ingest(obs, m)
    rng = m["rng"]
    fold = (m["folded"] + 0.4 * 10) / (m["faced"] + 10)                 # their fold-to-bet
    bet_str = (m["sd_bet_pct"] + 0.6 * 8) / (m["sd_bet_n"] + 8)        # avg pct of their betting hands
    pf_raise = (m["pf_raises"] + 0.3 * 10) / (m["pf_opps"] + 10)
    top = 1.0 - C.pre_pct(obs.hole_cards)
    can_raise = Action.RAISE_POT in obs.legal_actions
    call = obs.to_call
    # the stronger their bets look at showdown, the more equity we demand to call
    slack = 0.05 + max(0.0, bet_str - 0.6) * 0.8 - max(0.0, 0.55 - bet_str) * 0.8
    bluff = min(max((fold - 0.35) * 1.8, 0.0), 0.7)

    def act(a):
        m["pending"] = a in RAISES
        return a

    if obs.street == Street.PREFLOP:
        if call == 0:
            return act(Action.RAISE_POT if (top < 0.2 and can_raise) else Action.CHECK_CALL)
        if not obs.action_history:                       # button first in
            if top < 0.35 or (rng.random() < bluff and can_raise):
                return act(C.pick(obs, Action.RAISE_POT, Action.CHECK_CALL))
            return act(Action.CHECK_CALL if top < 0.8 else C.pick(obs, Action.FOLD))
        defend = 0.55 - max(0.0, 0.3 - pf_raise)         # tighter vs a tight raiser
        if top < 0.12 and can_raise:
            return act(Action.RAISE_POT)
        return act(Action.CHECK_CALL if top < defend else C.pick(obs, Action.FOLD))
    eq = C.eq_random(obs.hole_cards, obs.board, rng)
    pot_odds = call / (obs.pot + call) if call else 0
    if call > 0:
        if eq >= 0.76 and can_raise:
            return act(Action.RAISE_POT)
        if eq >= pot_odds + slack:
            return act(Action.CHECK_CALL)
        return act(C.pick(obs, Action.FOLD))
    if eq >= 0.66 and can_raise:
        return act(Action.RAISE_POT)
    if eq >= (0.56 if fold > 0.3 else 0.52) and can_raise:
        return act(Action.RAISE_HALF)
    if can_raise and rng.random() < bluff:
        return act(Action.RAISE_HALF)
    return act(Action.CHECK_CALL)


def on_hand_end(result, m):
    if "faced" not in m:
        return
    if result.hand_index == m["hand"]:
        if m["pending"]:
            m["faced"] += 1
            m["folded"] += (not result.went_to_showdown and result.my_net > 0)
            m["pending"] = False
        if result.went_to_showdown and result.opp_hole and m["opp_bet_hand"]:
            m["sd_bet_n"] += 1
            m["sd_bet_pct"] += C.pre_pct(result.opp_hole)
