# ShortStackShark: our heads-up Short Deck PLO5 bot

## How it plays
- **Preflop:** looks up a precomputed equity (vs a random hand) for all 376,992 starting hands (`tables.npz`).
- **Postflop:** Monte Carlo equity (about 450 samples, under 1 ms) using a NumPy table of every hole-pair × board-triple score.
- **Opponent range modeling:** random opponent hands are re-weighted by strength and narrowed each time the opponent bets or calls, scaled by how aggressive this opponent has been during the half. It's worth about +4 bb/deal over the same bot without it.
- **Decisions:** compares equity with pot odds, adjusted for implied odds, position and pot commitment. Value bets get thinner against calling stations, and it bluffs only against opponents who fold often.
- **Safety:** everything is in try/except with a fallback to a legal action, and a time governor cuts the sample count if the 8 s bank is draining too fast (about 3 s used now).

## Results (local)
| Opponent | bb/deal | Verdict |
|---|---|---|
| baseline_random | +5.3 | WIN |
| baseline_always_pot | +5.3 / +7.2 (judge) | WIN |
| baseline_always_half | +10.9 | WIN |
| baseline_calling_station | +7.6 | WIN |
| sparring/plain_agent (no range model) | +3.6 to +4.2 | WIN |

## Test
```
pip install fastapi==0.156.1 uvicorn==0.54.0 numpy
python -m pytest -q test_agent.py
python tools/sim.py agent.py baseline-bots/baseline_random.py --deals 500 --seed 1   # fast, no HTTP
python agent.py  /  python baseline-bots/baseline_always_pot.py  /  python judge_engine.py   # real judge
```
To A/B test a change: copy agent.py and strategy.py to `sparring/`, edit one of them, then run sim.py with the new version against the old one.

## Before submitting
1. Set `PARTICIPANT` in agent.py to your registered team name.
2. Push to a **public** repo. Submit the URL plus the full SHA from `git rev-parse HEAD`.
3. `tables.npz` must be committed (1 MB).
