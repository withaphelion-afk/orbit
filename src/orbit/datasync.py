"""Keep the data every machine needs on GitHub, on a `data` branch.

    python scripts/sync_data.py                  # pull what's new, merge, push
    python scripts/sync_data.py --pull           # pull and merge only
    python scripts/sync_data.py --status
    python scripts/sync_data.py --prefer-local   # push a deliberate rebuild of a price history
    python scripts/sync_data.py --recreate       # re-create the branch after it was deleted on GitHub

What is shared is only what is slow or impossible to rebuild; everything else
(features, the Vedic sky, the playbook, the backtest, the model) is rebuilt by
each machine's own runner and analysis run from these:

    {ASSET}_1d.csv, {ASSET}_1h.csv   stitched price histories (minutes to rebuild; some venues are region-blocked)
    history_report.json              where each history came from
    cache/dukascopy/**               the spot-silver files (hours to download: the feed throttles hard)
    ephemeris_cache/de421.bsp        NASA JPL's ephemeris kernel
    analysis/placebo.json            the latest placebo check (40 minutes to rerun)
    journal/suggestions.json         your decisions and notes, only if DATA_SYNC_JOURNAL is on

How it works: the `data` branch is checked out as a git worktree in
.orbit-sync/ (ignored by the main branch). A sync fetches the branch, merges it
file by file with this machine's data/ using the rules below, writes each
winner to both sides, and commits and pushes if anything changed; if another
machine pushed in the meantime it fetches and merges again. There are never
git merge conflicts, because files are merged by rules, not by git:

    price CSVs      the better file wins: for silver, spot (Dukascopy) beats futures; then the longer history
                    (earlier first bar); then the later last bar; then more bars. A tie keeps GitHub's copy, so two
                    machines don't keep swapping today's still-forming bar (--prefer-local sends a deliberate rebuild)
    history report  follows the price CSV that won
    silver cache    union of files (they never change once written); the larger copy if both differ, GitHub's on a tie
    kernel          union
    placebo         the later check wins
    journal         union by suggestion id; a decision beats pending or expired; if both machines decided, the first
                    decision stands and the other one (decision, time, notes) is kept in its notes. The local journal
                    is backed up before a sync changes it

Files are never deleted by a sync. If the branch disappears from GitHub after
this machine has used it (someone deleted it, say, to take it down), a sync
refuses to put it back unless asked to with --recreate, and then starts a new,
empty history rather than pushing the old one.

A machine that can pull but not push (no GitHub login, no write access) still
gets everything: the push failure is reported once, and it tries again a day later.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from orbit.config import settings
from orbit.config.settings import DATA_DIR, DATA_SYNC_BRANCH, DATA_SYNC_EVERY_HOURS, DATA_SYNC_REMOTE, REPO_ROOT
from orbit.fsutil import atomic_write_bytes, file_lock

DATA_SYNC_ENABLED = settings.DATA_SYNC_ENABLED
WORKTREE = REPO_ROOT / ".orbit-sync"
STATE = DATA_DIR / "run" / "sync.json"
LOCK = DATA_DIR / "run" / "sync.lock"
CSV_HEADER = ["timestamp", "open", "high", "low", "close", "volume", "source"]
PRICE_SUFFIXES = ("_1d.csv", "_1h.csv")
UNION_DIRS = ("cache/dukascopy",)
UNION_FILES = ("ephemeris_cache/de421.bsp",)
PUSH_ATTEMPTS = 4
RETRY_HOURS_AFTER_ERROR = 3
STALE_GIT_LOCK_SECONDS = 600
NETWORK = ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=60"]  # give up on a stalled transfer after a minute

BRANCH_README = """# Orbit data

