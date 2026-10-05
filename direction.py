"""Adaptive Direction Engine for Rise/Fall contracts (CALL / PUT).

Same principles as the digit engine, applied to price direction:
  * five component models, each giving P(price is higher at expiry):
      short     momentum over the last 10 moves
      long      momentum over the last 100 moves
      recency   exponentially weighted share of up-moves (lambda 0.97)
      reversal  the opposite of short-term momentum
      transition  P(up at expiry | direction of the last move), learned from resolved outcomes
  * weights learn from log loss (Hedge update with a small fixed share)
  * every prediction is made before its outcome exists and is scored at the contract's real
    horizon (N ticks, or N seconds/minutes/hours of tick time)
  * the walk-forward ledger only counts NON-overlapping predictions, so the luck test is valid
  * a tie (exit == entry) is a loss for both Rise and Fall, as on Deriv

It says TRADE only when walk-forward accuracy beats the break-even rate, is very unlikely to be
luck against a 50% coin flip, the forecast is not near 50/50, and all of that has held for many
consecutive ticks. Otherwise WAIT or SKIP.
"""
import math
import random
from collections import deque
from dataclasses import dataclass

from markets import to_seconds
from stats import binom_sf

MODELS = ("short", "long", "recency", "reversal", "transition")
DIRECTION_STRATEGIES = ("adaptive", "momentum", "reversal", "random")


@dataclass(frozen=True)
class DirectionParams:
    eta: float = 0.1
    share: float = 0.01
    min_samples: int = 300           # resolved, non-overlapping predictions
    max_p: float = 0.01              # chance the accuracy is luck vs a 50% coin flip
    min_edge: float = 0.03           # forecast must be at least this far from 50%
    max_entropy: float = 0.995       # binary forecast entropy at/above this -> SKIP (|p-0.5| < ~0.04)
    persistence: int = 50            # consecutive new resolved predictions the gate must hold for


