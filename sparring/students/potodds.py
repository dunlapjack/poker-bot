"""Student-style sparring bot: potodds."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import student_core
new_half, choose_action, on_hand_end = student_core.make_bot(open_pct=0.65, call_pct=0.65, threebet_pct=0.20, bet_eq=0.55, pot_eq=0.65, raise_eq=0.75, call_slack=0.0, bluff=0.15)
