#!/usr/bin/env sh
# Start Orbit on macOS or Linux. Same as: python scripts/start_orbit.py
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python scripts/start_orbit.py "$@"
else
  exec uv run python scripts/start_orbit.py "$@"
fi
