"""Context-split opponents for testing per-context stats (Session 6, item 0/2).

Base play is the TAG student. When facing a postflop bet, the response depends on
context, so a single fold-to-bet number misdescribes them:
  MODE=flop : folds the flop to any bet unless very strong; never folds the river.
  MODE=size : folds to pot-size bets unless strong; never folds to half-pot bets.
"""
import student_core as C
from student_core import Action, Street

_base_new, _base_act, _base_end = C.make_bot(open_pct=0.45, call_pct=0.45, threebet_pct=0.15, bet_eq=0.58,
                                             pot_eq=0.68, raise_eq=0.78, call_slack=0.10, bluff=0.10)


def make(mode):
    def choose_action(obs, memory):
        if obs.street != Street.PREFLOP and obs.to_call > 0:
            rng = memory.setdefault("rng", C.np.random.default_rng())
            eq = C.eq_random(obs.hole_cards, obs.board, rng)
            big = obs.to_call / max(obs.pot, 1) > 0.42          # pot-size bet faces 0.5, half-pot 0.33
            if mode == "flop":
                if obs.street == Street.FLOP:
                    return Action.CHECK_CALL if eq >= 0.66 else C.pick(obs, Action.FOLD)
                if obs.street == Street.RIVER:
                    return Action.CHECK_CALL
            else:
                if big:
                    return Action.CHECK_CALL if eq >= 0.62 else C.pick(obs, Action.FOLD)
                return Action.CHECK_CALL
        return _base_act(obs, memory)
    return _base_new, choose_action, _base_end
