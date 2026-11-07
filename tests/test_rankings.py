"""Short-deck PLO5 ranking checks for both the official evaluator and our fast table."""
import os, sys
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from evaluator import cards_from_str as C, omaha_score, category_name
import strategy as S

def fast(h, b):
    return int(S.score_many(np.array([C(h)]), np.array([C(b)]))[0])

def both(h, b):
    s = omaha_score(C(h), C(b)); assert s == fast(h, b); return s

def test_wheel_is_lowest_straight():
    wheel = both("Ah 6c Kd Kc Qs", "7d 8s 9h Jc Js")     # A6 + 789 = A-6-7-8-9
    six_t = both("6h Tc Kd Kc Qs", "7d 8s 9h Jc Js")     # 6T + 789 = 6-T
    assert category_name(wheel) == "straight" and six_t > wheel

def test_trips_beat_straight():
    trips = both("9c 9d Ks Qs 6h", "9h 7c 8d Ah Jc")
    straight = both("Tc 6d Ks Qs Kh", "9h 7c 8d Ah Jc")
    assert category_name(trips) == "three of a kind" and category_name(straight) == "straight"
    assert trips > straight

def test_flush_beats_full_house():
    flush = both("Ah Kh 6c 7d 8s", "Th 9h 6h Tc 9d")
    boat = both("Tc Td Js Qs Ks", "Th 9h 6h Tc 9d".replace("Tc", "6s"))
    assert category_name(flush) == "flush" and category_name(boat) == "full house" and flush > boat

def test_quads_beat_flush():
    assert both("Qc Qd 6h 7s 8c", "Qh Qs Ah Kh Th") > both("7h 6h 6c 7s 8c", "Qh Qs Ah Kh Th")

def test_exactly_two_hole_cards():
    # four spades in hand + one spade on board is NOT a flush
    assert category_name(both("As Ks Qs Js 6d", "Ts 9c 8d 7h 6c")) != "flush"
    # one heart in hand + four on board is NOT a flush (guide example: K-high straight)
    s = both("Th 7s 7d 8c 9c", "Ah Kh Qh Jh 6c")
    assert category_name(s) == "straight"

def test_fast_table_matches_official_random():
    rng = np.random.default_rng(7)
    for _ in range(20000):
        c = rng.permutation(36)[:10]
        assert S.score_many(c[None, :5], c[None, 5:])[0] == omaha_score(list(c[:5]), list(c[5:]))
