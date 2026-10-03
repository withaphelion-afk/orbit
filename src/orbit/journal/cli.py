"""Log a decision on a suggestion from the command line (the cloud `decide` job).

    python -m orbit.journal.cli --id ID --decision TAKEN|SKIPPED|MODIFIED [--notes ...]
                                [--entry X --stop Y --target Z]   (MODIFIED only)

The static web terminal has no server to POST to, so Take/Skip/Modify starts
the `decide` GitHub workflow, which runs this against the shared journal and
then republishes the terminal's data.
"""

from __future__ import annotations

import argparse
import sys

from orbit.core.types import Decision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log your decision on an Orbit suggestion")
    parser.add_argument("--id", required=True)
    parser.add_argument("--decision", required=True, choices=[d.value for d in Decision])
    parser.add_argument("--notes", default="")
    parser.add_argument("--entry", type=float)
    parser.add_argument("--stop", type=float)
    parser.add_argument("--target", type=float)
    args = parser.parse_args(argv)

    decision = Decision(args.decision)
    if decision == Decision.MODIFIED and None in (args.entry, args.stop, args.target):
        print("MODIFIED needs --entry, --stop and --target.", file=sys.stderr)
        return 2

    from orbit.strategy import live

    try:
        rec = live.decide(args.id, decision, args.notes, args.entry, args.stop, args.target)
    except KeyError:
        print(f"No suggestion {args.id}.", file=sys.stderr)
        return 1
    except ValueError as exc:
        # Already decided (a second click) or expired before the job ran: nothing to change.
        print(f"Nothing logged: {exc}.")
        return 0
    print(f"Logged {rec.decision.value} on {rec.id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
