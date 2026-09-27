"""Small numpy helpers for rolling-window maths over daily series.

numpy only (no pandas): pandas' compiled extensions are blocked by
Application Control on the development machine, while numpy (which Skyfield
already depends on) loads fine. Every function returns an array the same
length as its input, NaN where the window isn't full yet.
"""

from __future__ import annotations

import numpy as np


def rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < window:
        return out
    c = np.cumsum(np.insert(np.asarray(x, dtype=float), 0, 0.0))
    out[window - 1 :] = (c[window:] - c[:-window]) / window
    return out


def rolling_std(x: np.ndarray, window: int) -> np.ndarray:
    """Population standard deviation (ddof=0) over a trailing window; NaNs in the window give NaN."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) < window:
        return out
    view = np.lib.stride_tricks.sliding_window_view(x, window)
    out[window - 1 :] = view.std(axis=1)
    return out


def pct_change(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    out[1:] = x[1:] / x[:-1] - 1
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev = np.concatenate([[np.nan], close[:-1]])
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev), np.abs(low - prev)]), axis=0)
    tr[0] = high[0] - low[0]
    return tr
