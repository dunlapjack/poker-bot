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
| 6 | Range narrowing by action type, calibrated from showdowns (pot bet = top ~35% + observed bluff share) | tested in v6 work: showdown calibration hurt (-0.38); kept v5 range model |
| 7 | Nut / redraw / blocker features (nut flush, top set, discount non-nut flushes) | |
| 8 | Variance filter: take the lower-variance option in near-0-EV all-in spots vs unexploited opponents | |
| 9 | Bucketed preflop CFR (GTO-style) table, only if time remains and it beats #3 | **tested, rejected (Session 5)**: every variant lost to v7 |

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

## Session 3 results (Nov 7, evening): v6 promoted to root
**Maniac counter: tested, rejected (v5 is already at the optimum).** Against always_pot / always_half / lag / aggro_reg / a new `students/maniac.py`:
- Calling down wider (range loosened from showdown calibration): pool -0.38, worse vs all 4 maniacs (-0.7 to -1.3).
- Tightening further (x0.85 / x0.70 per raise): -0.43 / -2.03.
- Commit at any SPR vs maniacs (margin 0 / +3): -0.72 / -0.34.
Conclusion: the noise vs maniacs is variance from all-in pots (v5 already wins +8 to +13 bb/deal there), not a leak. Idea #6 in its "showdown calibration" form was tested this way and also hurt: preflop percentile at showdown misreads postflop made-hand raises.

**More Monte Carlo samples (900 vs 450): rejected.** Pool -0.02, thinking time almost doubled.

**Postflop threshold sweep (never tuned since v1) -> v6:**
| Variant | Pool diff vs v5 |
|---|---|
| raise_th 0.66 / 0.74 | +0.04 / -0.06 |
| value bets thinner (0.62/0.56) | +0.14 |
| value bets thicker (0.70/0.64) | -0.20 (worse vs stations) |
| pot-bet gap 0.04 | -0.01 |
| no postflop implied-odds discount | +0.17 |
| **thinner 0.60/0.53 + no implied odds (v6)** | **+0.29 (seeds 1-2), +0.35 ± 0.13 fresh seeds 11-13**, nothing worse |
Head-to-head: v6 vs v5 -0.02 ± 0.12 (even), v6 vs v1 +0.21 ± 0.14, self-play 0.00. Judge match vs calling station: 0 errors, 2.0-4.1 s of 8 s.

**Remaining ideas, by expected value:** #7 nut/blocker features (mostly captured by MC equity vs a strength-weighted range; low), #8 variance filter (helps win probability only, not EV; low), #9 preflop CFR (skip: no time to beat the tuned #3).

## Session 4 results (Nov 7, night): v7 promoted to root
Rule this session: only changes that test positive ship; everything else is removed from the code (not just switched off).

**Bluff / fold-to-bet sweep (vs v6, seeds 1-2):**
| Variant | Head-to-head | Pool | Verdict |
|---|---|---|---|
| bluff threshold 0.34 / 0.45 (was 0.38) | +0.04 / **-0.23** | 0.00 / +0.01 | rejected |
| **bluff slope 3.0, cap 0.7 (was 1.5 / 0.5)** | **+0.50 ± 0.17** | -0.01 | **accepted -> v7** |
| bluff with eq < 0.45 (was 0.35) | +0.11 | +0.01 | neutral, rejected |
| OOP bluffs at full rate | +0.13 | +0.01 | neutral, rejected |
| stations split at fold 0.45 | +0.16 | +0.03 | neutral, rejected |
| raise-bluffs facing a bet | **-0.55** | -0.09 (worse vs tag, nit) | rejected, code removed |
| archetype thresholds 0.55 / 0.28 | 0.00 | 0.00 | no effect |
| combined slope+eq+OOP | +0.50 | -0.03 (small dips vs tag/nit) | slope alone is cleaner |
v7 validation, fresh seeds 11-13: H2H vs v6 **+0.24 ± 0.12**, pool +0.01, nothing worse. 2,000-deal H2H (seeds 51-52): **vs v6 +0.44 ± 0.15, vs v5 +0.27 ± 0.20, vs v1 +0.53 ± 0.24**, self 0.00.

