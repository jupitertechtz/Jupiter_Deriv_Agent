"""Small, dependency-free statistics (keeps the Vercel bundle light)."""
import math


def chi2_sf(x: float, df: int) -> float:
    """P(Chi2_df >= x), via the regularized upper incomplete gamma Q(df/2, x/2)."""
    if x <= 0:
        return 1.0
    a, t = df / 2, x / 2
    if df % 2 == 0:
        term = total = 1.0
        for k in range(1, int(a)):
            term *= t / k
            total += term
        return min(1.0, math.exp(-t) * total)
    acc = sum(math.exp((k - 0.5) * math.log(t) - math.lgamma(k + 0.5)) for k in range(1, int(a + 0.5)))
    return min(1.0, math.erfc(math.sqrt(t)) + math.exp(-t) * acc)


def chisquare_uniform(counts) -> tuple[float, float]:
    n = sum(counts)
    expected = n / len(counts)
    stat = sum((c - expected) ** 2 / expected for c in counts)
    return stat, chi2_sf(stat, len(counts) - 1)


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    lp, lq, lfn = math.log(p), math.log1p(-p), math.lgamma(n + 1)
    total = 0.0
    for i in range(k, n + 1):
        term = math.exp(lfn - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
        total += term
        if i > n * p and term < 1e-17 * max(total, 1e-300):
            break
    return min(1.0, total)
