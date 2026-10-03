"""RSI divergence detection: the one algorithm, in Python.

web/src/lib/divergence.ts is the same algorithm in TypeScript (the browser
runs it live on every tick). Both must find exactly the same divergences:
tests/fixtures/divergence_cases.json holds shared cases that both test suites
check, so CI fails if the two ever disagree. Change both together.

Detection is deliberately broad; the learning model (divergence_model.py)
decides which candidates matter:

    RSI       Wilder's RSI(14) of the close
    swings    a low (high) lower (higher) than the 2 bars before it and no higher
              (lower) than the 2 bars after it; known only 2 bars later, on its
              confirmation bar. Its strength: how many bars back it stays the
              lowest low (highest high), up to 100 (left side only: no look-ahead)
    pairs     every two swings of the same kind 5-60 bars apart where price and
              RSI disagree:
                regular bullish  lower low in price,   higher low in RSI   -> LONG
                hidden bullish   higher low in price,  lower low in RSI    -> LONG
                regular bearish  higher high in price, lower high in RSI   -> SHORT
                hidden bearish   lower high in price,  higher high in RSI  -> SHORT
    forming   the same, where the second swing is one of the last 2 bars and
              still the extreme so far: shown (dashed), never alerted or traded
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass

import numpy as np

RSI_PERIOD = 14
LEFT = 2
RIGHT = 2
MIN_GAP = 5
MAX_GAP = 60
MAX_STRENGTH = 100


@dataclass(frozen=True)
class Candidate:
    kind: str  # "regular" or "hidden"
    direction: str  # "LONG" or "SHORT"
    i: int  # first swing
    j: int  # second swing
    confirm: int | None  # the bar the second swing is confirmed on (None while forming)
    p1: float  # price at each swing (low for LONG, high for SHORT)
    p2: float
    r1: float  # RSI at each swing
    r2: float
    s1: int  # swing strength (bars back it stays the extreme)
    s2: int

    @property
    def forming(self) -> bool:
        return self.confirm is None

    def as_dict(self) -> dict:
        return asdict(self)


def rsi(close: np.ndarray, n: int = RSI_PERIOD) -> np.ndarray:
    """Wilder's RSI, NaN for the first n bars. Same operations, in the same order, as the TypeScript version."""
    close = np.asarray(close, dtype=float)
    out = np.full(len(close), np.nan)
    if len(close) <= n:
        return out
    gain = loss = 0.0
    for k in range(1, n + 1):
        d = close[k] - close[k - 1]
        gain += d if d > 0 else 0.0
        loss += -d if d < 0 else 0.0
    gain /= n
    loss /= n
    out[n] = 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)
    for k in range(n + 1, len(close)):
        d = close[k] - close[k - 1]
        gain = (gain * (n - 1) + (d if d > 0 else 0.0)) / n
        loss = (loss * (n - 1) + (-d if d < 0 else 0.0)) / n
        out[k] = 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)
    return out


def _is_low(low: np.ndarray, k: int, right: int) -> bool:
    if k < LEFT:
        return False
    for a in range(k - LEFT, k):
        if not low[k] < low[a]:
            return False
    for b in range(k + 1, k + 1 + right):
        if not low[k] <= low[b]:
            return False
    return True


def _is_high(high: np.ndarray, k: int, right: int) -> bool:
    if k < LEFT:
        return False
    for a in range(k - LEFT, k):
        if not high[k] > high[a]:
            return False
    for b in range(k + 1, k + 1 + right):
        if not high[k] >= high[b]:
            return False
    return True


def _strength(values: np.ndarray, k: int, low: bool) -> int:
    s = 0
    while s < MAX_STRENGTH and k - s - 1 >= 0:
        v = values[k - s - 1]
        if (low and v <= values[k]) or (not low and v >= values[k]):
            break
        s += 1
    return s


def swings(high: np.ndarray, low: np.ndarray) -> tuple[list[int], list[int]]:
    """Confirmed swing lows and highs (bar indexes), in order."""
    n = len(low)
    lows = [k for k in range(n - RIGHT) if _is_low(low, k, RIGHT)]
    highs = [k for k in range(n - RIGHT) if _is_high(high, k, RIGHT)]
    return lows, highs


def _pairs(points: list[int], extra: list[int], values: np.ndarray, r: np.ndarray, low: bool, n: int) -> list[Candidate]:
    out: list[Candidate] = []
    confirmed = set(points)
    for j in [*points, *extra]:
        if math.isnan(r[j]):
            continue
        for i in points[bisect_left(points, j - MAX_GAP) : bisect_right(points, j - MIN_GAP)]:
            if math.isnan(r[i]):
                continue
            p1, p2, r1, r2 = float(values[i]), float(values[j]), float(r[i]), float(r[j])
            if low:
                if p2 < p1 and r2 > r1:
                    kind = "regular"
                elif p2 > p1 and r2 < r1:
                    kind = "hidden"
                else:
                    continue
                direction = "LONG"
            else:
                if p2 > p1 and r2 < r1:
                    kind = "regular"
                elif p2 < p1 and r2 > r1:
                    kind = "hidden"
                else:
                    continue
                direction = "SHORT"
            confirm = j + RIGHT if j in confirmed else None
            out.append(Candidate(kind, direction, i, j, confirm, p1, p2, r1, r2, _strength(values, i, low), _strength(values, j, low)))
    return out


def find(high, low, close, include_forming: bool = True) -> list[Candidate]:
    """Every divergence candidate in the series, ordered by second swing, then direction, then first swing."""
    high, low, close = (np.asarray(a, dtype=float) for a in (high, low, close))
    n = len(close)
    r = rsi(close)
    lows, highs = swings(high, low)
    forming_lows = forming_highs = []
    if include_forming:
        # The last RIGHT bars can't be confirmed yet: a swing "so far" if it beats the bars before it and the ones after it so far.
        tail = range(max(LEFT, n - RIGHT), n)
        forming_lows = [k for k in tail if _is_low(low, k, n - 1 - k)]
        forming_highs = [k for k in tail if _is_high(high, k, n - 1 - k)]
    found = _pairs(lows, forming_lows, low, r, True, n) + _pairs(highs, forming_highs, high, r, False, n)
    return sorted(found, key=lambda c: (c.j, c.direction, c.i))
