"""Strategy for heads-up Short Deck PLO5.

Core ideas
- Equity by vectorised Monte Carlo using a (hole-pair x board-triple) score table.
- Opponent RANGE modelling: random opponent hands are re-weighted by how strong they
  are (preflop equity + current made hand), narrowed every time the opponent bets,
  scaled by how aggressive this particular opponent has been (tracked per half).
- Decisions compare equity with pot odds; value-bet / bluff frequencies adapt to the
  opponent's observed fold-to-bet rate.
- A time governor shrinks the sample count if the 8 s bank is being used too fast.
Everything is wrapped so that any failure falls back to a safe legal action.
"""
from __future__ import annotations

import os
import time
from itertools import combinations

import numpy as np

from game import Action, Street

_HERE = os.path.dirname(os.path.abspath(__file__))
_T = np.load(os.path.join(_HERE, "tables.npz"))
PT = _T["PT"]          # (630, 7140) int32: score of pair+triple (0 if overlapping)
PID = _T["PID"]        # (36,36) pair id
TID = _T["TID"]        # (36,36,36) triple id
PRE = _T["PRE"]        # (376992,) preflop equity vs random hand, colex-indexed
BINOM = _T["BINOM"]    # (36,6) binomials for colex index

PI = np.array(list(combinations(range(5), 2)))
TI = np.array(list(combinations(range(5), 3)))
ALL = np.arange(36)

TIME_BANK = 8.0
COMMIT_MARGIN = float(os.environ.get("V2_MARGIN", "0.03"))   # idea #2: stack-off margin
PF_OPEN_RAISE = float(os.environ.get("PF_OPEN_RAISE", "0.555"))
PF_OPEN_LIMP = float(os.environ.get("PF_OPEN_LIMP", "0.40"))
PF_ISO = float(os.environ.get("PF_ISO", "0.52"))
PF_3BET = float(os.environ.get("PF_3BET", "0.60"))
PF_COMMIT_MARGIN = float(os.environ.get("PF_CM", "0.03"))
PF_IMPLIED = float(os.environ.get("PF_IMPLIED", "0.04"))
ARCH_N = float(os.environ.get("ARCH_N", "40"))
ARCH_FOLD = float(os.environ.get("ARCH_FOLD", "0.62"))
ARCH_STATION = float(os.environ.get("ARCH_STATION", "0.22"))
RAISE_TH = float(os.environ.get("RAISE_TH", "0.70"))
VALUE_HI = float(os.environ.get("VALUE_HI", "0.60"))
VALUE_LO = float(os.environ.get("VALUE_LO", "0.53"))
POT_GAP = float(os.environ.get("POT_GAP", "0.08"))
IMPLIED_POST = float(os.environ.get("IMPLIED_POST", "0.0"))
FOLD_SPLIT = float(os.environ.get("FOLD_SPLIT", "0.35"))
BLUFF_MIN = float(os.environ.get("BLUFF_MIN", "0.38"))
BLUFF_SLOPE = float(os.environ.get("BLUFF_SLOPE", "3.0"))
BLUFF_CAP = float(os.environ.get("BLUFF_CAP", "0.7"))
BLUFF_EQ = float(os.environ.get("BLUFF_EQ", "0.35"))
BLUFF_OOP = float(os.environ.get("BLUFF_OOP", "0.6"))
COMMIT_SPR = float(os.environ.get("V2_CSPR", "3.0"))          # use the engine at SPR <= this
CTX_ON = os.environ.get("CTX_ON", "1") == "1"                 # item 2: per-context fold stats drive the
CTX_K = float(os.environ.get("CTX_K", "3"))                   # folder/station switches (pseudo-obs per level)
EV_ON = os.environ.get("EV_ON", "1") == "1"                   # item 1: EV decides bluffs / thin bets
EV_R_IP = float(os.environ.get("EV_R_IP", "1.05"))
EV_R_OOP = float(os.environ.get("EV_R_OOP", "0.90"))
EV_MARGIN = float(os.environ.get("EV_MARGIN", "0.02"))        # bet only if EV beats check by this x pot
EV_WARM = int(os.environ.get("EV_WARM", "50"))               # hands of v7 logic before trusting stats
EV_RB = float(os.environ.get("EV_RB", "0.90"))                # extra realisation once a bet is called
EV_RAISE = os.environ.get("EV_RAISE", "1") == "1"             # model the opponent raising our bet
EV_AGGR = float(os.environ.get("EV_AGGR", "0.45"))            # no EV bets vs aggressive opponents
EV_STATION = os.environ.get("EV_STATION", "0") == "1"         # allow EV bets vs stations
N_TOP = int(os.environ.get("N_TOP", "450"))                    # MC samples when time allows
VALTH_SRC = os.environ.get("VALTH_SRC", "ctx")                # v14: fold rate for value_th: ctx (v13) | global | half
HANDS_PER_HALF = 1000