This branch holds the data Orbit can't cheaply rebuild, so any machine can
start from it: stitched price histories, the spot-silver cache, NASA's DE421
kernel and the latest placebo check. It is written by `scripts/sync_data.py`
(and by `start_orbit` and the runner), never by hand. See `src/orbit/datasync.py`
on the main branch for what is shared and how conflicts are resolved.
"""


class SyncError(RuntimeError):
    pass


@dataclass
class Result:
    pulled: list[str] = field(default_factory=list)  # files this machine took from GitHub
    pushed: list[str] = field(default_factory=list)  # files this machine sent
    commit: str | None = None
    skipped: str | None = None  # why nothing happened
    warning: str | None = None  # e.g. pulled fine, but couldn't push

    def summary(self) -> str:
        if self.skipped:
            return f"Data sync skipped: {self.skipped}"
        parts = [f"took {len(self.pulled)} file(s) from GitHub" if self.pulled else "nothing new on GitHub"]
        if self.pushed:
            parts.append(f"sent {len(self.pushed)} file(s) ({self.commit})")
        elif not self.warning:
            parts.append("nothing to send")
        text = "Data sync: " + ", ".join(parts) + "."
        return text + (f" {self.warning}" if self.warning else "")


# ---------------------------------------------------------------- git


def _env() -> dict:
    # English messages (they're parsed), and never wait on a password or passphrase prompt: this often runs
    # unattended. The user's own ssh command (core.sshCommand, GIT_SSH) is left alone.
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "SSH_ASKPASS_REQUIRE": "never",
            "LC_ALL": "C", "LANGUAGE": "C"}


def _git(*args: str, cwd: Path | None = None, check: bool = True, input: str | None = None, timeout: float = 900) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=cwd or REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          input=input, timeout=timeout, env=_env())
    if check and proc.returncode:
        raise SyncError(f"git {' '.join(a for a in args if not a.startswith('http.'))} failed: {(proc.stderr or proc.stdout).strip()[-800:]}")
    return proc


def _remote_ref() -> str:
    return f"refs/remotes/{DATA_SYNC_REMOTE}/{DATA_SYNC_BRANCH}"


def _fetch() -> bool:
    """Fetch the data branch. False if it doesn't exist on the remote."""
    heads = _git(*NETWORK, "ls-remote", "--heads", DATA_SYNC_REMOTE, DATA_SYNC_BRANCH).stdout.strip()
    if not heads:
        return False
    _git(*NETWORK, "-c", "fetch.unpackLimit=1", "fetch", "--no-tags", DATA_SYNC_REMOTE, f"+refs/heads/{DATA_SYNC_BRANCH}:{_remote_ref()}")
    return True


def _ref_exists(ref: str) -> bool:
    return _git("rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0


def _pack_loose_objects() -> None:
    """Each sync leaves a few large loose objects (whole CSVs); pack them so .git doesn't grow by megabytes a day."""
    counts = dict(line.split(": ", 1) for line in _git("count-objects", "-v", check=False).stdout.splitlines() if ": " in line)
    if int(counts.get("count", 0)) > 50 or int(counts.get("size", 0)) > 50_000:  # size is in KiB
        _git("repack", "-d", "-q", check=False)


def _common_dir(cwd: Path) -> Path | None:
    proc = _git("rev-parse", "--git-common-dir", cwd=cwd, check=False)
    if proc.returncode:
        return None
    p = Path(proc.stdout.strip())
    return (p if p.is_absolute() else cwd / p).resolve()


def _worktree_ok() -> bool:
    """The worktree exists, is on the data branch, and belongs to this checkout (not a copy's original)."""
    if not (WORKTREE / ".git").exists():
        return False
    proc = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=WORKTREE, check=False)
    if proc.returncode or proc.stdout.strip() != DATA_SYNC_BRANCH:
        return False
    return _common_dir(WORKTREE) == _common_dir(REPO_ROOT)


