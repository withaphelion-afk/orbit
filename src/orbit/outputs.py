"""Share computed files through single-commit branches of the data repo.

    python -m orbit.outputs --publish          # this machine's results -> `outputs`
    python -m orbit.outputs --fetch            # the latest results -> data/
    python -m orbit.outputs --site site/api    # the web terminal's data -> `site`

datasync.py shares the inputs that are slow to rebuild (prices, caches) and
merges them file by file. This module shares what is *computed* from them —
the playbook, backtest, feedback-loop calibration, Vedic model and sky, runner
status — for hosts that don't compute it themselves: the web server reads it,
and each scheduled GitHub Actions job starts from the previous job's results.

The `site` branch holds the static web terminal's data (snapshot.py): the app
reads it straight from this private repo with your GitHub token.

Each branch is replaced wholesale, never merged: a single commit force-pushed
every time, so it never accumulates history (the analysis JSON is ~50 MB and
changes daily). The previous commit is fetched first, so a push only sends the
files that changed.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from orbit.config.settings import DATA_DIR, DATA_SYNC_REMOTE, REPO_ROOT
from orbit.datasync import NETWORK, SyncError, _git
from orbit.fsutil import atomic_write_bytes

BRANCH = os.getenv("ORBIT_OUTPUTS_BRANCH", "outputs")
SITE_BRANCH = os.getenv("ORBIT_SITE_BRANCH", "site")
WORK = REPO_ROOT / ".orbit-outputs"
STATE = DATA_DIR / "run" / "outputs.json"
MANIFEST = "manifest.json"

INCLUDE = (
    "analysis/*.json",
    "analysis/runs.jsonl",
    "analysis/model/**/*",
    "strategy/**/*",
    "vedic/*",
    "runner_status.json",
)
SKIP_SUFFIXES = (".lock", ".tmp")
RUNS_KEPT = 40  # analysis run records (json + log) included, newest first
LOG_LINES_KEPT = 2000


def _clear(path: Path) -> None:
    """Remove a work folder. Git marks its object files read-only, which stops
    shutil.rmtree on Windows, so clear that flag first."""
    if not path.exists():
        return
    for p in path.rglob("*"):
        try:
            p.chmod(0o700)
        except OSError:
            pass
    shutil.rmtree(path)


def _remote_url() -> str:
    proc = _git("remote", "get-url", DATA_SYNC_REMOTE, cwd=REPO_ROOT, check=False)
    if proc.returncode:
        raise SyncError(f"no git remote called {DATA_SYNC_REMOTE}")
    return proc.stdout.strip()


def collect(data_dir: Path = DATA_DIR) -> dict[str, Path]:
    """{path relative to data/: file} for everything that gets published."""
    files: dict[str, Path] = {}
    for pattern in INCLUDE:
        for path in data_dir.glob(pattern):
            if path.is_file() and not path.name.endswith(SKIP_SUFFIXES):
                files[path.relative_to(data_dir).as_posix()] = path
    runs = data_dir / "analysis" / "runs"
    if runs.exists():
        newest = sorted(runs.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:RUNS_KEPT]
        for record in newest:
            for path in (record, record.with_suffix(".log")):
                if path.exists():
                    files[path.relative_to(data_dir).as_posix()] = path
    return files


def _log_tail(path: Path) -> bytes:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    return "".join(lines[-LOG_LINES_KEPT:]).encode("utf-8")


def _replace_branch(branch: str, files: dict[str, Path | bytes], message: str) -> None:
    """Make `branch` on the data remote one commit holding exactly `files`."""
    url = _remote_url()
    _clear(WORK)
    WORK.mkdir(parents=True)
    _git("init", "-q", "-b", branch, cwd=WORK)
    # Knowing the current commit lets the push send only the objects that changed.
    _git(*NETWORK, "fetch", "-q", "--depth", "1", url, f"refs/heads/{branch}", cwd=WORK, check=False)
    for rel, source in files.items():
        target = WORK / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, bytes):
            target.write_bytes(source)
        else:
            shutil.copyfile(source, target)
    (WORK / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    _git("add", "-A", cwd=WORK)
    who = ["-c", "user.name=Orbit", "-c", "user.email=orbit@localhost"]
    _git(*who, "commit", "-q", "-m", message, cwd=WORK)
    proc = _git(*NETWORK, "push", "-q", "--force", url, f"HEAD:refs/heads/{branch}", cwd=WORK, check=False)
    _clear(WORK)
    if proc.returncode:
        raise SyncError(f"could not push the {branch} branch: {proc.stderr.strip()[-300:]}")


def publish(data_dir: Path = DATA_DIR) -> int:
    """Replace the outputs branch with this machine's results. Returns the number of files sent."""
    files: dict[str, Path | bytes] = dict(collect(data_dir))
    log = data_dir / "logs" / "runner.log"
    if log.exists():
        files["logs/runner.log"] = _log_tail(log)
    manifest = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "host": os.getenv("ORBIT_HOST_NAME") or platform.node(),
        "files": sorted(files),
    }
    files[MANIFEST] = json.dumps(manifest, indent=2).encode("utf-8")
    _replace_branch(BRANCH, files, f"Results from {manifest['host']} at {manifest['published_at']}")
    return len(files) - 1