**Unpredictability / risk-taking: tested, all rejected.** New exploiter `students/profiler.py` profiles us (our fold-to-bet, showdown strength of our bets, preflop raise rate) and counter-adjusts, like a smart student bot would.
| Mixing (vs v7) | Pool | Note |
|---|---|---|
| all knobs low (10%) | -0.24 | worse vs maniac, station, always_half |
| all knobs high (25%) | -0.64 | worse vs 7 opponents |
| trap strong hands 15% | -0.15 | H2H -0.22, worse vs station |
| hero-call near-folds 15% | -0.07 | worse vs tag |
| raise limp hands 15% | -0.14 | worse vs v6, maniac |
| baseline bluffs 8% | +0.005 | +0.09 vs v6 but -0.13 vs profiler: neutral |
| swap bet sizes 15% | -0.04 | |
Why: the bot is already unpredictable where it matters. Its bluffs are random draws whose rate follows the opponent's measured fold rate, and Monte Carlo noise blurs every threshold. The profiler loses to v7 (+1.2 to +1.4 bb/deal). The larger bluff slope in v7 is the "less predictable" change that actually paid.

**Samples 300 instead of 450: neutral (-0.03 ± 0.09), rejected.** The time governor already protects the 8 s bank (v7 judge match: 3.8-4.0 s, 0 errors).

**#7 / #8 / #9 assessment:** #7 nut/blocker effects are already in the equity by construction (opponent hands are sampled from the deck minus our cards, so blockers count; range weights rank made hands, so better flushes/fulls are weighted up when the opponent raises). #8 is EV-neutral by design, so it can't pass the positive-only rule. #9 (preflop CFR) needs a solver for a 376,992-hand game; not feasible in the time left.


**Sample-count sweep (Session 4b, vs v7 at 450, fresh seeds 71-76, 2,400 deals per opponent):** 200: pool -0.14 ± 0.08 (worse vs lag, nit, aggro_reg) | 300: -0.04 ± 0.06 | 600: -0.04 ± 0.05 (worse vs plain) | 900: -0.05 ± 0.06 (worse vs aggro_reg). **450 stays.** None improved, so nothing changes.
**v7 vs baselines (3,000 deals each, seeds 81-83):** random +9.8, always_pot +8.1, always_half +12.9, calling_station +12.5, check-folder +1.49 (max ~1.5). 0 errors.

## Session 5 results (Nov 7, late): #9 preflop CFR tested, rejected (v7 stays)
`tools/build_cfr.py` (kept as a tool; no bot code changed): 40 PRE-percentile buckets, joint bucket frequency + showdown equity from 600k MC deals, preflop tree generated from `game.Game` (exact pot-limit sizes, 4-raise cap), vectorised CFR+ with linear averaging. Solves in ~5 s, exploitability < 0.001 chips/hand **inside the abstraction**. Flop-seen terminals pay pot x clip(E x real) to the button.
The solution depends heavily on `real`: button raises the top ~12% / ~25% / ~60% / ~70% at 0.95 / 1.00 / 1.05 / 1.10.
| Variant (vs v7, seeds 1-2, 400 deals) | H2H | Pool | WORSE vs |
|---|---|---|---|
| all, real 0.95 | -0.51 ± 0.27 | -0.39 ± 0.17 | always_pot, always_half, station, check-folder, tag |
| all, real 1.00 | -0.53 ± 0.31 | -0.40 ± 0.18 | always_half, check-folder, tag |
| hybrid (CFR only vs no archetype), 1.00 | -0.53 | -0.36 ± 0.17 | always_half, tag |
| all / hybrid, 1.05 | -0.54 | -0.42 / -0.50 | always_pot, always_half, tag, aggro_reg |
| all / hybrid, 1.10 | -0.67 | -0.75 / -0.89 | 5-6 opponents |
| button opening only, 1.00 | -0.16 ± 0.23 | -0.26 ± 0.13 | plain, always_half, station, check-folder, profiler |
Why: the abstraction treats postflop as "equity x pot", but our postflop play (range model, exploits, commitment engine) realises equity very differently by pot size and opponent type, and the opponents aren't GTO. The hand-tuned #3 thresholds were tuned against exactly that. No variant came close to 0, so no fresh-seed run.

