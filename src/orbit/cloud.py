"""Orbit's web server on a free cloud host (a Hugging Face Space), with no PC on.

    python -m orbit.cloud

On a cloud host the work is split:
- GitHub Actions runs the runner (hourly) and the analysis (daily), and shares
  the data (datasync.py, private data repo) and the results (outputs.py).
- This process serves the API and the web terminal, and keeps them current:
  at start it pulls the data and results, then every few minutes it takes
  whatever the Actions jobs published, pushes your decisions to the data repo
  within seconds of you making them, and hands the RUN ANALYSIS button to the
  analysis workflow (a free host is too small and sleeps too readily to run it).

Configuration, from the host's secrets and variables:
    ORBIT_CLOUD=1               turns this mode on (set in the Space's Dockerfile)
    ORBIT_DATA_REPO             owner/name of the private data repo
    ORBIT_DATA_TOKEN            token with read/write Contents on that repo
    ORBIT_DISPATCH_TOKEN        token with read/write Actions on the code repo (for RUN ANALYSIS)
    ORBIT_CODE_REPO             owner/name of the code repo (default withaphelion-afk/orbit)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from orbit import datasync, outputs
from orbit.analysis import jobs
from orbit.config import settings

log = logging.getLogger("orbit.cloud")

CODE_REPO = os.getenv("ORBIT_CODE_REPO", "withaphelion-afk/orbit")
CODE_BRANCH = os.getenv("ORBIT_CODE_BRANCH", "main")
WORKFLOW = "analysis.yml"
GITHUB_API = "https://api.github.com"
DISPATCHED = settings.DATA_DIR / "run" / "dispatched.json"

TICK_SECONDS = 15  # how often the background loop wakes; well under the run heartbeat's 120 s
REFRESH_SECONDS = 300  # pull data and results this often
UNSEEN_RUN_GIVE_UP = timedelta(minutes=15)  # a dispatched run GitHub still hasn't listed by then is marked failed


def enabled() -> bool:
    return os.getenv("ORBIT_CLOUD") == "1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- data repo


def connect_data_repo() -> None:
    """Point the data sync's git remote at the private data repo, authenticated
    by the host's token. The token goes only into git's own config, so remote
    URLs, logs and error messages stay free of it."""
    repo, token = os.getenv("ORBIT_DATA_REPO", ""), os.getenv("ORBIT_DATA_TOKEN", "")
    if not repo or not token:
        raise SystemExit("Set ORBIT_DATA_REPO and ORBIT_DATA_TOKEN in the host's secrets (README: Free cloud hosting).")
    url = f"https://github.com/{repo}"

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=settings.REPO_ROOT, capture_output=True, text=True)

    if git("config", "--global", f"url.https://x-access-token:{token}@github.com/{repo}.insteadOf", url).returncode:
        raise SystemExit("could not configure git for the data repo")  # deliberately without git's output: it echoes the token
    for key, value in (("user.name", "orbit-cloud"), ("user.email", "orbit-cloud@users.noreply.github.com")):
        git("config", "--global", key, value)
    remote = settings.DATA_SYNC_REMOTE
    if git("remote", "get-url", remote).returncode:
        git("remote", "add", remote, f"{url}.git")


def pull_everything() -> None:
    result = datasync.sync()
    log.info(result.summary())
    taken = outputs.fetch()
    if taken:
        log.info(f"Results: took {taken} files ({outputs.last_fetch().get('published_at')}).")


# ---------------------------------------------------------------- RUN ANALYSIS -> GitHub


def _gh_headers() -> dict:
    token = os.getenv("ORBIT_DISPATCH_TOKEN", "")
    if not token:
        raise RuntimeError("RUN ANALYSIS needs ORBIT_DISPATCH_TOKEN on this host (README: Free cloud hosting)")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _read_dispatched() -> dict | None:
    try:
        return json.loads(DISPATCHED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def dispatch(run: jobs.AnalysisRun) -> None:
    """jobs.start's spawn on a cloud host: start the analysis workflow for this
    run record instead of a local process. The workflow runs it under the same
    id, so when its results arrive they replace this record in place."""
    response = requests.post(
        f"{GITHUB_API}/repos/{CODE_REPO}/actions/workflows/{WORKFLOW}/dispatches",
        headers=_gh_headers(),
        json={"ref": CODE_BRANCH, "inputs": {"placebo": str(run.include_placebo).lower(),
                                             "refresh": str(run.refresh_data).lower(), "run_id": run.id}},
        timeout=20,
    )
    if response.status_code != 204:
        raise RuntimeError(f"GitHub refused to start the analysis workflow (HTTP {response.status_code}): {response.text[:200]}")
    DISPATCHED.parent.mkdir(parents=True, exist_ok=True)
    DISPATCHED.write_text(json.dumps({"run_id": run.id, "at": _now().isoformat()}), encoding="utf-8")
    run.step = "Waiting for GitHub Actions"
    run.log.append("Handed to GitHub Actions (this host only serves the terminal). Results arrive here when it finishes.")
    run.heartbeat_at = _now()
    jobs.save(run)


def _find_github_run(run_id: str) -> dict | None:
    response = requests.get(
        f"{GITHUB_API}/repos/{CODE_REPO}/actions/workflows/{WORKFLOW}/runs",
        headers=_gh_headers(),
        params={"event": "workflow_dispatch", "per_page": 20},
        timeout=20,
    )
    response.raise_for_status()
    return next((r for r in response.json().get("workflow_runs", []) if r.get("display_title") == f"analysis {run_id}"), None)


def track_dispatched(find=_find_github_run, fetch_results=outputs.fetch) -> None:
    """Keep a handed-over run's record alive and in step with GitHub until its
    results arrive (the record's heartbeat would otherwise go stale and the
    terminal would call it dead)."""
    handed = _read_dispatched()
    if not handed:
        return
    run = jobs.load(handed["run_id"])
    if run is None or run.status in ("succeeded", "failed"):
        DISPATCHED.unlink(missing_ok=True)
        return
    gh = find(run.id)
    if gh is None:
        if _now() - datetime.fromisoformat(handed["at"]) > UNSEEN_RUN_GIVE_UP:
            run.status, run.finished_at = "failed", _now()
            run.error = "GitHub never started the analysis workflow. Check the Actions tab of the code repo."
            jobs.save(run)
            DISPATCHED.unlink(missing_ok=True)
            return
    elif gh.get("status") == "completed":
        fetch_results(force=True)  # brings the workflow's own record for this id, with its log and summary
        run = jobs.load(run.id) or run
        if run.status not in ("succeeded", "failed"):  # the workflow ended before it could publish
            run.status, run.finished_at = ("succeeded" if gh.get("conclusion") == "success" else "failed"), _now()
            run.error = None if run.status == "succeeded" else f"GitHub Actions: {gh.get('conclusion')} ({gh.get('html_url')})"
            jobs.save(run)
        DISPATCHED.unlink(missing_ok=True)
        return
    else:
        running = gh.get("status") == "in_progress"
        run.status = "running" if running else "queued"
        run.step = "Running on GitHub Actions" if running else "Waiting for GitHub Actions"
        link = f"GitHub run: {gh.get('html_url')}"
        if link not in run.log:
            run.log.append(link)
    run.heartbeat_at = _now()
    jobs.save(run)


# ---------------------------------------------------------------- background loop


def _journal_mtime() -> float:
    from orbit.journal.store import PATH

    return PATH.stat().st_mtime if PATH.exists() else 0.0


def keep_current(stop: threading.Event) -> None:
    journal_seen = _journal_mtime()
    next_refresh = time.monotonic() + REFRESH_SECONDS
    while not stop.wait(TICK_SECONDS):
        try:
            if _journal_mtime() != journal_seen:  # you decided on a suggestion: share it now
                log.info(datasync.sync().summary())
                journal_seen = _journal_mtime()
            if time.monotonic() >= next_refresh:
                pull_everything()
                journal_seen = _journal_mtime()
                next_refresh = time.monotonic() + REFRESH_SECONDS
            track_dispatched()
        except Exception:
            log.exception("Background refresh failed; trying again shortly.")


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    connect_data_repo()
    try:
        pull_everything()
    except Exception:
        log.exception("First pull failed; serving what's here and retrying in the background.")
    stop = threading.Event()
    threading.Thread(target=keep_current, args=(stop,), name="orbit-cloud-refresh", daemon=True).start()
    from orbit.api.app import create_app

    uvicorn.run(create_app(), host=settings.API_HOST, port=settings.API_PORT, log_level="info")
    stop.set()


if __name__ == "__main__":
    main()
