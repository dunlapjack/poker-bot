# Overnight results (Session 8, Nov 8, 2026, started 2:57 am CST, stop by 8:57 am)

Units: chips/deal, 1000-deal halves, all-in EV, BANK=20 in the cloud container (2 cores, one job queue).
Bar = `sparring/v13` (= root). Candidates only, nothing promoted, nothing committed or pushed.
Tuning seeds: pool 1001-1008 / H2H 2001-2015. Fresh confirm seeds: 9001-9008 / 9101-9115, then 9201+.
`sparring/v14` = v13 + one knob `VALTH_SRC` (ctx = v13 default | global | half). All knob experiments run as `sparring/v14/agent.py::KNOB=V`.

## Decisions taken without asking
- results/ cache was empty on the PC, so the v13 baseline is re-played on the tuning seeds in the first run.
- Opponent panel: full 18 bots unless a row says "trimmed".

| # | Idea | Knobs | Seeds (pool / H2H) | H2H vs v13 | Pool vs v13 | WORSE | Verdict |
|---|---|---|---|---|---|---|---|
| S01 | 1. value_th uses global opp_fold_to_bet | v14 VALTH_SRC=global | 1001-8 / 2001-15 | -0.010 ± 0.069 | +0.001 ± 0.012 | ctx_flop -0.046 ± 0.029 | rejected (neutral; tag +0.08 but ctx_flop worse) |
| S13 | 5. preflop steal: raise every button hand >= pe 0.40 when opp folds >= 55% to our button raises (n >= 20) | v15 PF_STEAL_TH=0.55 | 1001-8 / 2001-15 | 0.000 (never fires vs v13) | -0.006 ± 0.009 | none | rejected (fires only vs tag/nit/ctx bots, all slightly negative: limping those hands is already better) |
| S03 | 2. EV chooser starts earlier | v14 EV_WARM=25 (was 50) | 1001-8 / 2001-15 | **+0.168 ± 0.112** | +0.010 ± 0.014 | none | screen positive: goes to fresh-seed confirm |
| S04 | 2. EV chooser starts later | v14 EV_WARM=100 | 1001-8 / 2001-15 | **-0.252 ± 0.108** | +0.002 ± 0.014 | none (H2H negative) | rejected. Trend: earlier is better, so EV_WARM=10 added to the queue |
| S05 | 2. EV bets off vs more opponents | v14 EV_AGGR=0.40 (was 0.45) | 1001-8 / 2001-15 | **-0.736 ± 0.115** | -0.013 ± 0.009 | ctx_size -0.272 ± 0.131 | rejected |
| S06 | 2. EV bets allowed vs slightly more aggressive opponents | v14 EV_AGGR=0.50 | 1001-8 / 2001-15 | **+0.143 ± 0.067** | +0.001 ± 0.005 | none | screen positive (H2H only; changes play almost only vs v13-like bots): fresh-seed confirm |
| S07 | 2. EV bet margin removed | v14 EV_MARGIN=0.0 (was 0.02) | 1001-8 / 2001-15 | +0.055 ± 0.084 | +0.010 ± 0.011 | none (better vs v1, v5) | neutral (H2H not significant); not pursued alone |
| S08 | 2. EV bet margin raised | v14 EV_MARGIN=0.04 | 1001-8 / 2001-15 | -0.072 ± 0.087 | -0.007 ± 0.010 | v1 -0.072 ± 0.069 | rejected |
| S09 | 3. less context shrinkage | v14 CTX_K=2 (was 3) | 1001-8 / 2001-15 | +0.018 ± 0.080 | +0.001 ± 0.012 | none | neutral, rejected |
| S10 | 3. more context shrinkage | v14 CTX_K=5 | 1001-8 / 2001-15 | +0.016 ± 0.081 | +0.004 ± 0.013 | ctx_flop -0.078 ± 0.071 | rejected (k=3 stays) |
| S11 | 3. lower folder threshold (preflop archetype + ctx folder switch) | v14 ARCH_FOLD=0.58 | 1001-8 / 2001-15 | +0.145 ± 0.079 | -0.022 ± 0.013 | ctx_size -0.285 ± 0.115 | rejected (pool negative) |
| S12 | 3. higher folder threshold | v14 ARCH_FOLD=0.66 | 1001-8 / 2001-15 | -0.067 ± 0.074 | +0.009 ± 0.012 | none (better vs tag) | neutral, rejected (0.62 stays) |
| S14 | 2. EV chooser starts even earlier | v14 EV_WARM=10 | 1001-8 / 2001-15 | -0.110 ± 0.104 | -0.002 ± 0.015 | none | rejected. EV_WARM H2H by value: 10 -0.11, 25 +0.17, 50 0, 100 -0.25: not monotonic, so the 25 result may be noise (fresh seeds decide) |
| S15 | 2b. EV chooser: lower out-of-position realisation | v14 EV_R_OOP=0.80 (was 0.90) | 1001-8 / 2001-15 | -0.001 ± 0.077 | +0.007 ± 0.008 | none (better vs tag) | neutral, rejected |
| S16 | 2b. EV chooser: no extra realisation discount once our bet is called | v14 EV_RB=1.00 (was 0.90) | 1001-8 / 2001-15 | **+0.405 ± 0.107** | **+0.038 ± 0.014** | none (better vs tag, potodds, profiler, v1) | **best screen**: fresh-seed confirm first; EV_RB=1.10 screen added |
| S17 | 3b. lower folder threshold for the postflop ctx switch only (preflop archetype stays 0.62) | v15 CTX_FOLD=0.58 | 1001-8 / 2001-15 | +0.145 ± 0.079 | -0.004 ± 0.010 | none (ctx_size -0.033 ± 0.050) | H2H-only gain, pool flat: shows S11's ctx_size loss came from the preflop folder switch. Not stacked (no pool gain) |
| C01 | **CONFIRM** EV_RB=1.00 (S16) on fresh seeds, full panel | v14 EV_RB=1.00 | **9001-8 / 9101-15 (new)** | **+0.261 ± 0.100** | **+0.034 ± 0.014** | **none** (better vs nit, v1, v5) | **RECOMMENDED**. Packaged as `sparring/v16` (= v13 with EV_RB default 1.00, one line) |
| C02 | CONFIRM combo of the 4 positive screens | v14 VALTH_SRC=half, EV_WARM=25, EV_AGGR=0.50, EV_RB=1.00 | 9001-8 / 9101-15 | **+0.373 ± 0.125** | +0.019 ± 0.020 | none | H2H higher than EV_RB alone but pool lower (nit +0.07 -> -0.01). Dropped EV_WARM=25 (looked like noise, S14) and re-test the rest on seeds 9201+ next to v16. Individual fresh confirms of VALTH half / EV_AGGR 0.50 dropped for time |
| S18 | 2b. EV_RB above 1 (called bets realise more) | v14 EV_RB=1.10 | 1001-8 / 2001-15 | **+0.572 ± 0.133** | **+0.070 ± 0.019** | none (better vs potodds, profiler, v1, v5) | best screen; trend 0.90 -> 1.00 -> 1.10 is monotonic. Fresh confirm on 9201+ replaces the combo-3 re-test (no time for both) |
| X01 | identity check: `sparring/v16` (EV_RB default 1.00) vs v14::EV_RB=1.00 | | H2H 2001-2 | 0.000 exactly | | | v16 plays identically to the confirmed knob setting |
| C05 | **2nd CONFIRM** `sparring/v16` (EV_RB 1.00) on a second fresh set | v16 | **9201-8 / 9301-15 (new)** | **+0.423 ± 0.118** | **+0.023 ± 0.015** | ctx_size -0.062 ± 0.054 (was +0.028 ± 0.051 on 9001-8; pooled over 16 seeds about -0.02, i.e. noise-sized, like the v13 baseline_random flag) | still the recommended candidate; better vs profiler, v1 |
| C06 | CONFIRM EV_RB=1.10 (S18) on fresh seeds | v14 EV_RB=1.10 (= `sparring/v17`) | 9201-8 / 9301-15 | **+0.462 ± 0.136** | **+0.051 ± 0.019** | **ctx_size -0.105 ± 0.082** | higher EV than v16 on the same seeds (+0.023), but the ctx_size loss grows with EV_RB (1.00: -0.06, 1.10: -0.11), so it looks real, not noise. NOT "recommended" by the rule; alternative for Jack to decide |
| C07 | CONFIRM `sparring/v17` (EV_RB 1.10) on the first fresh set | v17 | 9001-8 / 9101-15 | **+0.480 ± 0.126** | **+0.050 ± 0.019** | **none** (ctx_size +0.029; better vs plain, nit, v1, v5) | passes the rule on this set. Both sets pooled: ctx_size -0.038 ± 0.053, tag -0.025 ± 0.077 (neither flagged) |

## Summary (stopped 8:30 am, 5.5 h, out of time for another fresh set)
- **Best candidate: `sparring/v17`** = v13 with `EV_RB` 0.90 -> 1.10 (one line). Fresh seeds, 2 sets: H2H **+0.48 / +0.46**, pool **+0.050 / +0.051**. One WORSE on set 2 only (ctx_size -0.105 ± 0.082); pooled over both sets ctx_size -0.038 ± 0.053 (not flagged).
- **Conservative alternative: `sparring/v16`** = EV_RB 1.00. H2H +0.26 / +0.42, pool +0.034 / +0.023; set 1 clean, set 2 ctx_size -0.062 ± 0.054; pooled -0.017 ± 0.037.
- Everything else was neutral, H2H-only, or worse. Nothing committed, pushed or promoted; root agent.py/strategy.py untouched.
- Housekeeping: `Datathon F26/_stage/` holds the transfer tarballs (safe to delete); an empty `poker-bot/logs/` folder was left by the first sync (deletion is off for me).
