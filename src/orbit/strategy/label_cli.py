"""Record a ✓ real / ✗ not real on a divergence from the command line (the cloud's label workflow runs this).

    python -m orbit.strategy.label_cli --asset BTC --timeframe 4h --t1 1759000000 --t2 1759300000 --direction LONG --verdict real
"""

import argparse
import sys

from orbit.strategy.divergence_model import add_label

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--asset", required=True, choices=["BTC", "ETH", "SOL", "SILVER"])
    p.add_argument("--timeframe", required=True, choices=["1h", "4h", "1d", "1w"])
    p.add_argument("--t1", required=True, type=int)
    p.add_argument("--t2", required=True, type=int)
    p.add_argument("--direction", required=True, choices=["LONG", "SHORT"])
    p.add_argument("--verdict", required=True, choices=["real", "not"])
    p.add_argument("--note", default="")
    p.add_argument("--source", default="detected", choices=["detected", "manual"])
    a = p.parse_args()
    print(add_label(a.asset, a.timeframe, a.t1, a.t2, a.direction, a.verdict, a.note, a.source))
    sys.exit(0)
