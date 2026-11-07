"""Student-style sparring bot: lag."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import student_core
new_half, choose_action, on_hand_end = student_core.make_bot(open_pct=0.85, call_pct=0.75, threebet_pct=0.35, bet_eq=0.48, pot_eq=0.60, raise_eq=0.68, call_slack=0.02, bluff=0.40, bluff_river=0.30)
