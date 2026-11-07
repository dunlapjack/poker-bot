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
| 2 | Exact SPR commitment engine: commit when equity >= SPR/(1+2·SPR) + margin; never bet-fold at SPR <= 1.5; test margins of +0/+3/+6 points | **done (v2)**: margin +3 best (pool +0.30 vs v1; +0 = +0.17, +6 = +0.24) |
| 3 | Preflop overhaul: open the button wide (~85–90%), BB defends ~70–80%, 3-bet the top ~15–18% by equity vs the opponent's range, 4-bet = all-in at >= ~55% vs the 3-bet range, preflop tables vs top 50/25/12% ranges | **done (v3)**: play 95% of buttons (raise top 22%, complete to pe 0.40), iso-raise limps at pe 0.52, 3-bet at eq 0.60 vs range, 4-bet+ = commit rule. Pool +0.86 vs v2. Widening the *raise* range hurt vs aggressive bots; widening the *limp* range was the win |
| 4 | Archetype classifier with bounded counters (maniac / station / check-folder / random), Beta priors, scaled by min(1, n/100), revert if the last 200 hands are below -0.5 bb/hand | **done (v4)**: folder (fold-to-bet >= 62%) -> bet/raise every hand; station (<= 22% and passive) -> thinner value, wider raises; conf = min(1, n/40); auto-off if last 150-200 hands < -0.5 bb. Pool +0.20 vs v3, never worse. Includes the **fold-tracking bug fix** (see below) |
| 5 | Sizing policy: pot when SPR <= 3, for value and vs stations; half-pot c-bets vs folders and on dry boards | **done (v5)** with GTO bluff threshold: bluff when fold-to-bet > 38% (half-pot break-even is 33%). Self-play +0.19 vs v4 |
| 6 | Range narrowing by action type, calibrated from showdowns (pot bet = top ~35% + observed bluff share) | |
| 7 | Nut / redraw / blocker features (nut flush, top set, discount non-nut flushes) | |
| 8 | Variance filter: take the lower-variance option in near-0-EV all-in spots vs unexploited opponents | |
| 9 | Bucketed preflop CFR (GTO-style) table, only if time remains and it beats #3 | |

## Key numbers
- SPR after a pot open = 6.2; 3-bet pot = 1.7; 4-bet pot = 0.24. Equity needed to stack off = SPR/(1+2·SPR): 46% / 39% / 16%.
- A half-pot bluff needs 33% folds; a pot-size bluff needs 50%.
- Paired flops: about 1/3 of random hands already have trips or better, so straights are bluff-catchers there.

## Session 2 results (Nov 7): v5 promoted to root
**Bug fixed (was in v1):** the opponent's fold-to-our-bet rate never counted folds, because our final raise isn't in `action_history` when the hand ends. `decide()` now marks `pending` itself. Before the fix the stat only saw calls, so every bluff/fold-based decision used a biased-low fold rate.

**Testing upgrades**
- `tools/gauntlet.py` now uses common random numbers (bot RNGs reseeded per decision), so identical bots score exactly 0 and A/B noise comes only from changed decisions.
- `tools/compare.py NEW OLD`: paired A/B on the same deals vs 11 opponents + head-to-head, 2 workers.
- `sparring/students/`: 5 "typical student" bots (tag, lag, nit, potodds, aggro_reg): preflop percentile + MC equity vs random hand. Sim-only (no HTTP server).

**v5 vs v1, fresh seeds** (compare, 3x400 deals, seeds 11-13): pool average **+1.18 ± 0.24 bb/deal**. Head-to-head vs v1 over 6,000 deals (seeds 31-36): **+0.27 ± 0.11**. vs tag +0.08 ± 0.19, vs nit +0.22 ± 0.16 (6,000 deals). Self-play: v5 vs v5 = 0.00, vs v4 +0.16 ± 0.10, vs v3 +0.12, vs v2 +0.10.
Time: 1.7-2.7 s per 1000-hand half on Jack's PC; real judge match vs always_pot used 1.8 s of 8 s, 0 errors. 18 tests pass.

**GTO notes applied:** stack-off threshold = SPR/(1+2·SPR); at SPR <= 4 play shove-or-fold; bluff break-even alpha = B/(P+B) (33% half pot, 50% pot), MDF = P/(P+B); exploit measured tendencies first, GTO frequencies only as the default vs unknown opponents.

**Next ideas:** #6 (range narrowing by action, calibrated from showdowns), #7 (nut/blocker features), maniac counter (call down wider vs always_pot/lag; still the noisiest matchup), #8 variance filter. Tuning was done on seeds 1-2; always confirm on fresh seeds.
