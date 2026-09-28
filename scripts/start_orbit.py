"""Start Orbit on this machine (Windows, macOS or Linux) and open the web terminal.

    python scripts/start_orbit.py               # or double-click start_orbit.cmd / start_orbit.sh
    python scripts/start_orbit.py --no-browser  # what autostart uses
    python scripts/start_orbit.py --status

Starts the API (which also serves the web terminal, rebuilt first if its
sources changed), the 24/7 runner, and the silver download if it isn't
complete. Safe to run twice. See src/orbit/launcher.py.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbit import launcher  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-browser", action="store_true", help="don't open the web terminal")
    parser.add_argument("--status", action="store_true", help="show what's running and exit")
    args = parser.parse_args()
    sys.exit(launcher.status() if args.status else launcher.start(open_browser=not args.no_browser))
