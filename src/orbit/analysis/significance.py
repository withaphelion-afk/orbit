"""Is a pattern's hit rate better than chance? Reusable significance tools.

Primary null: circular shift of the event calendar.
    Keep the events' exact spacing, slide the whole calendar by k bars
    (wrapping around), and recompute the hit rate — for every k at least
    MIN_SHIFT_GAP_DAYS away from the real alignment. Shuffling dates
    uniformly would break the clustering of events (Mercury stations come in
    pairs, ingresses are evenly spaced) and ignore that markets trend, which
    makes random-date baselines look worse than they are and real patterns
    look better. The circular shift keeps both structures intact.

    Every shift is computed at once as a circular cross-correlation via FFT.

    With L bars there are only ~L distinct shifts, so the empirical p-value
    can't go below ~1/L. When fewer than TAIL_MIN_EXCEEDANCES null values
    reach the observed count, the p-value comes from a count distribution
    fitted to the null's mean and variance instead, floored at P_FLOOR. That's
    an approximation and is recorded as such in the run metadata.

Secondary check: uniformly random dates. The chance of k or more hits among n
    random distinct days, given K hit-days out of L, is exactly hypergeometric,
    so it's computed exactly rather than simulated. Reported, not corrected.

Multiple testing: Benjamini-Hochberg FDR across every test in a family.
"""

from __future__ import annotations

import math

import numpy as np

TAIL_MIN_EXCEEDANCES = 10
P_FLOOR = 1e-6


def shift_null_counts(target: np.ndarray, events: np.ndarray, min_gap: int) -> np.ndarray:
    """Hit counts for every circular shift of `events` against `target`.

    Both are 0/1 arrays over the same L bars. Element k of the circular
    cross-correlation is the number of shifted events (t -> t+k mod L) that
    land on a target bar. Shifts within `min_gap` of 0 (either side) are dropped.
    """
    L = len(target)
    corr = np.fft.irfft(np.fft.rfft(target, L) * np.conj(np.fft.rfft(events, L)), L)
    counts = np.rint(corr).astype(int)
    if L <= 2 * min_gap + 1:
        return counts[1:]
    return counts[min_gap : L - min_gap + 1]


def shift_p_value(observed_hits: int, null_hits: np.ndarray) -> float:
    """One-sided: probability the null reaches at least `observed_hits`.

    Empirical while the null has enough exceedances. Beyond the shift
    resolution, a count tail fitted to the null's own mean and variance:
    negative binomial when over-dispersed (the usual case, because overlapping
    forward windows make hits cluster), Poisson otherwise. Count tails are
    right-skewed like the real null; a normal tail is not and understates
    how often chance reaches a high count.
    """
    exceed = int(np.sum(null_hits >= observed_hits))
    empirical = (1 + exceed) / (1 + len(null_hits))
    if exceed >= TAIL_MIN_EXCEEDANCES or len(null_hits) < 30:
        return empirical
    mu, var = float(null_hits.mean()), float(null_hits.var())
    if mu <= 0:
        return empirical
    tail = negbinom_sf(observed_hits, mu, var) if var > mu else poisson_sf(observed_hits, mu)
    return max(P_FLOOR, tail)


def poisson_sf(k: int, mu: float) -> float:
    """P(X >= k) for X ~ Poisson(mu)."""
    if k <= 0:
        return 1.0
    below = sum(math.exp(x * math.log(mu) - mu - math.lgamma(x + 1)) for x in range(k))
    return max(0.0, 1.0 - below)


def negbinom_sf(k: int, mu: float, var: float) -> float:
    """P(X >= k) for a negative binomial with the given mean and variance (var > mu)."""
    if k <= 0:
        return 1.0
    r = mu * mu / (var - mu)
    p = mu / var  # success probability in the (r, p) parameterisation
    log_pmf = lambda x: math.lgamma(x + r) - math.lgamma(r) - math.lgamma(x + 1) + r * math.log(p) + x * math.log(1 - p)
    below = sum(math.exp(log_pmf(x)) for x in range(k))
    return max(0.0, 1.0 - below)


def _log_comb(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def hypergeom_sf(k: int, L: int, K: int, n: int) -> float:
    """P(X >= k) for X ~ Hypergeometric(population L, K successes, n draws)."""
    lo, hi = max(k, 0, n - (L - K)), min(n, K)
    if lo > hi:
        return 0.0 if k > hi else 1.0
    denom = _log_comb(L, n)
    terms = [_log_comb(K, x) + _log_comb(L - K, n - x) - denom for x in range(lo, hi + 1)]
    m = max(terms)
    return min(1.0, math.exp(m) * sum(math.exp(t - m) for t in terms))


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """BH-adjusted q-values, in the same order as the input."""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, p_values[i] * m / rank)
        q[i] = running
    return q


def episodes(mask: np.ndarray) -> int:
    """Number of distinct True runs in a boolean array."""
    if not len(mask):
        return 0
    m = mask.astype(int)
    return int(m[0] + np.sum((m[1:] == 1) & (m[:-1] == 0)))
