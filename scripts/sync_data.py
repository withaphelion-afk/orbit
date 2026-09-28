"""Sync Orbit's shared data with the `data` branch on GitHub.

    python scripts/sync_data.py            # take what's new, merge, send what this machine has
    python scripts/sync_data.py --pull     # take only
    python scripts/sync_data.py --status

start_orbit runs this on start and the runner once a day, so it's rarely
needed by hand. What is shared and how conflicts are resolved: src/orbit/datasync.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbit.datasync import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
