"""Small helpers shared by the Vedic modules."""

from __future__ import annotations

import numpy as np


def debounce(flags: np.ndarray, min_run: int) -> np.ndarray:
    """Merge interior runs shorter than `min_run` samples into the run before them.

    Right at a station a graha barely moves, so the sign of its speed can
    flicker for a sample or two; this keeps one clean change.
    """
    flags = np.asarray(flags, dtype=bool).copy()
    changed = True
    while changed:
        changed = False
        edges = np.flatnonzero(np.diff(flags.astype(int))) + 1
        bounds = np.concatenate([[0], edges, [len(flags)]])
        for a, b in zip(bounds[1:-2], bounds[2:-1]):  # interior runs only
            if b - a < min_run:
                flags[a:b] = flags[a - 1]
                changed = True
                break
    return flags