# ------------------------------------------------------------------ evaluation

def score_many(hole: np.ndarray, board: np.ndarray) -> np.ndarray:
    """Omaha scores for N hole/board pairs (N x 5 each)."""
    p = PID[hole[:, PI[:, 0]], hole[:, PI[:, 1]]]
    t = TID[board[:, TI[:, 0]], board[:, TI[:, 1]], board[:, TI[:, 2]]]
    return PT[p[:, :, None], t[:, None, :]].reshape(len(hole), -1).max(1)


def made_many(hole: np.ndarray, board: tuple) -> np.ndarray:
    """Best made hand using exactly 3 of the 3/4 visible board cards (N x 5 holes)."""
    p = PID[hole[:, PI[:, 0]], hole[:, PI[:, 1]]]                    # N x 10
    tids = np.array([TID[a, b, c] for a, b, c in combinations(board, 3)])
    return PT[p[:, :, None], tids[None, None, :]].reshape(len(hole), -1).max(1)


def preflop_eq_many(hole: np.ndarray) -> np.ndarray:
    h = np.sort(hole, axis=1)
    idx = (BINOM[h[:, 0], 1] + BINOM[h[:, 1], 2] + BINOM[h[:, 2], 3]
           + BINOM[h[:, 3], 4] + BINOM[h[:, 4], 5])
    return PRE[idx]


def preflop_eq(hole) -> float:
    return float(preflop_eq_many(np.array([hole]))[0])


def _pct_rank(x: np.ndarray) -> np.ndarray:
    r = np.empty(len(x))
    r[np.argsort(x, kind="stable")] = np.arange(len(x))
    return r / max(len(x) - 1, 1)


def equity(hole, board, n: int, tight: float, rng) -> float:
    """Equity vs an opponent range. tight in [0,1): 0 = random hand, 0.8 = roughly top 20%."""
    res, w, _ = equity_detail(hole, board, n, tight, rng)
    return float((res * w).sum() / max(w.sum(), 1e-9))


def equity_detail(hole, board, n: int, tight: float, rng):
    """Per-sample (result, range weight, opponent strength) for the item 1 EV chooser."""
    board = tuple(board)
    known = np.array(list(hole) + list(board))
    deck = np.setdiff1d(ALL, known)
    need = 10 - len(board)
    draw = deck[rng.random((n, len(deck))).argsort(1)[:, :need]]
    opp = draw[:, :5]
    fb = np.concatenate([np.broadcast_to(np.array(board, dtype=np.int64), (n, len(board))),
                         draw[:, 5:]], 1) if board else draw[:, 5:]
    me = score_many(np.broadcast_to(np.array(hole), (n, 5)), fb)
    op = score_many(opp, fb)
    res = (me > op) + 0.5 * (me == op)
    strength = _pct_rank(preflop_eq_many(opp))
    if board:
        strength = 0.35 * strength + 0.65 * _pct_rank(made_many(opp, board) + 0.0)
    if tight <= 0.01:
        return res, np.ones(n), strength
    # soft threshold keeps some weak hands (bluffs / draws) in the range
    w = 1.0 / (1.0 + np.exp(-(strength - tight) / 0.08))
    return res, w, strength


# ------------------------------------------------------------------ opponent model

def new_model() -> dict:
    return {
        "opp_acts": 0, "opp_raises": 0,          # postflop + preflop voluntary actions
        "pf_open_opps": 0, "pf_open_raises": 0, "pf_open_folds": 0,
        "faced_bet": 0, "folded_to_bet": 0,       # opp response to OUR raises
        "showdowns": 0,
        "hand": -1, "seen": 0, "pending": False, "my_last_raise": False,
        "nets": [], "exploit_off": False,
        "ctx": {},                                # item 2: (street, size, ip) -> [fold, call, raise]
        "pend_ctx": None,
    }


def _rate(hits, n, prior, prior_n):
    return (hits + prior * prior_n) / (n + prior_n)