def _drop_worktree() -> None:
    if WORKTREE.exists():
        shutil.rmtree(WORKTREE, ignore_errors=True)
    _git("worktree", "prune")
    # In a copy of the Orbit folder, .git still registers the ORIGINAL's .orbit-sync (which exists, so prune keeps it)
    # and git refuses to check the data branch out twice. Forget that registration here; the original is untouched.
    common = _common_dir(REPO_ROOT)
    for entry in (common / "worktrees").glob("*") if common else []:
        try:
            target = Path((entry / "gitdir").read_text(encoding="utf-8").strip()).resolve().parent
        except OSError:
            continue
        if target.name == WORKTREE.name and target != WORKTREE.resolve():
            shutil.rmtree(entry, ignore_errors=True)


def _identity() -> list[str]:
    """Commit as the machine's git user (unsigned); fall back to a neutral name if none is set."""
    out = ["-c", "commit.gpgSign=false"]
    if not _git("config", "user.name", check=False).stdout.strip():
        out += ["-c", "user.name=Orbit data sync"]
    if not _git("config", "user.email", check=False).stdout.strip():
        out += ["-c", "user.email=orbit-sync@localhost"]
    return out


def _new_empty_branch() -> None:
    """Start the branch from a new, empty history: nothing old, nothing from the main branch."""
    _drop_worktree()
    _git("branch", "-D", DATA_SYNC_BRANCH, check=False)
    _git("update-ref", "-d", _remote_ref(), check=False)
    tree = _git("mktree", input="").stdout.strip()
    root = _git(*_identity(), "commit-tree", tree, "-m", "Start the data branch").stdout.strip()
    _git("worktree", "add", "--force", "-B", DATA_SYNC_BRANCH, str(WORKTREE), root)


def _attach_to_remote() -> None:
    if not _worktree_ok():
        _drop_worktree()
        _git("worktree", "add", "--force", "-B", DATA_SYNC_BRANCH, str(WORKTREE), _remote_ref())
    _assert_worktree()
    _git("reset", "--hard", "--quiet", _remote_ref(), cwd=WORKTREE)
    _git("clean", "-fdq", cwd=WORKTREE)


def _assert_worktree() -> None:
    """Refuse to reset or clean anything but the data worktree (never the main checkout)."""
    top = _git("rev-parse", "--show-toplevel", cwd=WORKTREE, check=False).stdout.strip()
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=WORKTREE, check=False).stdout.strip()
    if not top or Path(top).resolve() != WORKTREE.resolve() or branch != DATA_SYNC_BRANCH:
        raise SyncError(f"{WORKTREE} is not the {DATA_SYNC_BRANCH} worktree; not touching it")


def _clear_stale_git_locks() -> None:
    """Remove git lock files left by a git process that was killed (we hold Orbit's own sync lock, so none is live)."""
    common = _common_dir(REPO_ROOT)
    candidates = []
    if common:
        candidates += [common / "refs" / "heads" / f"{DATA_SYNC_BRANCH}.lock",
                       common / "refs" / "remotes" / DATA_SYNC_REMOTE / f"{DATA_SYNC_BRANCH}.lock"]
    if (WORKTREE / ".git").exists():
        for name in ("index.lock", "HEAD.lock"):
            proc = _git("rev-parse", "--git-path", name, cwd=WORKTREE, check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                path = Path(proc.stdout.strip())
                candidates.append(path if path.is_absolute() else WORKTREE / path)
    now = time.time()
    for lock in candidates:
        try:
            if now - lock.stat().st_mtime > STALE_GIT_LOCK_SECONDS:
                lock.unlink()
        except OSError:
            pass


def _init_branch_files() -> None:
    # Store every file byte for byte: no line-ending conversion on any OS.
    for name, text in ((".gitattributes", "* -text\n"), ("README.md", BRANCH_README)):
        path = WORKTREE / name
        if not path.exists() or path.read_bytes() != text.encode("utf-8"):
            path.write_bytes(text.encode("utf-8"))


def _remove_strays() -> None:
    """Half-written temp files (an interrupted atomic write) must never be committed."""
    for pattern in (".*.tmp", "*.part"):
        for p in WORKTREE.rglob(pattern):
            if ".git" not in p.parts:
                p.unlink(missing_ok=True)


RACE_SIGNS = ("fetch first", "non-fast-forward", "cannot lock ref", "failed to update ref", "incorrect old value")


def _push(force: bool = False) -> tuple[str, str]:
    """('ok' | 'race' | 'failed', reason). A race means another machine pushed first."""
    spec = f"{'+' if force else ''}HEAD:refs/heads/{DATA_SYNC_BRANCH}"
    proc = _git(*NETWORK, "push", "--porcelain", DATA_SYNC_REMOTE, spec, cwd=WORKTREE, check=False)
    if proc.returncode == 0:
        return "ok", ""
    ref_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("!")]
    if any(("[rejected]" in ln or "[remote rejected]" in ln) and any(s in ln for s in RACE_SIGNS) for ln in ref_lines):
        return "race", ref_lines[0]
    detail = [ln.strip() for ln in (proc.stdout + proc.stderr).splitlines()
              if ln.startswith(("!", "remote:", "fatal:", "error:")) and "failed to push some refs" not in ln]
    return "failed", " | ".join(detail)[-600:] or "git push failed"