def publish_site(site_dir: Path) -> int:
    """Replace the site branch with the web terminal's data (snapshot.py's output). Returns the file count."""
    files: dict[str, Path | bytes] = {p.relative_to(site_dir).as_posix(): p for p in site_dir.rglob("*") if p.is_file()}
    _replace_branch(SITE_BRANCH, files, f"Terminal data at {datetime.now(timezone.utc).isoformat()}")
    return len(files)


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def remote_head() -> str | None:
    heads = _git(*NETWORK, "ls-remote", "--heads", _remote_url(), BRANCH, cwd=REPO_ROOT).stdout.split()
    return heads[0] if heads else None


def fetch(data_dir: Path = DATA_DIR, force: bool = False) -> int:
    """Copy the latest published results into data/ (overwriting, never deleting).
    Returns the number of files taken; 0 when nothing was published or nothing changed."""
    head = remote_head()
    if head is None or (head == _state().get("commit") and not force):
        return 0
    url = _remote_url()
    _clear(WORK)
    WORK.mkdir(parents=True)
    _git("init", "-q", cwd=WORK)
    _git(*NETWORK, "fetch", "-q", "--depth", "1", url, f"refs/heads/{BRANCH}", cwd=WORK)
    _git("checkout", "-q", "FETCH_HEAD", cwd=WORK)

    taken = 0
    for path in WORK.rglob("*"):
        rel = path.relative_to(WORK).as_posix()
        if not path.is_file() or rel.startswith(".git") or rel in (MANIFEST, ".gitattributes"):
            continue
        atomic_write_bytes(data_dir / rel, path.read_bytes())
        taken += 1
    manifest = json.loads((WORK / MANIFEST).read_text(encoding="utf-8")) if (WORK / MANIFEST).exists() else {}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"commit": head, "published_at": manifest.get("published_at"),
                                 "host": manifest.get("host"), "fetched_at": datetime.now(timezone.utc).isoformat()}),
                     encoding="utf-8")
    _clear(WORK)
    return taken


def main() -> int:
    parser = argparse.ArgumentParser(description="Share Orbit's computed results through the outputs branch")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--publish", action="store_true")
    group.add_argument("--fetch", action="store_true")
    group.add_argument("--site", type=Path, metavar="DIR", help="publish the web terminal's data (snapshot.py output)")
    parser.add_argument("--force", action="store_true", help="--fetch even if nothing changed")
    args = parser.parse_args()
    try:
        if args.publish:
            print(f"Published {publish()} result files to the {BRANCH} branch.")
        elif args.site:
            print(f"Published {publish_site(args.site)} terminal data files to the {SITE_BRANCH} branch.")
        else:
            n = fetch(force=args.force)
            print(f"Took {n} result files from the {BRANCH} branch." if n else "Results are up to date (or none published yet).")
    except SyncError as exc:
        print(f"Outputs: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