def opp_aggr(m) -> float:
    return _rate(m["opp_raises"], m["opp_acts"], 0.3, 20)


def opp_fold_to_bet(m) -> float:
    return _rate(m["folded_to_bet"], m["faced_bet"], 0.4, 15)


def _ingest_history(obs, m) -> None:
    """Update counters from action history entries we haven't processed yet."""
    if m["hand"] != obs.hand_index:
        m["hand"], m["seen"], m["pending"], m["my_last_raise"] = obs.hand_index, 0, False, False
    hist = obs.action_history
    for i in range(m["seen"], len(hist)):
        a = hist[i]
        if a.is_me:
            m["pending"] = a.action in (Action.RAISE_HALF, Action.RAISE_POT)
            m["pend_ctx"] = (int(a.street), a.action == Action.RAISE_POT, bool(obs.is_button)) if m["pending"] else None
            continue
        is_raise = a.action in (Action.RAISE_HALF, Action.RAISE_POT)
        m["opp_acts"] += 1
        m["opp_raises"] += is_raise
        if a.street == Street.PREFLOP and i == 0:  # opp is button, first to act
            m["pf_open_opps"] += 1
            m["pf_open_raises"] += is_raise
            m["pf_open_folds"] += a.action == Action.FOLD
        if m["pending"]:
            m["faced_bet"] += 1
            m["folded_to_bet"] += a.action == Action.FOLD
            _ctx_add(m, 0 if a.action == Action.FOLD else (2 if is_raise else 1))
            m["pending"] = False
    m["seen"] = len(hist)


def _ctx_add(m, outcome) -> None:
    c = m.get("pend_ctx")
    if c is None:
        return
    m["ctx"].setdefault(c, [0, 0, 0])[outcome] += 1
    m["pend_ctx"] = None


def ctx_fold(m, street, pot_size=None, ip=None) -> float:
    """Item 2: opponent's fold rate to our bets, shrunk hierarchically
    global -> street -> street x size -> street x size x position (CTX_K pseudo-obs per level)."""
    f = opp_fold_to_bet(m)
    if not CTX_ON:
        return f
    st = int(street)
    levels = [lambda c: c[0] == st]
    if pot_size is not None:
        levels.append(lambda c: c[0] == st and c[1] == pot_size)
        if ip is not None:
            levels.append(lambda c: c[0] == st and c[1] == pot_size and c[2] == ip)
    for sel in levels:
        fo = n = 0
        for c, v in m["ctx"].items():
            if sel(c):
                fo += v[0]
                n += v[0] + v[1] + v[2]
        f = (fo + CTX_K * f) / (n + CTX_K)
    return f


def on_hand_end(result, m) -> None:
    if result.hand_index == m["hand"] and m["pending"]:
        # our last raise got a response we never saw: fold if we won without showdown
        m["faced_bet"] += 1
        folded = not result.went_to_showdown and result.my_net > 0
        if folded:
            m["folded_to_bet"] += 1
        _ctx_add(m, 0 if folded else 1)
        m["pending"] = False
    if result.went_to_showdown:
        m["showdowns"] += 1
    # safety: if the exploits are losing over the last 200 hands, switch them off
    m["nets"].append(result.my_net)
    if len(m["nets"]) > 200:
        m["nets"].pop(0)
    if len(m["nets"]) >= 150 and archetype(m)[0] != "none" and sum(m["nets"]) / len(m["nets"]) < -1.0:
        m["exploit_off"] = True


def range_tightness(obs, m) -> float:
    """How strong the opponent's range is, from its actions this hand."""
    aggr = opp_aggr(m)
    # a raise from a player who raises x% of the time keeps roughly the top x% (floored)
    keep_raise = min(max(aggr * 1.3, 0.2), 0.9)
    keep = 1.0
    for a in obs.action_history:
        if a.is_me:
            continue
        if a.action in (Action.RAISE_HALF, Action.RAISE_POT):
            keep *= keep_raise if a.action == Action.RAISE_POT else min(keep_raise * 1.2, 0.95)
        elif a.action == Action.CHECK_CALL and a.amount > 0:
            keep *= 0.85
    keep = max(keep, 0.08)
    return 1.0 - keep


