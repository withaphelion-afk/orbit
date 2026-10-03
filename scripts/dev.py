"""Local task runner: no Claude, no tokens. Standard library only.

    uv run python scripts/dev.py check            # every test, typecheck, lint and build, with a summary
    uv run python scripts/dev.py start | stop     # run Orbit on this machine
    uv run python scripts/dev.py status           # cloud health: latest GitHub runs, latest published data
    uv run python scripts/dev.py cleanup          # delete merged branches, prune caches
    uv run python scripts/dev.py ship "message"   # commit to a new branch, push, open a PR (no check: CI checks PRs)
    uv run python scripts/dev.py deploy [PR]      # check first; only if everything passes, merge the PR into main
    uv run python scripts/dev.py install-hook     # run `check` automatically before any push to main

The full check runs only on the way to main (deploy, and pushes to main via the
hook): main is what Vercel deploys, so that's where a broken build would hurt.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
WIN = sys.platform == "win32"
NPM = "npm.cmd" if WIN else "npm"
NPX = "npx.cmd" if WIN else "npx"


def run(cmd: list[str], cwd: Path = ROOT, quiet: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=quiet, encoding="utf-8", errors="replace")


def out(cmd: list[str], cwd: Path = ROOT) -> str:
    return run(cmd, cwd, quiet=True).stdout.strip()


def check() -> bool:
    steps = [
        ("python deps", ["uv", "sync", "--extra", "dev"], ROOT),
        ("python tests", ["uv", "run", "pytest", "-q"], ROOT),
        ("web deps", [NPM, "ci", "--no-audit", "--no-fund"], WEB),
        ("web typecheck", [NPX, "tsc", "-b"], WEB),
        ("web lint", [NPX, "oxlint"], WEB),
        ("web tests", [NPX, "vitest", "run"], WEB),
        ("web build", [NPM, "run", "build"], WEB),
    ]
    results = []
    for name, cmd, cwd in steps:
        start = time.time()
        p = run(cmd, cwd, quiet=True)
        ok = p.returncode == 0
        results.append((name, ok, time.time() - start))
        print(f"{'PASS' if ok else 'FAIL'}  {name:14s} {time.time() - start:6.1f}s")
        if not ok:
            tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-25:])
            print(f"\n--- {name} failed; last lines (paste these to Claude) ---\n{tail}\n")
            break  # later steps depend on earlier ones
    passed = len(results) == len(steps) and all(ok for _, ok, _ in results)
    print("\nALL CHECKS PASSED" if passed else "\nCHECK FAILED")
    return passed


def status() -> None:
    print("Latest GitHub runs:")
    for wf in ("runner.yml", "analysis.yml", "decide.yml", "label.yml", "ci.yml", "deploy-web.yml"):
        line = out(["gh", "run", "list", "--workflow", wf, "--limit", "1", "--json", "conclusion,status,createdAt",
                    "-q", '.[0] | "\\(.status) \\(.conclusion // "-") \\(.createdAt)"'])
        print(f"  {wf:16s} {line or 'no runs'}")
    data_remote = out(["git", "remote", "get-url", "data"]) or "https://github.com/withaphelion-afk/orbit-data.git"
    print("\nLatest published data (orbit-data branches):")
    for branch in ("data", "outputs", "site"):
        sha = out(["git", "ls-remote", data_remote, f"refs/heads/{branch}"]).split("\t")[0][:8]
        print(f"  {branch:8s} {sha or 'missing'}")
    print("\nOpen PRs:")
    print("  " + (out(["gh", "pr", "list", "--limit", "5"]) or "none").replace("\n", "\n  "))


def cleanup() -> None:
    run(["git", "fetch", "-q", "--prune", "origin"])
    merged = [b.strip().removeprefix("origin/") for b in out(["git", "branch", "-r", "--merged", "origin/main"]).splitlines()]
    stale = [b for b in merged if b and "->" not in b and b != "main"]
    for b in stale:
        run(["git", "push", "-q", "origin", "--delete", b])
        print(f"deleted origin/{b}")
    for b in out(["git", "branch", "--merged", "main"]).replace("*", "").split():
        if b != "main":
            run(["git", "branch", "-d", b], quiet=True)
            print(f"deleted local {b}")
    for cache in ROOT.rglob("__pycache__"):
        if ".venv" not in cache.parts and "node_modules" not in cache.parts:
            for f in cache.iterdir():
                f.unlink()
            cache.rmdir()
    print("cleanup done")


def ship(message: str) -> None:
    if not out(["git", "status", "--porcelain"]):
        sys.exit("Nothing to ship: no changes.")
    branch = "work-" + time.strftime("%Y%m%d-%H%M")
    run(["git", "checkout", "-b", branch])
    run(["git", "add", "-A"])
    run(["git", "commit", "-q", "-m", message])
    run(["git", "push", "-q", "-u", "origin", branch])
    run(["gh", "pr", "create", "--base", "main", "--head", branch, "--title", message, "--body", "Shipped with scripts/dev.py ship."])
    print("PR opened. CI checks it; run `dev.py deploy` to check locally and merge into main.")


def deploy(pr: str | None) -> None:
    print("Checking before deploying to main...\n")
    if not check():
        sys.exit("Not deployed: fix the failures above first.")
    target = [pr] if pr else []
    p = run(["gh", "pr", "merge", *target, "--merge", "--delete-branch"])
    if p.returncode:
        sys.exit("Merge failed (see above).")
    run(["git", "checkout", "-q", "main"])
    run(["git", "pull", "-q", "--ff-only", "origin", "main"])
    print("Merged into main. CI runs, then Vercel deploys automatically.")


HOOK = """#!/bin/sh
# Installed by scripts/dev.py install-hook: run the full check only for pushes to main.
while read local_ref local_sha remote_ref remote_sha; do
  if [ "$remote_ref" = "refs/heads/main" ]; then
    echo "Pushing to main: running scripts/dev.py check first..."
    uv run python scripts/dev.py check || { echo "Push to main blocked: check failed."; exit 1; }
  fi
done
exit 0
"""


def install_hook() -> None:
    hook = ROOT / ".git" / "hooks" / "pre-push"
    hook.write_text(HOOK, encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    print(f"Installed {hook}: the check now runs before any push to main (other branches push without it).")


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "help"
    if cmd == "check":
        sys.exit(0 if check() else 1)
    elif cmd in ("start", "stop"):
        sys.exit(run([sys.executable, str(ROOT / "scripts" / f"{cmd}_orbit.py")]).returncode)
    elif cmd == "status":
        status()
    elif cmd == "cleanup":
        cleanup()
    elif cmd == "ship":
        if len(args) < 2:
            sys.exit('Usage: dev.py ship "commit message"')
        ship(args[1])
    elif cmd == "deploy":
        deploy(args[1] if len(args) > 1 else None)
    elif cmd == "install-hook":
        install_hook()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
