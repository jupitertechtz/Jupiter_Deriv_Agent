"""Adaptive Digit Engine v2.

An online-learning ensemble that predicts the next last digit, scores itself
walk-forward against the 10% baseline, and only says MATCH when the measured
evidence clears a strict gate. Otherwise it says SKIP or WAIT.

Five component models, each a probability over digits 0-9 (Laplace-smoothed):
  short        frequency over the last ~100 ticks
  long         frequency over the last ~1,000 ticks
  recency      exponentially weighted frequency (lambda ~0.97)
  transition1  P(next | last digit)
  transition2  P(next | last two digits)

After every tick each model is scored with log loss and the weights are updated
with the exponentiated-gradient (Hedge) rule, plus a small fixed share so no
model's weight collapses to zero and the ensemble can keep adapting.

Every tick the engine commits to a prediction BEFORE seeing the next digit, so the
prediction ledger is a genuine walk-forward test with no look-ahead.
"""
import math
from collections import deque
from dataclasses import dataclass

from stats import binom_sf

MODELS = ("short", "long", "recency", "transition1", "transition2")
BASELINE = 0.10
LOG2_10 = math.log2(10)


@dataclass(frozen=True)
class EngineParams:
    short_window: int = 100
    long_window: int = 1000
    recency_lambda: float = 0.97
    alpha: float = 1.0               # Laplace smoothing
    eta: float = 0.1                 # learning rate for model weights
    share: float = 0.01              # fixed share: keeps every model at >= share/5 weight
    ledger_size: int = 2000          # walk-forward predictions kept
    min_samples: int = 1000          # walk-forward predictions needed before trusting accuracy
    max_p: float = 0.01              # accuracy must be this unlikely under pure luck
    min_edge: float = 0.02           # P(best) - 10%
    min_separation: float = 0.005    # P(best) - P(second best)
    max_entropy: float = 0.99        # predictive entropy at/above this = uniform regime -> SKIP
    persistence: int = 30            # gate must pass on this many consecutive ticks before MATCH
    min_accuracy: float = 0.0        # walk-forward accuracy required; 0 = the break-even rate


class _Window:
    """Rolling hit-rate and mean predicted probability over the last k predictions."""

    def __init__(self, k: int):
        self.k, self.q = k, deque()
        self.hits = 0
        self.prob = 0.0

    def add(self, hit: bool, prob: float) -> None:
        self.q.append((hit, prob))
        self.hits += hit
        self.prob += prob
        if len(self.q) > self.k:
            h, p = self.q.popleft()
            self.hits -= h
            self.prob -= p

    @property
    def n(self) -> int:
        return len(self.q)

    def accuracy(self):
        return self.hits / self.n if self.n >= self.k else None