# ---------------------------------------------------------------- merge rules


@dataclass(frozen=True)
class CsvInfo:
    valid: bool
    spot: bool = False
    first: float = 0.0
    last: float = 0.0
    rows: int = 0

    def rank(self, built_at: str = "") -> tuple:
        # spot silver first; then the longer history (earlier first bar); then the newer full build (a deliberate
        # rebuild, from history_report.json); then the later last bar; then more bars
        return (self.valid, self.spot, -self.first, built_at, self.last, self.rows)


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def csv_info(path: Path) -> CsvInfo:
    """What a candle CSV holds, from its header, first and last rows. Anything malformed ranks lowest."""
    try:
        data = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return CsvInfo(False)
    lines = [ln for ln in data.splitlines() if ln.strip()]
    if len(lines) < 2 or next(csv.reader([lines[0]])) != CSV_HEADER:
        return CsvInfo(False)
    first, last = next(csv.reader([lines[1]])), next(csv.reader([lines[-1]]))
    if len(first) != len(CSV_HEADER) or len(last) != len(CSV_HEADER):
        return CsvInfo(False)
    try:
        [float(v) for v in last[1:6]]
        return CsvInfo(True, last[6].startswith("dukascopy:"), _epoch(first[0]), _epoch(last[0]), len(lines) - 1)
    except ValueError:
        return CsvInfo(False)


def csv_winner(local: Path, remote: Path, prefer_local: bool = False, local_built: str = "", remote_built: str = "") -> str | None:
    """Which file is the base: 'local', 'remote', or None if neither is usable. A tie goes to GitHub's copy;
    `prefer_local` makes this machine's (valid) file the base whatever the ranks say."""
    a = csv_info(local) if local.exists() else CsvInfo(False)
    b = csv_info(remote) if remote.exists() else CsvInfo(False)
    if not a.valid and not b.valid:
        return None
    if prefer_local and a.valid:
        return "local"
    ka, kb = a.rank(local_built), b.rank(remote_built)
    return "local" if ka > kb else "remote"


def extend_tail(base: bytes, other: bytes) -> bytes:
    """`base` plus the bars in `other` that come after base's last bar (so a newer bar is never dropped)."""
    base_lines = base.decode("utf-8").splitlines(keepends=True)
    last = next(ln for ln in reversed(base_lines) if ln.strip())
    last_ts = _epoch(last.split(",", 1)[0])
    tail = []
    for line in reversed(other.decode("utf-8").splitlines(keepends=True)[1:]):
        if not line.strip():
            continue
        row = next(csv.reader([line.strip()]))
        try:
            if len(row) != len(CSV_HEADER) or _epoch(row[0]) <= last_ts:
                break
        except ValueError:
            break
        tail.append(line if line.endswith("\n") else line + "\r\n")
    if not tail:
        return base
    text = "".join(base_lines)
    if not text.endswith("\n"):
        text += "\r\n"
    return (text + "".join(reversed(tail))).encode("utf-8")


