"""Context-split sparring bot: MODE=size (see ctx_split.py)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ctx_split
new_half, choose_action, on_hand_end = ctx_split.make("size")
