"""Student-style sparring bot: nit."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import student_core
new_half, choose_action, on_hand_end = student_core.make_bot(open_pct=0.20, call_pct=0.20, threebet_pct=0.08, bet_eq=0.62, pot_eq=0.72, raise_eq=0.80, call_slack=0.15, bluff=0.0)
