"""Write tests/fixtures/divergence_cases.json: inputs and the expected divergences.

Both test suites check their own implementation against this file (Python:
tests/test_strategy.py, TypeScript: web/src/lib/divergence.test.ts), so the two
can never drift apart. Regenerate only on a deliberate change to the algorithm:

    python tests/fixtures/make_divergence_cases.py
"""

import json
from pathlib import Path

import numpy as np

from orbit.strategy import divergence as det


def walk(seed: int, n: int = 400):
    rng = np.random.default_rng(seed)
    close = np.round(100 * np.exp(np.cumsum(rng.normal(0, 0.02, n))), 4)
    spread = np.abs(rng.normal(0, 0.01, n))
    high = np.round(close * (1 + spread), 4)
    low = np.round(close * (1 - spread), 4)
    return high.tolist(), low.tolist(), close.tolist()


def ties():
    # Equal lows and highs, to pin down the strict/non-strict comparisons.
    base = [10, 9, 8, 7, 7, 8, 9, 10, 11, 10, 9, 8, 7, 7, 6, 7, 8, 9, 10, 11, 12, 11, 10, 9, 8, 9, 10, 11, 12, 12, 11, 10]
    close = [float(c) * (1 + 0.05 * k) - 3 * k for k in range(3) for c in base]
    return [c + 0.5 for c in close], [c - 0.5 for c in close], close


cases = []
for name, (high, low, close) in [*((f"walk-{s}", walk(s)) for s in (1, 2, 3, 4)), ("ties", ties())]:
    found = det.find(high, low, close)
    lows, highs = det.swings(np.array(high), np.array(low))
    cases.append({"name": name, "high": high, "low": low, "close": close, "swings": {"lows": lows, "highs": highs}, "rsi": [None if np.isnan(v) else float(v) for v in det.rsi(close)],
                  "expected": [c.as_dict() for c in found]})
Path(__file__).with_name("divergence_cases.json").write_text(json.dumps(cases), encoding="utf-8")
print({c["name"]: len(c["expected"]) for c in cases})