def archetype(m):
    """Idea #4: bounded counter-strategies. Returns (kind, confidence 0..1)."""
    if m.get("exploit_off"):
        return "none", 0.0
    n = m["faced_bet"]
    f = opp_fold_to_bet(m)
    conf = min(1.0, n / ARCH_N)
    if n >= 12 and f >= ARCH_FOLD:
        return "folder", conf
    if n >= 12 and f <= ARCH_STATION and opp_aggr(m) < 0.4:   # passive non-folder (not a maniac)
        return "station", conf
    return "none", 0.0


# ------------------------------------------------------------------ time governor

def n_samples(obs, mem) -> int:
    used = mem.get("time_used", 0.0)
    left = mem.get("bank", TIME_BANK) * 0.80 - used   # keep 20% safety margin
    hands_left = max(mem.get("hands", HANDS_PER_HALF) - obs.hand_index, 1)
    per_hand = left / hands_left                       # seconds we can spend per remaining hand
    if per_hand <= 0.0006:
        return 0                                       # emergency: heuristics only
    if per_hand < 0.0015:
        return 120
    if per_hand < 0.003:
        return 250
    return N_TOP


# ------------------------------------------------------------------ decisions

def _pick(obs, *prefs):
    for a in prefs:
        if a in obs.legal_actions:
            return a
    return Action.CHECK_CALL


def decide(obs, mem) -> Action:
    a = _decide(obs, mem)
    # remember our own bet/raise so a fold that ends the hand is counted in on_hand_end
    # (bug fix: our final raise is never in action_history before the hand ends)
    m = mem["model"]
    m["pending"] = a in (Action.RAISE_HALF, Action.RAISE_POT)
    m["pend_ctx"] = (int(obs.street), a == Action.RAISE_POT, bool(obs.is_button)) if m["pending"] else None
    return a


def _cont_eq(res, w, strength, f):
    """Equity vs the part of the weighted range that does NOT fold (top 1-f by strength)."""
    if f <= 0.01:
        return float((res * w).sum() / max(w.sum(), 1e-9))
    o = np.argsort(strength, kind="stable")
    cw = np.cumsum(w[o]) / max(w.sum(), 1e-9)
    keep = np.zeros(len(res), bool)
    keep[o[cw > f]] = True
    if not keep.any():
        return 1.0
    return float((res[keep] * w[keep]).sum() / max(w[keep].sum(), 1e-9))


def ctx_raise(m, street, pot_size, ip) -> float:
    """Opponent's raise rate vs our bet, same hierarchical shrinkage as ctx_fold (prior 0.10)."""
    f = 0.10
    st = int(street)
    for sel in (lambda c: c[0] == st, lambda c: c[0] == st and c[1] == pot_size,
                lambda c: c[0] == st and c[1] == pot_size and c[2] == ip):
        r = n = 0
        for c, v in m["ctx"].items():
            if sel(c):
                r += v[2]
                n += v[0] + v[1] + v[2]
        f = (r + CTX_K * f) / (n + CTX_K)
    return f


def _band_eq(res, w, strength, lo, hi):
    """Equity vs the slice of the weighted range between cumulative-weight quantiles lo..hi."""
    o = np.argsort(strength, kind="stable")
    cw = np.cumsum(w[o]) / max(w.sum(), 1e-9)
    sel = o[(cw > lo) & (cw <= hi + 1e-9)]
    if len(sel) == 0:
        return None
    return float((res[sel] * w[sel]).sum() / max(w[sel].sum(), 1e-9))