def _other_decision_note(rec: dict) -> str:
    return f"[Also decided on another machine: {rec.get('decision')} at {rec.get('decided_at')}" + (
        f": {rec['notes']}]" if rec.get("notes") else "]")


def merge_journal(local: list[dict], remote: list[dict]) -> list[dict]:
    """Union by id. A decision beats pending/expired; the earliest decision stands and a different
    later one is kept in its notes; outcomes known on either side are kept."""
    order = {"decided": 2, "expired": 1, "pending": 0}
    merged: dict[str, dict] = {}
    for rec in [*remote, *local]:
        rid = rec.get("id")
        if not rid:
            continue
        cur = merged.get(rid)
        if cur is None:
            merged[rid] = dict(rec)
            continue
        a, b = cur, rec
        ka = (order.get(a.get("status"), 0), _neg_time(a.get("decided_at")))
        kb = (order.get(b.get("status"), 0), _neg_time(b.get("decided_at")))
        win, lose = (b, a) if kb > ka else (a, b)
        out = dict(win)
        if out.get("paper") is None and lose.get("paper") is not None:
            out["paper"] = lose["paper"]
        same = all(win.get(k) == lose.get(k) for k in ("decision", "acted_entry", "acted_stop", "acted_target"))
        if out.get("acted") is None and lose.get("acted") is not None and same:
            out["acted"] = lose["acted"]
        others = {(o.get("decision"), o.get("decided_at")): o for o in [*(win.get("other_decisions") or []), *(lose.get("other_decisions") or [])]}
        if win.get("status") == "decided" and lose.get("status") == "decided":
            win_notes, lose_notes = win.get("notes") or "", lose.get("notes") or ""
            if same and win.get("decided_at") == lose.get("decided_at"):
                if win_notes in lose_notes:  # the same decision; one copy already carries more notes
                    out["notes"] = lose_notes
            else:
                # Two people decided the same suggestion on different machines: the first decision stands, and the
                # other one (with its levels and its outcome) is kept alongside it, never dropped.
                others.setdefault((lose.get("decision"), lose.get("decided_at")),
                                  {k: lose.get(k) for k in ("decision", "decided_at", "notes", "acted_entry", "acted_stop", "acted_target", "acted")})
                if _other_decision_note(lose) not in win_notes:
                    out["notes"] = (win_notes + " " + _other_decision_note(lose)).strip()
        if others:
            out["other_decisions"] = sorted(others.values(), key=lambda o: o.get("decided_at") or "")
        merged[rid] = out
    return sorted(merged.values(), key=lambda r: (r.get("created_at") or "", r["id"]))


def _neg_time(iso: str | None) -> float:
    """Sort key where an earlier decision ranks higher; no decision ranks lowest."""
    if not iso:
        return float("-inf")
    try:
        return -datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _dump(obj) -> bytes:
    return (json.dumps(obj, indent=1) + "\n").encode("utf-8")


