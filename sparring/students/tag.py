"""Student-style sparring bot: tag."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import student_core
new_half, choose_action, on_hand_end = student_core.make_bot(open_pct=0.45, call_pct=0.45, threebet_pct=0.15, bet_eq=0.58, pot_eq=0.68, raise_eq=0.78, call_slack=0.10, bluff=0.10)