def ev_choose(obs, m, res, w, strength, eq, spr, river):
    """Item 1: one-street EV table for CHECK/CALL, FOLD, RAISE_HALF, RAISE_POT.
    EV(bet b) = f*Pot + (1-f-r)*[E_cont*R*R_b*(Pot+b+c) - b] + r*max(-b, E_raise*R*R_b*(final pot) - (b+x))
    f, r = opponent's fold / raise rate to this size here (item 2 stats); E_cont = equity vs the
    middle of the range that calls, E_raise = vs the top r that raises; c = their call, x = their raise."""
    pot, call = obs.pot, obs.to_call
    R = 1.0 if (river or spr <= 1.0) else (EV_R_IP if obs.is_button else EV_R_OOP)
    R_eq = min(eq * R, 1.0)
    evs = {Action.CHECK_CALL: R_eq * (pot + call) - call}
    if call > 0:
        evs[Action.FOLD] = 0.0
    for act in (Action.RAISE_HALF, Action.RAISE_POT):
        if act not in obs.legal_actions:
            continue
        to = obs.raise_to.get(act) if isinstance(obs.raise_to, dict) else None
        if to is None:
            continue
        b = to - obs.my_bet                      # chips we add
        c = max(to - obs.opp_bet, 0)             # chips the opponent must add to call
        f = ctx_fold(m, obs.street, act == Action.RAISE_POT, bool(obs.is_button))
        if call > 0:
            f *= 0.6                             # folds to raises are rarer than folds to bets
        r = ctx_raise(m, obs.street, act == Action.RAISE_POT, bool(obs.is_button)) if EV_RAISE else 0.0
        r = min(r, max(1.0 - f - 0.05, 0.0))
        ec = _band_eq(res, w, strength, f, 1.0 - r)
        ec = min((ec if ec is not None else eq) * R * EV_RB, 1.0)
        ev = f * pot + (1 - f - r) * (ec * (pot + b + c) - b)
        if r > 0:
            er = _band_eq(res, w, strength, 1.0 - r, 1.0)
            er = eq if er is None else er
            er = min(er * R * EV_RB, 1.0)
            x = pot + b + 2 * c                  # rough size of a pot raise
            ev += r * max(-b, er * (pot + b + c + 2 * x) - (b + x))
        evs[act] = ev
    return evs