class _Merge:
    """Apply the rules to one pair of folders: local = data/, shared = the worktree."""

    def __init__(self, local: Path, shared: Path, include_journal: bool, prefer_local: bool = False):
        self.local, self.shared, self.include_journal, self.prefer_local = local, shared, include_journal, prefer_local
        self.pulled: list[str] = []
        self.pushed: list[str] = []
        self.warning: str | None = None

    def _take(self, rel: str, data: bytes, to_local: bool, to_shared: bool) -> None:
        lp, sp = self.local / rel, self.shared / rel
        if to_local and (not lp.exists() or lp.read_bytes() != data):
            atomic_write_bytes(lp, data)
            self.pulled.append(rel)
        if to_shared and (not sp.exists() or sp.read_bytes() != data):
            atomic_write_bytes(sp, data)
            self.pushed.append(rel)

    def prices(self) -> dict[str, str]:
        winners = {}
        lrep = _read_json(self.local / "history_report.json") or {}
        srep = _read_json(self.shared / "history_report.json") or {}
        names = {p.name for p in self.local.glob("*.csv")} | {p.name for p in self.shared.glob("*.csv")}
        for name in sorted(n for n in names if n.endswith(PRICE_SUFFIXES)):
            stem = name[: -len(".csv")]
            key = stem[: -len("_1d")] if stem.endswith("_1d") else stem  # history_report key: "BTC" or "BTC_1h"
            lp, sp = self.local / name, self.shared / name
            side = csv_winner(lp, sp, self.prefer_local, (lrep.get(key) or {}).get("built_at", ""), (srep.get(key) or {}).get("built_at", ""))
            if side is None:
                continue
            base_path, other_path = (lp, sp) if side == "local" else (sp, lp)
            data = base_path.read_bytes()
            base_info = csv_info(base_path)
            other_info = csv_info(other_path) if other_path.exists() else CsvInfo(False)
            if other_info.valid and other_info.spot == base_info.spot and other_info.last > base_info.last:
                data = extend_tail(data, other_path.read_bytes())
            self._take(name, data, to_local=True, to_shared=True)
            winners[name] = side
        return winners

    def report(self, winners: dict[str, str]) -> None:
        lrep = _read_json(self.local / "history_report.json") or {}
        srep = _read_json(self.shared / "history_report.json") or {}
        if not lrep and not srep:
            return
        out = {}
        for key in sorted(set(lrep) | set(srep)):
            asset, _, tf = key.partition("_")
            side = winners.get(f"{asset}_{tf or '1d'}.csv", "local")
            first, second = (srep, lrep) if side == "remote" else (lrep, srep)
            out[key] = first.get(key, second.get(key))
        data = json.dumps(out, indent=2).encode("utf-8")
        self._take("history_report.json", data, to_local=out != lrep, to_shared=out != srep)

    def union(self) -> None:
        rels: set[str] = set(UNION_FILES)
        for d in UNION_DIRS:
            for base in (self.local, self.shared):
                root = base / d
                if root.exists():
                    rels |= {p.relative_to(base).as_posix() for p in root.rglob("*")
                             if p.is_file() and not p.name.endswith((".part", ".tmp"))}
        for rel in sorted(rels):
            lp, sp = self.local / rel, self.shared / rel
            if not lp.exists() and not sp.exists():
                continue
            if lp.exists() and sp.exists():
                if lp.stat().st_size == sp.stat().st_size and lp.read_bytes() == sp.read_bytes():
                    continue
                keep_local = lp.stat().st_size > sp.stat().st_size
            else:
                keep_local = lp.exists()
            data = (lp if keep_local else sp).read_bytes()
            self._take(rel, data, to_local=not keep_local, to_shared=keep_local)

    def placebo(self) -> None:
        rel = "analysis/placebo.json"
        a, b = _read_json(self.local / rel), _read_json(self.shared / rel)
        if not a and not b:
            return
        a_time, b_time = (a or {}).get("checked_at", ""), (b or {}).get("checked_at", "")
        if b and b_time > a_time:
            self._take(rel, (self.shared / rel).read_bytes(), to_local=True, to_shared=False)
        elif a and a_time > b_time:
            self._take(rel, (self.local / rel).read_bytes(), to_local=False, to_shared=True)

    def journal(self) -> None:
        rel = "journal/suggestions.json"
        lp = self.local / rel
        a, b = _read_json(lp), _read_json(self.shared / rel)
        if lp.exists() and a is None:
            self.warning = "This machine's journal can't be read, so it wasn't synced; restore it from data/journal/backups/."
            return
        if a is None and b is None:
            return
        merged = merge_journal(a or [], b or [])
        data = json.dumps(merged, indent=1).encode("utf-8")
        if lp.exists() and merged != a:
            # Keep a copy of exactly what this machine had before the sync changed it.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            atomic_write_bytes(self.local / "journal" / "backups" / f"before-sync-{stamp}.json", lp.read_bytes())
        conflicts = sum(1 for r in merged if r.get("other_decisions")) - sum(1 for r in (a or []) if r.get("other_decisions"))
        if conflicts > 0:
            self.warning = f"{conflicts} suggestion(s) were decided differently on two machines; the first decision stands and the other is kept with it."
        self._take(rel, data, to_local=merged != (a or []), to_shared=merged != (b or []))

    def run(self) -> None:
        winners = self.prices()
        self.report(winners)
        self.union()
        self.placebo()
        if self.include_journal:
            from orbit.journal import store  # the journal's own lock: the API and runner write it too

            with store.locked():
                self.journal()