def _binary_entropy(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


class _Moves:
    def __init__(self, size):
        self.q, self.size, self.up, self.nz = deque(), size, 0, 0

    def add(self, move):
        self.q.append(move)
        self.up += move > 0
        self.nz += move != 0
        if len(self.q) > self.size:
            old = self.q.popleft()
            self.up -= old > 0
            self.nz -= old != 0

    def p_up(self):
        return (self.up + 1) / (self.nz + 2)


class DirectionEngine:
    def __init__(self, duration: int, unit: str, params: DirectionParams | None = None):
        self.p = params or DirectionParams()
        self.tick_h = duration if unit == "t" else None
        self.sec_h = None if unit == "t" else to_seconds(duration, unit)
        self.short, self.long = _Moves(10), _Moves(100)
        self.rec = 0.5
        self.trans = {1: [0, 0], -1: [0, 0], 0: [0, 0]}     # last move -> [ups, downs] at expiry
        self.weights = {m: 1 / len(MODELS) for m in MODELS}
        self.pending: deque = deque()                       # predictions awaiting their outcome
        self.ledger_open = False
        self.hits = self.samples = 0
        self.prob_sum = 0.0
        self.recent = deque(maxlen=100)                     # last 100 ledger hits
        self.n = 0
        self.prev_price = self.prev_time = None
        self.last_move = 0
        self.current = None                                 # (comps, p_up) for the next contract
        self.streak = 0
        self._streak_key = None

    # ---------- models ----------
    def components(self) -> dict[str, float]:
        ups, downs = self.trans[self.last_move]
        short = self.short.p_up()
        return {"short": short, "long": self.long.p_up(), "recency": self.rec, "reversal": 1 - short,
                "transition": (ups + 1) / (ups + downs + 2)}

    # ---------- learning ----------
    def _resolve(self, outcome: int, pred: dict) -> None:
        if outcome != 0:
            up = outcome > 0
            raw = {}
            for m in MODELS:
                pm = min(max(pred["comps"][m], 1e-6), 1 - 1e-6)
                loss = -math.log(pm if up else 1 - pm)
                raw[m] = self.weights[m] * math.exp(-self.p.eta * loss)
            z = sum(raw.values())
            self.weights = {m: (1 - self.p.share) * raw[m] / z + self.p.share / len(MODELS) for m in MODELS}
            self.trans[pred["last_move"]][0 if up else 1] += 1
        if pred["ledger"]:
            hit = outcome == pred["dir"]                    # a tie is a loss either way
            self.samples += 1
            self.hits += hit
            self.prob_sum += pred["p_dir"]
            self.recent.append(hit)
            self.ledger_open = False

    def update(self, t: float, price: float) -> None:
        # contracts start at the tick after they are made
        for pred in self.pending:
            if pred["entry"] is None:
                pred["entry"], pred["entry_t"], pred["entry_n"] = price, t, self.n
        # resolve contracts whose horizon has passed
        while self.pending and self.pending[0]["entry"] is not None:
            pred = self.pending[0]
            if self.tick_h is not None:
                if self.n - pred["entry_n"] < self.tick_h:
                    break
                exit_price = price
            else:
                if t <= pred["entry_t"] + self.sec_h:
                    break
                exit_price = self.prev_price                # last tick at or before expiry
            self.pending.popleft()
            self._resolve((exit_price > pred["entry"]) - (exit_price < pred["entry"]), pred)
        # features
        if self.prev_price is not None:
            move = (price > self.prev_price) - (price < self.prev_price)
            self.short.add(move)
            self.long.add(move)
            if move:
                self.rec = 0.97 * self.rec + 0.03 * (move > 0)
            self.last_move = move
        self.prev_price, self.prev_time = price, t
        self.n += 1
        # new prediction
        comps = self.components()
        p_up = sum(self.weights[m] * comps[m] for m in MODELS)
        direction = 1 if p_up >= 0.5 else -1
        ledger = not self.ledger_open
        if ledger:
            self.ledger_open = True
        self.pending.append({"comps": comps, "dir": direction, "p_dir": max(p_up, 1 - p_up), "ledger": ledger,
                             "last_move": self.last_move, "entry": None, "entry_t": None, "entry_n": None})
        self.current = (comps, p_up)

    def fit(self, times, prices, breakeven: float | None = None) -> "DirectionEngine":
        for t, p in zip(times, prices):
            self.update(t, p)
            if breakeven is not None and self.samples >= self.p.min_samples:
                self.evaluate(breakeven, fast=True)
        return self

    # ---------- decision ----------
    def _gate_streak(self, passed: bool, breakeven: float) -> int:
        """Count consecutive NEW resolved predictions on which the gate passed.

        Counting ticks would be too weak here: with an N-tick contract a fresh, non-overlapping
        prediction only resolves every ~N+1 ticks, so many ticks add almost no new evidence."""
        if not passed:
            self.streak = 0
            self._streak_key = (self.samples, round(breakeven, 6))
            return 0
        key = (self.samples, round(breakeven, 6))
        if self._streak_key != key:
            self._streak_key = key
            self.streak += 1
        return self.streak

    def evaluate(self, breakeven: float = 0.5, fast: bool = False) -> dict:
        if self.current is None:
            return {"decision": "SKIP", "gate": "no_data", "reason": "No ticks yet.", "score": 0.0}
        comps, p_up = self.current
        direction = "RISE" if p_up >= 0.5 else "FALL"
        p_dir = max(p_up, 1 - p_up)
        h = _binary_entropy(p_up)
        P = self.p
        if fast and h >= P.max_entropy:
            self._gate_streak(False, breakeven)
            return {"decision": "SKIP", "gate": "uniform", "direction": direction, "p_dir": p_dir, "score": 0.0,
                    "reason": f"Forecast is close to 50/50 (P = {p_dir:.1%})."}
        n = self.samples
        acc = self.hits / n if n else 0.0
        luck_p = binom_sf(self.hits, n, 0.5) if n else 1.0
        mean_pred = self.prob_sum / n if n else 0.5
        calibration = max(0.0, 1 - abs(mean_pred - acc) / mean_pred) if n else 0.0
        edge = p_dir - 0.5
        score = p_dir * (acc / 0.5) * calibration * min(1.0, n / P.min_samples) * \
            min(1.0, max(0.0, (1 - h) / (1 - P.max_entropy)))

        if h >= P.max_entropy:
            decision, gate = "SKIP", "uniform"
            reason = f"Forecast is close to 50/50 (P({direction.lower()}) = {p_dir:.1%}): no usable structure."
        elif n < P.min_samples:
            decision, gate = "WAIT", "samples"
            reason = f"Only {n} resolved walk-forward predictions; needs {P.min_samples}."
        elif acc <= breakeven:
            decision, gate = "WAIT", "below_breakeven"
            reason = f"Walk-forward accuracy {acc:.1%} is not above break-even {breakeven:.1%}."
        elif luck_p >= P.max_p:
            decision, gate = "WAIT", "not_significant"
            reason = f"Accuracy {acc:.1%} could be luck vs a coin flip (p = {luck_p:.3f}, needs < {P.max_p})."
        elif edge < P.min_edge:
            decision, gate = "WAIT", "small_edge"
            reason = f"Forecast {p_dir:.1%} is within {P.min_edge:.0%} of 50%."
        elif self._gate_streak(True, breakeven) < P.persistence:
            decision, gate = "WAIT", "persistence"
            reason = f"Evidence has held for {self.streak} of {P.persistence} consecutive new predictions."
        else:
            decision, gate = "TRADE", "passed"
            reason = (f"Walk-forward accuracy {acc:.1%} beats break-even {breakeven:.1%} over {n} predictions "
                      f"(luck p = {luck_p:.4f}); forecast {direction} at {p_dir:.1%}.")
        if gate not in ("persistence", "passed"):
            self._gate_streak(False, breakeven)
        recent = sum(self.recent) / len(self.recent) if self.recent else None
        return {
            "decision": decision, "gate": gate, "reason": reason, "direction": direction,
            "p_up": round(p_up, 4), "p_dir": round(p_dir, 4), "edge": round(edge, 4), "entropy": round(h, 4),
            "samples": n, "walk_forward_accuracy": round(acc, 4),
            "recent_accuracy": round(recent, 4) if recent is not None else None,
            "luck_p": round(luck_p, 4), "breakeven": round(breakeven, 4), "calibration": round(calibration, 3),
            "score": round(score, 5), "weights": {m: round(w, 3) for m, w in self.weights.items()},
            "ticks_seen": self.n, "gate_streak": self.streak, "persistence_required": P.persistence,
        }


def simple_direction(strategy: str, engine: DirectionEngine) -> int:
    """+1 Rise / -1 Fall for the simple strategies (no evidence gate)."""
    if strategy == "momentum":
        return 1 if engine.short.up * 2 >= engine.short.nz else -1
    if strategy == "reversal":
        return -1 if engine.short.up * 2 >= engine.short.nz else 1
    return random.choice((1, -1))


def _outcome(times, prices, i, duration, unit, tick_seconds=2.0):
    """Outcome of a contract bought at tick i: enters at tick i+1, exits per its duration."""
    e = i + 1
    if e >= len(prices):
        return None, None
    if unit == "t":
        x = e + duration
        if x >= len(prices):
            return None, None
        exit_i = x
    else:
        expiry = times[e] + to_seconds(duration, unit)
        exit_i = e
        while exit_i + 1 < len(prices) and times[exit_i + 1] <= expiry:
            exit_i += 1
        if exit_i + 1 >= len(prices):
            return None, None                                # history ends before expiry
    diff = prices[exit_i] - prices[e]
    return (diff > 0) - (diff < 0), exit_i


def backtest_direction(times, prices, strategy: str, duration: int, unit: str, stake: float, payout: float,
                       params: DirectionParams | None = None, gated: bool = True) -> dict:
    """Walk-forward Rise/Fall backtest with one open contract at a time."""
    engine = DirectionEngine(duration, unit, params)
    breakeven = stake / payout
    n = wins = ties = 0
    busy_until = -1
    rng_state = random.getstate()
    random.seed(7)
    for i, (t, p) in enumerate(zip(times, prices)):
        engine.update(t, p)
        if i <= busy_until or i < 120:
            continue
        if strategy == "adaptive" and gated:
            ev = engine.evaluate(breakeven, fast=True)
            if ev["decision"] != "TRADE":
                continue
            direction = 1 if ev["direction"] == "RISE" else -1
        elif strategy == "adaptive":
            direction = 1 if engine.current[1] >= 0.5 else -1
        else:
            direction = simple_direction(strategy, engine)
        outcome, exit_i = _outcome(times, prices, i, duration, unit)
        if outcome is None:
            break
        n += 1
        wins += outcome == direction
        ties += outcome == 0
        busy_until = exit_i
    random.setstate(rng_state)
    pnl = wins * (payout - stake) - (n - wins) * stake
    name = strategy if (strategy != "adaptive" or gated) else "adaptive_ungated"
    return {"strategy": name, "trades": n, "wins": wins, "ties": ties, "win_rate": wins / n if n else 0.0,
            "pnl": round(pnl, 2), "luck_p": binom_sf(wins, n, 0.5) if n else 1.0}


def params_from_settings(s) -> DirectionParams:
    return DirectionParams(min_samples=s.direction_min_samples, max_p=s.direction_max_p,
                           min_edge=s.direction_min_edge, max_entropy=s.direction_max_entropy,
                           persistence=s.direction_persistence)
