"""Student-style sparring bot: aggro_reg."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import student_core
new_half, choose_action, on_hand_end = student_core.make_bot(open_pct=0.70, call_pct=0.60, threebet_pct=0.25, bet_eq=0.52, pot_eq=0.62, raise_eq=0.70, call_slack=0.04, bluff=0.28, bluff_river=0.18)