# ---------------------------------------------------------------- sync


def _state() -> dict:
    return _read_json(STATE) or {}


def _save_state(**fields) -> None:
    atomic_write_bytes(STATE, _dump({**_state(), **fields}))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def due(now: datetime | None = None) -> bool:
    """Once a day after a good sync; sooner (every few hours) after one that failed."""
    st = _state()
    last = st.get("last_attempt") or st.get("last_success")
    if not last:
        return True
    hours = DATA_SYNC_EVERY_HOURS if st.get("last_attempt_ok", True) else RETRY_HOURS_AFTER_ERROR
    return (now or datetime.now(timezone.utc)) - datetime.fromisoformat(last) >= timedelta(hours=hours)


def _preflight() -> str | None:
    if not DATA_SYNC_ENABLED:
        return "turned off (ORBIT_DATA_SYNC=0)"
    if shutil.which("git") is None:
        return "git isn't installed"
    top = _git("rev-parse", "--show-toplevel", check=False)
    if top.returncode or Path(top.stdout.strip()).resolve() != REPO_ROOT.resolve():
        return "this copy of Orbit isn't a git checkout"
    if _git("remote", "get-url", DATA_SYNC_REMOTE, check=False).returncode:
        return f"no git remote called {DATA_SYNC_REMOTE}"
    return None


def sync(push: bool = True, include_journal: bool | None = None, prefer_local: bool = False, recreate: bool = False) -> Result:
    """Pull the data branch, merge it with data/, and (if `push`) send back what this machine has that it doesn't."""
    why = _preflight()
    if why:
        return Result(skipped=why)
    if include_journal is None:
        include_journal = settings.DATA_SYNC_JOURNAL
    with file_lock(LOCK, timeout=300):
        try:
            result = _sync_locked(push, include_journal, prefer_local, recreate)
        except Exception as exc:
            _save_state(last_attempt=_now(), last_attempt_ok=False, last_error=f"{type(exc).__name__}: {exc}"[:800])
            raise
        return result


def _sync_locked(push: bool, include_journal: bool, prefer_local: bool, recreate: bool) -> Result:
    _clear_stale_git_locks()
    try:
        return _sync_rounds(push, include_journal, prefer_local, recreate)
    finally:
        _pack_loose_objects()


