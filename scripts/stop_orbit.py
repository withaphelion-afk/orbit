"""Stop Orbit's API, runner and silver download on this machine.

    python scripts/stop_orbit.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbit import launcher  # noqa: E402

if __name__ == "__main__":
    sys.exit(launcher.stop())