**Thinking time:** a real match vs Minsky used 1.6 s of 8 s. More samples were already tested and don't add EV (Session 4b: 600 / 900 samples = -0.04 / -0.05 pool), so the spare time isn't a lever on its own.

## Session 6 results (Nov 7-8, night): research items 0-4. v12 = candidate, NOT promoted yet
Full results tables: `sparring/SESSION6_RESULTS.txt`. Units everywhere are **chips per deal** (1 bb = 2 chips; earlier sessions' "bb" numbers were chips too).
**Discord (Rishab, 9:22 PM):** in the real tournament the unit of execution is ONE half, and mirrored halves are paired. Nothing carries over between halves.

**Item 0, harness (done):** `tools/runpool.py run|report NEW OLD [--pool 1001-1008] [--h2h 2001-2015]` caches every match in `results/` (gitignored, keyed by a hash of the bot's files + knobs), uses real 1000-deal halves, an 18-bot panel (13 old + ctx_flop + ctx_size + v1/v5/v6) x 8 seeds, and 15,000 H2H deals. Bot specs can carry knobs: `path::K=V,K=V`. Fixes: (1) the all-in equity MC used a process-global RNG -> now seeded per deal (identical bots score exactly 0 again); (2) the container is ~2.5x slower than Jack's PC, so v7 sat near its time budget and concurrent jobs pushed the governor into low-sample/emergency play (one run was corrupted) -> the harness gives bots a **20 s bank** (`BANK` env; ~8 s on the PC); (3) Pool workers recycle (memory leak from re-loading bots). Control variate skipped: duplicate seats + CRN already cancel card luck, and paired diffs come from decision changes. Full-power candidate = ~12-14 min with the baseline cached.
**Item 2, per-context fold stats (ACCEPTED):** fold/call/raise counts keyed by (street, half|pot, position), hierarchical Beta shrinkage global -> street -> size -> position (k=3). "replace" = the folder/station switches use the context stats (folder if fold-to-our-half-pot-bet here >= 0.62). vs v7: alongside H2H +0.35 ± 0.07, pool +0.07 ± 0.01; **replace H2H +0.81 ± 0.07, pool +0.16 ± 0.02**. Main source: v-family bots fold ~90% to river half-pot bets.
**Item 3, frequency-matched narrowing (REJECTED):** keep = observed bet freq per (street, facing), showdown fallback. H2H +0.16 but pool -0.13 ± 0.03, WORSE vs 9; loosened (x1.4, floor 0.25): pool -0.09, WORSE vs 5. EHS potential not built (needs several runouts per sampled hand).
**Item 1, one-street EV chooser (ACCEPTED in "bluff" mode):** EV(bet) = f*Pot + (1-f-r)*[E_call*R*0.9*(Pot+b+c) - b] + r*max(-b, E_raise*R*0.9*(final pot) - (b+x)), with f, r from the item 2 stats, E_call / E_raise = equity vs range bands. Used only below value-bet strength (the EV table decides bluffs and thin bets; v7 keeps value bets and their sizing), after hand 50. vs v8-replace: H2H +1.01 ± 0.13, pool +0.14 ± 0.02. Rejected modes: full (over-bets; loses to stations), size-only (neutral), no raise branch (pot-bets 2.5x as often as v7).
**Item 4, Exp3 (REJECTED):** arms = base / RAISE_TH 0.66 / FOLD_SPLIT 0.45, eta 0.025, floor 4%, learned within a half: H2H +0.03 ± 0.08, pool +0.01 ± 0.02. A bandit can't beat the base without an arm that is better for some opponents.
**Re-tests at full power on top of items 1+2:** RAISE_TH 0.66 (H2H +0.05 ± 0.07, pool +0.008 ± 0.012, neutral), FOLD_SPLIT 0.45 (pool +0.014 ± 0.013 but WORSE vs ctx_flop). Screening-rejected (WORSE vs >= 1): POT_GAP 0.04, N_TOP 300, N_TOP 600. BLUFF_EQ / BLUFF_OOP / baseline bluffs are superseded by the EV bluff rule (they only act in the first 50 hands now).

**Fresh-seed confirmation (the decision):**
| Version | Seeds | H2H vs v7 | Pool vs v7 | WORSE |
|---|---|---|---|---|
| v11 = items 2+1 | 3001-8 / 4001-15 | **+1.48 ± 0.14** | **+0.31 ± 0.03** | plain -0.08, lag -0.12, maniac -0.10 |
| **v12** = v11 + no EV bets vs aggressive (aggr >= 0.45) or station opponents | 5001-8 / 6001-15 (new) | **+1.54 ± 0.14** | **+0.30 ± 0.03** | **plain -0.11 ± 0.06**, potodds -0.06 ± 0.06 |
Item 2 alone on fresh seeds: plain -0.03, lag -0.05, maniac -0.03 (not flagged). v12 vs v11 head-to-head: -0.14 ± 0.07 (v11 counts as "aggressive" so v12 turns off EV vs it); same pool.
vs v1 / v5 / v6 on fresh seeds: +1.07 / +1.73 / +1.29. Better vs tag, profiler, both ctx bots, checkfold.
**v12 on Jack's PC:** judge match vs always_pot: 1.28-1.41 s of 8 s, 0 errors; 18 tests pass.

## HANDOFF for the next session (start here)
**State:** root `agent.py`/`strategy.py` are still **v7** (commit ad62dde). `sparring/v12` is the candidate. Do NOT resubmit until Jack says the bot is final.
**Jack's decision needed:** promote v12? It's +1.5 H2H / +0.30 pool vs v7 on unseen seeds, but strictly fails the rule because of plain_agent (-0.11 ± 0.06, ~2% of our +5/deal edge vs it; consistent on every seed set) and potodds (-0.06, marginal).
**Next fix to try (v13, ~40 min):** the plain_agent loss comes from item 2 "replace" mode: station detection uses the street-level fold rate instead of the global one (plain folds 7% on the flop but 24% on the river, so on the river it isn't treated as a station). Make the station test use `opp_fold_to_bet(m)` (v7 style) and keep the context stats for the folder test. Run `runpool run sparring/v13/agent.py sparring/v12/agent.py` on 1001-1008 / 2001-2015, then v13 vs v7 on NEW seeds (7001-7008 / 8001-8015). Ship if no WORSE.
**Session 7 time budget (Jack's rule: state the expected time up front, give progress updates with time left, and name a ceiling):** setup + build v13 ~10 min, tuning run vs v12 ~14 min, v13 + v7 on new seeds 7001-7008 / 8001-8015 ~25 min, PC judge match + pytest + commit ~5 min. Expect ~55 min; **ceiling 90 min**. If v13 still has a WORSE opponent, stop and report; don't start more variants without asking.
**Promote steps:** copy `sparring/vN/strategy.py` to the root (agent.py root keeps PARTICIPANT), copy tables.npz if needed, `pytest -q tests test_agent.py`, one judge match, commit, push, resubmit with the new SHA (only when Jack says).
**Testing notes:** run long jobs in the cloud container (stage poker-bot/, `pip install fastapi uvicorn pytest`), never run other CPU jobs alongside a queue, keep `BANK=20` (default). `sparring/v10` holds every Session 6 experiment behind env knobs (CTX_MODE, RN_ON, EV_MODE, EV_RSTRICT, EXP3_ARMS, N_TOP, BASE_BLUFF) for reproducing the tables.