class AdaptiveDigitEngine:
    def __init__(self, params: EngineParams | None = None):
        self.p = params or EngineParams()
        self.short, self.short_counts = deque(), [0] * 10
        self.long, self.long_counts = deque(), [0] * 10
        self.rec = [BASELINE] * 10
        self.t1 = [[0] * 10 for _ in range(10)]
        self.t2: dict[tuple[int, int], list[int]] = {}
        self.prev: deque = deque(maxlen=2)
        self.weights = {m: 1 / len(MODELS) for m in MODELS}
        self.windows = {k: _Window(k) for k in (50, 100, 500, 1000)}
        self.ledger = _Window(self.p.ledger_size)    # all walk-forward predictions (capped)
        self.pending = None                          # (components, final, digit) for the next tick
        self.n = 0
        self.streak = 0                              # consecutive ticks the evidence gate has passed

    # ---------- component models ----------
    def _smooth(self, counts, total):
        a = self.p.alpha
        return [(c + a) / (total + 10 * a) for c in counts]

    def components(self) -> dict[str, list[float]]:
        uniform = [BASELINE] * 10
        comps = {
            "short": self._smooth(self.short_counts, len(self.short)),
            "long": self._smooth(self.long_counts, len(self.long)),
            "recency": list(self.rec),
            "transition1": uniform,
            "transition2": uniform,
        }
        if self.prev:
            row = self.t1[self.prev[-1]]
            comps["transition1"] = self._smooth(row, sum(row))
        if len(self.prev) == 2:
            row = self.t2.get(tuple(self.prev))
            if row:
                comps["transition2"] = self._smooth(row, sum(row))
        return comps

    def _blend(self, comps):
        w = self.weights
        return [sum(w[m] * comps[m][d] for m in MODELS) for d in range(10)]

    # ---------- learning ----------
    def update(self, digit: int) -> None:
        """Feed the next actual digit: score the pending prediction, learn, then predict again."""
        if self.pending is not None:
            comps, final, predicted = self.pending
            losses = {m: -math.log(max(comps[m][digit], 1e-12)) for m in MODELS}
            raw = {m: self.weights[m] * math.exp(-self.p.eta * losses[m]) for m in MODELS}
            z = sum(raw.values())
            k = len(MODELS)
            self.weights = {m: (1 - self.p.share) * raw[m] / z + self.p.share / k for m in MODELS}
            if self.n >= self.p.short_window:           # ledger starts once the models have data
                hit = predicted == digit
                for win in self.windows.values():
                    win.add(hit, final[predicted])
                self.ledger.add(hit, final[predicted])

        for q, counts, size in ((self.short, self.short_counts, self.p.short_window),
                                (self.long, self.long_counts, self.p.long_window)):
            q.append(digit)
            counts[digit] += 1
            if len(q) > size:
                counts[q.popleft()] -= 1
        lam = self.p.recency_lambda
        self.rec = [lam * r for r in self.rec]
        self.rec[digit] += 1 - lam
        if self.prev:
            self.t1[self.prev[-1]][digit] += 1
        if len(self.prev) == 2:
            self.t2.setdefault(tuple(self.prev), [0] * 10)[digit] += 1
        self.prev.append(digit)
        self.n += 1

        comps = self.components()
        final = self._blend(comps)
        self.pending = (comps, final, max(range(10), key=final.__getitem__))

    def fit(self, digits, breakeven: float | None = None) -> "AdaptiveDigitEngine":
        """Replay history. With a break-even rate, the gate is also checked on every replayed
        tick, so the 'held for N consecutive ticks' count reflects the history too."""
        warm = self.p.short_window + self.p.min_samples
        for d in digits:
            self.update(d)
            if breakeven is not None and self.n > warm:
                self.evaluate(breakeven, fast=True)
        return self

    # ---------- decision ----------
    def marginal_entropy(self) -> float:
        """Entropy of plain digit counts in the long window (1.0 = perfectly even)."""
        n = len(self.long)
        if not n:
            return 1.0
        return -sum((c / n) * math.log2(c / n) for c in self.long_counts if c) / LOG2_10

    def predictive_entropy(self) -> float:
        """Entropy of the ensemble's distribution for the NEXT digit (1.0 = no idea).

        This is the regime signal. Plain digit counts can be perfectly even while the
        sequence is still predictable (e.g. a digit tends to follow another), so the gate
        uses what the engine actually predicts, not just how often each digit appeared."""
        if self.pending is None:
            return 1.0
        return -sum(x * math.log2(x) for x in self.pending[1] if x > 0) / LOG2_10

    def _gate_streak(self, passed: bool, breakeven: float) -> int:
        """Count consecutive ticks on which the evidence gate passed (counted once per tick)."""
        key = (self.n, round(breakeven, 6))
        if getattr(self, "_streak_key", None) != key:
            self._streak_key = key
            self.streak = self.streak + 1 if passed else 0
        return self.streak

    def evaluate(self, breakeven: float = BASELINE, fast: bool = False) -> dict:
        """Current prediction plus the evidence for and against trading it.

        fast=True returns early with a minimal SKIP when the forecast is near uniform, for
        per-tick checks across many markets. Use the default for full reports."""
        if self.pending is None:
            return {"decision": "SKIP", "gate": "no_data", "reason": "No ticks yet.", "score": 0.0}
        _, final, digit = self.pending
        if fast:
            h_fast = self.predictive_entropy()
            if h_fast >= self.p.max_entropy:
                self._gate_streak(False, breakeven)
                return {"decision": "SKIP", "gate": "uniform", "digit": digit, "score": 0.0,
                        "reason": f"Next-digit forecast is near uniform (entropy {h_fast:.3f}).",
                        "p_best": max(final), "walk_forward_accuracy": self.ledger.hits / self.ledger.n if self.ledger.n else 0.0}
        ranked = sorted(final, reverse=True)
        p_best, p_second = ranked[0], ranked[1]
        edge, separation = p_best - BASELINE, p_best - p_second
        h = self.predictive_entropy()
        h_marginal = self.marginal_entropy()

        led = self.ledger
        samples = led.n
        wf_acc = led.hits / samples if samples else 0.0
        mean_pred = led.prob / samples if samples else BASELINE
        luck_p = binom_sf(led.hits, samples, BASELINE) if samples else 1.0
        calibration = max(0.0, 1 - abs(mean_pred - wf_acc) / mean_pred) if samples else 0.0
        reliability = wf_acc / BASELINE
        sample_conf = min(1.0, samples / self.p.min_samples)
        regime_conf = 1.0 if self.p.max_entropy >= 1 else min(1.0, max(0.0, (1 - h) / (1 - self.p.max_entropy)))
        score = p_best * reliability * calibration * sample_conf * regime_conf

        P = self.p
        required = P.min_accuracy if P.min_accuracy > 0 else breakeven
        if h >= P.max_entropy:
            decision, gate = "SKIP", "uniform"
            reason = f"Next-digit forecast is near uniform (entropy {h:.3f} ≥ {P.max_entropy}): no usable structure."
        elif samples < P.min_samples:
            decision, gate = "WAIT", "samples"
            reason = f"Only {samples} walk-forward predictions; needs {P.min_samples}."
        elif wf_acc <= required:
            decision, gate = "WAIT", "below_breakeven"
            reason = (f"Walk-forward accuracy {wf_acc:.1%} is not above the required {required:.1%}"
                      + (f" (break-even {breakeven:.1%})." if P.min_accuracy else " (break-even)."))
        elif luck_p >= P.max_p:
            decision, gate = "WAIT", "not_significant"
            reason = f"Accuracy {wf_acc:.1%} could be luck (p = {luck_p:.3f}, needs < {P.max_p})."
        elif edge < P.min_edge or separation < P.min_separation:
            decision, gate = "WAIT", "small_edge"
            reason = f"Edge {edge:+.1%} / separation {separation:.1%} below {P.min_edge:.0%} / {P.min_separation:.1%}."
        elif self._gate_streak(True, breakeven) < P.persistence:
            decision, gate = "WAIT", "persistence"
            reason = (f"Evidence has held for {self.streak} of the {P.persistence} consecutive ticks required "
                      f"(walk-forward accuracy {wf_acc:.1%}, luck p = {luck_p:.4f}).")
        else:
            decision, gate = "MATCH", "passed"
            reason = (f"Walk-forward accuracy {wf_acc:.1%} beats the required {required:.1%} over {samples} "
                      f"predictions (luck p = {luck_p:.4f}), edge {edge:+.1%}, held for {self.streak} ticks.")
        if gate not in ("persistence", "passed"):
            self._gate_streak(False, breakeven)

        acc = {str(k): w.accuracy() for k, w in self.windows.items()}
        return {
            "decision": decision, "gate": gate, "reason": reason,
            "digit": digit, "probabilities": [round(x, 4) for x in final],
            "p_best": round(p_best, 4), "edge": round(edge, 4), "separation": round(separation, 4),
            "entropy": round(h, 4), "marginal_entropy": round(h_marginal, 4), "samples": samples, "walk_forward_accuracy": round(wf_acc, 4),
            "rolling_accuracy": {k: (round(v, 4) if v is not None else None) for k, v in acc.items()},
            "luck_p": round(luck_p, 4), "breakeven": round(breakeven, 4), "required_accuracy": round(required, 4),
            "calibration": round(calibration, 3), "reliability": round(reliability, 3),
            "sample_confidence": round(sample_conf, 3), "regime_confidence": round(regime_conf, 3),
            "score": round(score, 5), "weights": {m: round(w, 3) for m, w in self.weights.items()},
            "ticks_seen": self.n, "gate_streak": self.streak, "persistence_required": P.persistence,
        }


def params_from_settings(s) -> EngineParams:
    return EngineParams(min_samples=s.adaptive_min_samples, max_p=s.adaptive_max_p, min_edge=s.adaptive_min_edge,
                        min_separation=s.adaptive_min_separation, max_entropy=s.adaptive_max_entropy,
                        persistence=s.adaptive_persistence, eta=s.adaptive_eta,
                        short_window=s.adaptive_short_window, long_window=s.adaptive_long_window,
                        recency_lambda=s.adaptive_recency_lambda,
                        ledger_size=max(2000, s.adaptive_min_samples), min_accuracy=s.adaptive_min_accuracy)


ADAPTIVE = "adaptive"
