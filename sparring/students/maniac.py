"""Student-style sparring bot: maniac (raises most hands, bluffs a lot, rarely folds)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import student_core
new_half, choose_action, on_hand_end = student_core.make_bot(open_pct=0.95, call_pct=0.90, threebet_pct=0.55, bet_eq=0.40, pot_eq=0.50, raise_eq=0.58, call_slack=-0.05, bluff=0.60, bluff_river=0.45)
