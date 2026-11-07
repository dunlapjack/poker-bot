"""Fast in-process duplicate match between two bot files (no HTTP).

    python tools/sim.py agent.py baseline-bots/baseline_random.py --deals 500 --seed 1

Reports bb/deal for bot A with a 95% CI, the verdict, and A's thinking time per half.
Use it for quick A/B tests; always confirm with judge_engine.py before submitting.
"""
import argparse
import importlib.util
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import AgentConfig, Game, make_deal  # noqa: E402


def load_bot(path, tag):
    """Load a bot file with its OWN strategy module (each bot dir may have a different one)."""
    full = os.path.join(ROOT, path)
    bot_dir = os.path.dirname(full)
    for name in ("strategy", "strategy_plain"):
        sys.modules.pop(name, None)          # force a fresh import from this bot's folder
    sys.path.insert(0, bot_dir)
    try:
        spec = importlib.util.spec_from_file_location(f"bot_{tag}_{abs(hash(full))}", full)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(bot_dir)
    return mod


def play_half(bots, seed, deals, cfg):
    """bots[0] sits in seat 0. Returns per-deal net chips for seat 0 and time per seat."""
    mems = [{}, {}]
    for b, m in zip(bots, mems):
        b.new_half(cfg, m)
    nets, times, errors = [], [0.0, 0.0], [0, 0]
    for i in range(deals):
        g = Game(make_deal(seed, i), button_seat=i % 2, hand_index=i)
        while not g.is_terminal:
            s = g.to_act
            obs = g.observation(s)
            t = time.perf_counter()
            try:
                a = bots[s].choose_action(obs, mems[s])
                if a not in obs.legal_actions:
                    raise ValueError(f"illegal {a}")
            except Exception as e:  # noqa: BLE001
                errors[s] += 1
                print("ERROR seat", s, e)
                a = obs.legal_actions[1] if obs.to_call == 0 else obs.legal_actions[0]
            times[s] += time.perf_counter() - t
            g.apply(a)
        for s in (0, 1):
            bots[s].on_hand_end(g.hand_result(s), mems[s])
        nets.append(g.result().nets[0])
    return nets, times, errors


def match(path_a, path_b, deals=500, seed=1, quiet=False):
    a, b = load_bot(path_a, "a"), load_bot(path_b, "b")
    cfg = AgentConfig(num_hands=deals)
    n1, t1, e1 = play_half([a, b], seed, deals, cfg)
    n2, t2, e2 = play_half([b, a], seed, deals, cfg)
    per = [(x - y) / 2 for x, y in zip(n1, n2)]       # bb per deal (two hands)
    mean = sum(per) / len(per)
    sd = math.sqrt(sum((p - mean) ** 2 for p in per) / (len(per) - 1))
    half = 1.96 * sd / math.sqrt(len(per))
    verdict = "WIN" if mean - half > 0 else "LOSS" if mean + half < 0 else "CHOP"
    scale = 1000 / deals
    if not quiet:
        print(f"{os.path.basename(path_a)} vs {os.path.basename(path_b)}: {mean:+.3f} bb/deal "
              f"[{mean - half:+.3f}, {mean + half:+.3f}] {verdict} | A time/half (scaled to 1000 hands): "
              f"{t1[0] * scale:.2f}s, {t2[1] * scale:.2f}s | errors A={e1[0] + e2[1]} B={e1[1] + e2[0]}")
    return mean, half, verdict


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--deals", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    match(args.a, args.b, args.deals, args.seed)
