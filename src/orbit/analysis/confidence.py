"""Turn sample size, effect size and corrected significance into one label.

    insufficient_data  fewer than MIN_OCCURRENCES occurrences. Never tested,
                       never presented as a signal, however clean it looks.
    none               enough data, nothing beyond chance.
    weak               nominally significant (p < NOMINAL_ALPHA) but it does
                       not survive FDR correction: worth watching, no more.
    moderate           survives FDR at FDR_MODERATE with a real effect.
    strong             survives FDR at FDR_STRONG, has at least
                       STRONG_MIN_OCCURRENCES occurrences and a large effect.

The 0-100 score blends the same three ingredients so results can be ranked
within a label; the label is what should be trusted.
"""

from __future__ import annotations

from orbit.config.settings import (
    FDR_MODERATE,
    FDR_STRONG,
    MIN_OCCURRENCES,
    NOMINAL_ALPHA,
    STRONG_MIN_OCCURRENCES,
)
from orbit.core.types import ConfidenceLabel

MODERATE_MIN_LIFT = 1.25  # hit rate at least 25% above the base rate
STRONG_MIN_LIFT = 1.5


def lift(rate: float, base: float) -> float:
    return rate / base if base > 0 else float("nan")


def label(n: int, rate: float, base: float, p: float | None, q: float | None) -> ConfidenceLabel:
    if n < MIN_OCCURRENCES or p is None or q is None:
        return ConfidenceLabel.INSUFFICIENT_DATA
    lf = lift(rate, base)
    if q <= FDR_STRONG and n >= STRONG_MIN_OCCURRENCES and lf >= STRONG_MIN_LIFT:
        return ConfidenceLabel.STRONG
    if q <= FDR_MODERATE and lf >= MODERATE_MIN_LIFT:
        return ConfidenceLabel.MODERATE
    if p <= NOMINAL_ALPHA and lf > 1:
        return ConfidenceLabel.WEAK
    return ConfidenceLabel.NONE


def score(n: int, rate: float, base: float, p: float | None, q: float | None) -> int:
    if n < MIN_OCCURRENCES or p is None or q is None:
        return 0
    sample = min(1.0, n / 50)
    effect = max(0.0, min(1.0, lift(rate, base) - 1))  # 0 at no lift, 1 at double the base rate
    significance = max(0.0, 1 - q / 0.2) if q < 0.2 else 0.3 * max(0.0, 1 - p / 0.1)
    return round(100 * sample * effect * significance)


RANK = {
    ConfidenceLabel.STRONG: 4,
    ConfidenceLabel.MODERATE: 3,
    ConfidenceLabel.WEAK: 2,
    ConfidenceLabel.NONE: 1,
    ConfidenceLabel.INSUFFICIENT_DATA: 0,
}
