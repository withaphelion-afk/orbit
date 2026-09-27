"""Start Orbit automatically when you log in (per user, no admin rights).

    python scripts/autostart.py            # turn it on
    python scripts/autostart.py --remove   # turn it off

Windows: a .cmd in your Startup folder. macOS: a LaunchAgent. Linux: an XDG
autostart entry. Each runs scripts/start_orbit.py --no-browser.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbit import launcher  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remove", action="store_true", help="stop starting Orbit at login")
    args = parser.parse_args()
    sys.exit(launcher.remove_autostart() if args.remove else launcher.install_autostart())