def _decide(obs, mem) -> Action:
    m = mem["model"]
    _ingest_history(obs, m)
    rng = mem["rng"]
    legal = obs.legal_actions
    can_raise = Action.RAISE_POT in legal
    pot, call = obs.pot, obs.to_call
    pot_odds = call / (pot + call) if call else 0.0
    # chips we'd still have after calling, relative to the pot: low => committed
    spr_after = (obs.my_stack - call) / max(pot + call, 1)

    tight = range_tightness(obs, m)
    n = n_samples(obs, mem)

    # ---------------- preflop (idea #3)
    if obs.street == Street.PREFLOP:
        pe = preflop_eq(obs.hole_cards)
        eff = min(obs.my_stack, obs.opp_stack + call)
        need_ai = eff / max(pot + 2 * eff - call, 1)
        first_in = not obs.action_history and obs.is_button   # button opening
        kind, conf = archetype(m)
        open_raise = PF_OPEN_RAISE - (0.025 if kind == "station" else 0.0)
        if first_in:
            if kind == "folder" and rng.random() < conf:
                return _pick(obs, Action.RAISE_POT, Action.CHECK_CALL)
            if pe >= open_raise:
                return _pick(obs, Action.RAISE_POT, Action.CHECK_CALL)
            if pe >= PF_OPEN_LIMP:
                return Action.CHECK_CALL                      # complete
            return _pick(obs, Action.FOLD, Action.CHECK_CALL)
        if call == 0:                                         # BB option after limp
            if can_raise and kind == "folder" and rng.random() < conf:
                return Action.RAISE_POT
            if pe >= PF_ISO and can_raise:
                return Action.RAISE_POT
            return Action.CHECK_CALL
        # facing a raise: equity vs the raiser's range
        eq = equity(obs.hole_cards, (), min(n, 300), tight, rng) if (n and tight > 0.05) else pe
        r = obs.raises_this_street
        if can_raise:
            if r >= 2 and eq >= need_ai + PF_COMMIT_MARGIN:
                return Action.RAISE_POT                       # 4-bet+ = get it in
            if r == 1 and eq >= PF_3BET:
                return Action.RAISE_POT                       # 3-bet for value
        need = pot_odds - (PF_IMPLIED if spr_after > 1.5 else 0.0)
        if eq >= need or eq >= need_ai:
            return Action.CHECK_CALL
        return _pick(obs, Action.FOLD, Action.CHECK_CALL)

    # ---------------- postflop
    if n == 0:
        # emergency heuristic: made-hand category only
        cat = 0
        if len(obs.board) == 5:
            from evaluator import omaha_score
            cat = omaha_score(obs.hole_cards, obs.board) >> 20
        if cat >= 4:
            return _pick(obs, Action.RAISE_POT, Action.CHECK_CALL)
        return Action.CHECK_CALL if call == 0 or cat >= 2 else _pick(obs, Action.FOLD, Action.CHECK_CALL)

    res_s, w_s, str_s = equity_detail(obs.hole_cards, obs.board, n, tight, rng)
    eq = float((res_s * w_s).sum() / max(w_s.sum(), 1e-9))
    river = obs.street == Street.RIVER
    # equity realisation: out of position / draws realise less
    real = 1.0 if (river or obs.is_button) else 0.93
    eqr = eq * real
    fold_rate = ctx_fold(m, obs.street)                         # street-level (item 2)
    fold_half = ctx_fold(m, obs.street, False, bool(obs.is_button))   # to OUR half-pot bet here

    # ---- SPR commitment engine (idea #2)
    eff = min(obs.my_stack, obs.opp_stack + call)            # chips that can still go in
    need_ai = eff / max(pot + 2 * eff - call, 1)             # equity to stack off right now
    spr_now = eff / max(pot, 1)
    committed = eq >= need_ai + COMMIT_MARGIN and spr_now <= COMMIT_SPR
    i_bet_street = any(a.is_me and a.street == obs.street and a.action in (Action.RAISE_HALF, Action.RAISE_POT)
                       for a in obs.action_history)
    if call > 0:
        if committed:
            return _pick(obs, Action.RAISE_POT, Action.CHECK_CALL)   # get it in
        if i_bet_street and spr_after <= 1.5 and eq >= pot_odds:
            return Action.CHECK_CALL                                  # never bet-fold shallow
    elif committed and can_raise:
        return Action.RAISE_POT                                       # build the pot to commit
    use_ev = EV_ON and obs.hand_index >= EV_WARM and not m.get("exploit_off")
    if call > 0:
        raise_th = RAISE_TH + 0.05 * obs.raises_this_street
        if eq >= raise_th and can_raise:
            return Action.RAISE_POT
        margin = 0.0 if river else -IMPLIED_POST * min(spr_after, 2)   # implied odds on earlier streets
        if spr_after < 0.5:
            margin -= 0.04                                        # pot-committed
        if eqr >= pot_odds + margin:
            return Action.CHECK_CALL
        return _pick(obs, Action.FOLD, Action.CHECK_CALL)

    # no bet to us: value bet / bluff / check
    kind, conf = archetype(m)
    if CTX_ON:                                               # item 2: context stats drive the switches
        kind, conf = "none", 0.0
        if not m.get("exploit_off"):
            if fold_half >= ARCH_FOLD:
                kind, conf = "folder", 1.0
            elif opp_fold_to_bet(m) <= ARCH_STATION and opp_aggr(m) < 0.4 and m["faced_bet"] >= 12:   # v13: global fold rate (v7 style)
                kind, conf = "station", 1.0
    fr_v = fold_rate if VALTH_SRC == "ctx" else (opp_fold_to_bet(m) if VALTH_SRC == "global" else fold_half)
    value_th = VALUE_HI if fr_v > FOLD_SPLIT else VALUE_LO        # vs stations bet thinner
    if kind == "station":
        value_th -= 0.03 * conf
    if kind == "folder" and can_raise and eq < value_th and rng.random() < conf:
        return Action.RAISE_HALF                                  # cheapest bet that wins the pot
    if eq >= value_th + POT_GAP and can_raise:
        return Action.RAISE_POT
    if eq >= value_th and can_raise:
        if kind == "station" or spr_now <= 3:
            return Action.RAISE_POT                               # idea #5: big value sizing
        return Action.RAISE_HALF
    if use_ev and can_raise and opp_aggr(m) < EV_AGGR and (EV_STATION or kind != "station"):
        # item 1: below value-bet strength, bet only when the EV table says it beats checking
        evt = ev_choose(obs, m, res_s, w_s, str_s, eq, spr_now, river)
        bets = {a: v for a, v in evt.items() if a in (Action.RAISE_HALF, Action.RAISE_POT)}
        if bets:
            a = max(bets, key=bets.get)
            if bets[a] > evt[Action.CHECK_CALL] + EV_MARGIN * pot:
                return a                                          # item 1: +EV bluff / thin bet
        return Action.CHECK_CALL
    # bluff: profitable if opp folds more than the bet's break-even (half pot -> 33%)
    # half-pot bluff breaks even at 33% folds (GTO alpha = B/(P+B)); bluff above that
    if can_raise and fold_half > BLUFF_MIN and eq < BLUFF_EQ:
        bluff_p = min((fold_half - 0.33) * BLUFF_SLOPE, BLUFF_CAP) * (1.0 if obs.is_button else BLUFF_OOP)
        if not river:
            bluff_p *= 1.2                                        # semi-bluffs have equity
        if rng.random() < bluff_p:
            return Action.RAISE_HALF
    return Action.CHECK_CALL