def _sync_rounds(push: bool, include_journal: bool, prefer_local: bool, recreate: bool) -> Result:
    result = Result()
    force = False
    for _ in range(PUSH_ATTEMPTS):
        remote_exists = _fetch()
        if remote_exists and not recreate:
            _attach_to_remote()
        elif (_state().get("branch_seen") or _state().get("last_success")) and not recreate:
            raise SyncError(
                f"the {DATA_SYNC_BRANCH} branch is gone from GitHub, though this machine has synced with it before. "
                "If it was deleted on purpose, turn the sync off (ORBIT_DATA_SYNC=0 in .env). To publish this machine's "
                "data again as a new branch, run: python scripts/sync_data.py --recreate"
            )
        elif not push:
            return result  # nothing on GitHub to take yet
        else:
            # The first sync ever, or --recreate: a new, empty history. Over an existing branch (--recreate) the
            # push replaces it in one step, so a failed push never leaves GitHub without the branch.
            _new_empty_branch()
            force, recreate = remote_exists, False
        _init_branch_files()
        merge = _Merge(DATA_DIR, WORKTREE, include_journal, prefer_local)
        merge.run()
        result.pulled = sorted(set(result.pulled) | set(merge.pulled))
        result.warning = merge.warning
        if not push:
            _save_state(last_pull=_now(), branch_seen=True)
            return result
        _remove_strays()
        _git("add", "-A", cwd=WORKTREE)
        if _git("diff", "--cached", "--quiet", cwd=WORKTREE, check=False).returncode == 0:
            break  # nothing this machine has that GitHub doesn't
        host = platform.node() or "unknown host"
        _git(*_identity(), "commit", "--quiet", "-m", f"Data from {host}: {len(merge.pushed)} file(s)", cwd=WORKTREE)
        outcome, reason = _push(force=force)
        if outcome == "ok":
            result.pushed = sorted(merge.pushed)
            result.commit = _git("rev-parse", "--short", "HEAD", cwd=WORKTREE).stdout.strip()
            break
        if outcome == "failed":
            # Can't push (no login, no write access, a server-side rule): keep what was pulled, drop the local
            # commit, and try again tomorrow rather than every hour.
            if _ref_exists(_remote_ref()):
                _git("reset", "--hard", "--quiet", _remote_ref(), cwd=WORKTREE)
            result.warning = " ".join(filter(None, [result.warning, f"Couldn't send this machine's data to GitHub ({reason[:200]}); will try again in a day."]))
            _save_state(last_success=_now(), last_attempt=_now(), last_attempt_ok=True, last_pull=_now(), branch_seen=remote_exists,
                        last_pulled=len(result.pulled), last_pushed=0, last_push_error=reason[-400:])
            return result
        # Another machine pushed first: fetch its data and merge again.
    else:
        raise SyncError(f"gave up after {PUSH_ATTEMPTS} attempts: the data branch kept moving")
    _save_state(last_success=_now(), last_attempt=_now(), last_attempt_ok=True, branch_seen=True,
                last_commit=result.commit, last_pulled=len(result.pulled), last_pushed=len(result.pushed), last_push_error=None)
    return result


def status() -> str:
    why = _preflight()
    if why:
        return f"Data sync: {why}."
    st = _state()
    remote = _git(*NETWORK, "ls-remote", "--heads", DATA_SYNC_REMOTE, DATA_SYNC_BRANCH, check=False).stdout.strip()
    lines = [
        f"branch     {DATA_SYNC_REMOTE}/{DATA_SYNC_BRANCH} {'exists' if remote else 'not on GitHub (the first sync creates it)'}",
        f"last sync  {st.get('last_success', 'never')}",
        f"last try   {st.get('last_attempt', 'never')}{'' if st.get('last_attempt_ok', True) else ' (failed: ' + str(st.get('last_error')) + ')'}",
        f"journal    {'shared' if settings.DATA_SYNC_JOURNAL else 'kept on this machine (ORBIT_DATA_SYNC_JOURNAL=1 to share)'}",
    ]
    if st.get("last_push_error"):
        lines.append(f"push       couldn't send last time: {st['last_push_error'][:300]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync Orbit's shared data with the GitHub data branch.")
    parser.add_argument("--pull", action="store_true", help="only take what's new from GitHub; send nothing")
    parser.add_argument("--status", action="store_true", help="show the sync state and exit")
    parser.add_argument("--prefer-local", action="store_true", help="on equal price files, send this machine's (a deliberate rebuild)")
    parser.add_argument("--recreate", action="store_true", help="publish this machine's data as a new branch (after it was deleted)")
    args = parser.parse_args(argv)
    if args.status:
        print(status())
        return 0
    try:
        print(sync(push=not args.pull, prefer_local=args.prefer_local, recreate=args.recreate).summary())
    except (SyncError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"Data sync failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
