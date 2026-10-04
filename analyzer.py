"""Rolling last-digit statistics and digit-selection strategies.

Every strategy here is a HYPOTHESIS to test, not an edge. Deriv volatility
indices use an audited RNG, so each digit should hit ~10% of the time no
matter what the recent history looks like. The chi-square test tells you
whether an observed imbalance is bigger than chance would produce.
"""
import random
from collections import deque

from stats import chisquare_uniform


class DigitAnalyzer:
    def __init__(self, window: int = 500):
        self.window = window
        self.digits: deque = deque(maxlen=window)
        self._counts = [0] * 10

    def add(self, digit: int) -> None:
        if len(self.digits) == self.window:
            self._counts[self.digits[0]] -= 1
        self.digits.append(digit)
        self._counts[digit] += 1

    def extend(self, digits) -> None:
        for d in digits:
            self.add(d)

    @property
    def n(self) -> int:
        return len(self.digits)

    def counts(self) -> list[int]:
        return list(self._counts)

    def frequencies(self) -> list[float]:
        n = self.n or 1
        return [c / n for c in self._counts]

    def uniformity_p_value(self) -> float | None:
        """Chi-square p-value against 'all digits equally likely'. Low = more uneven than chance."""
        if self.n < 50:
            return None
        return chisquare_uniform(self._counts)[1]

    def coldest(self) -> int:
        lo = min(self._counts)
        return random.choice([d for d, c in enumerate(self._counts) if c == lo])

    def hottest(self) -> int:
        hi = max(self._counts)
        return random.choice([d for d, c in enumerate(self._counts) if c == hi])

    def summary(self, symbol: str) -> str:
        freqs = " ".join(f"{d}:{f*100:4.1f}%" for d, f in enumerate(self.frequencies()))
        p = self.uniformity_p_value()
        p_txt = "n/a" if p is None else f"{p:.3f}"
        return f"{symbol:<8} n={self.n:<6} p={p_txt:<6} {freqs}"


# Strategy = function(analyzer) -> digit to bet on.
STRATEGIES = {
    "coldest": lambda a: a.coldest(),          # "due" digit (gambler's fallacy)
    "hottest": lambda a: a.hottest(),          # "streaky" digit
    "repeat_last": lambda a: a.digits[-1],     # bet the last digit repeats
    "random": lambda a: random.randint(0, 9),  # baseline: every other strategy should match this
}


def rank_markets(results: dict[str, DigitAnalyzer]) -> str:
    """Rank markets by how uneven their digits are, with a multiple-comparison warning."""
    rows = sorted(results.items(), key=lambda kv: kv[1].uniformity_p_value() or 1.0)
    k = len(rows)
    bonferroni = 0.05 / max(k, 1)
    lines = [a.summary(sym) for sym, a in rows]
    flagged = [sym for sym, a in rows if (a.uniformity_p_value() or 1) < bonferroni]
    lines.append("")
    lines.append(f"Testing {k} markets: a raw p < 0.05 shows up by pure chance about "
                 f"{(1 - 0.95 ** k) * 100:.0f}% of the time. Corrected threshold: p < {bonferroni:.4f}.")
    lines.append("Markets beyond corrected threshold: " + (", ".join(flagged) if flagged else "none (digits look uniform)"))
    lines.append("Even a flagged market only matters if the imbalance persists on NEW data. Re-run before believing it.")
    return "\n".join(lines)
