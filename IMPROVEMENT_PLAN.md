# Bot improvement plan (start a new chat by pointing Claude at this file)

## Rules confirmed (Discord, 2:07 PM)
- Blinds don't count toward the 4-raise cap; all-ins that fall short of a full raise still count as a raise.
- `game.py` already does both, and the bot reads `raises_this_street`/`legal_actions` from the engine, so no change is needed.

## How we test (never submit a change that hasn't passed this)
1. Copy the current `agent.py` and `strategy.py` into a new folder, e.g. `sparring/v2/`, and edit **that** copy. The root `agent.py` keeps the real team name.
2. Run `python tools/gauntlet.py sparring/v2/agent.py --deals 400 --seeds 101 202`.
3. Accept a change only if it **beats v1** (all-in-EV confidence interval above 0) and doesn't get worse against any baseline. Time per half must stay at or under about 4 s.
4. Promote it: copy it to the root, keeping `PARTICIPANT`, and to `sparring/vN` as the new bar. Run `python -m pytest -q tests test_agent.py` and one real `judge_engine.py` match, then commit, push and resubmit with the new SHA.

`tests/test_rankings.py` checks the short-deck rankings (A6789 wheel, trips > straight, flush > full house, exactly 2 hole cards) and 20k random hands against the official evaluator. All pass.

## Baseline: v1 gauntlet (300 deals, seed 101, all-in-EV bb/deal)
| Opponent | v1 | Max / note |
|---|---|---|
| v1 (self) | -0.16 ± 0.35 | sanity check, about 0 as expected |
| plain (no range model) | +4.18 | |
| random | +6.33 | |
| always_pot (maniac) | **+2.83 ± 2.8** | weak and noisy: improve maniac handling |
| always_half | +9.28 | |
| calling_station | +7.97 | |
| check-folder | **+0.62** | the max is about +1.5: raise every hand vs folders |

## Ranked ideas (from the research report). Work in this order.
| # | Idea | Status |
|---|---|---|
| 1 | Ranking audit + duplicate gauntlet with all-in EV | **done** |
| 2 | Exact SPR commitment engine: commit when equity >= SPR/(1+2·SPR) + margin; never bet-fold at SPR <= 1.5; test margins of +0/+3/+6 points | next |
| 3 | Preflop overhaul: open the button wide (~85–90%), BB defends ~70–80%, 3-bet the top ~15–18% by equity vs the opponent's range, 4-bet = all-in at >= ~55% vs the 3-bet range, preflop tables vs top 50/25/12% ranges | |
| 4 | Archetype classifier with bounded counters (maniac / station / check-folder / random), Beta priors, scaled by min(1, n/100), revert if the last 200 hands are below -0.5 bb/hand | |
| 5 | Sizing policy: pot when SPR <= 3, for value and vs stations; half-pot c-bets vs folders and on dry boards | |
| 6 | Range narrowing by action type, calibrated from showdowns (pot bet = top ~35% + observed bluff share) | |
| 7 | Nut / redraw / blocker features (nut flush, top set, discount non-nut flushes) | |
| 8 | Variance filter: take the lower-variance option in near-0-EV all-in spots vs unexploited opponents | |
| 9 | Bucketed preflop CFR (GTO-style) table, only if time remains and it beats #3 | |

## Key numbers
- SPR after a pot open = 6.2; 3-bet pot = 1.7; 4-bet pot = 0.24. Equity needed to stack off = SPR/(1+2·SPR): 46% / 39% / 16%.
- A half-pot bluff needs 33% folds; a pot-size bluff needs 50%.
- Paired flops: about 1/3 of random hands already have trips or better, so straights are bluff-catchers there.
