"""Start, stop and check Orbit on any machine (Windows, macOS, Linux).

    python scripts/start_orbit.py            # API + web terminal, runner, silver download; opens the browser
    python scripts/stop_orbit.py
    python scripts/start_orbit.py --status
    python scripts/autostart.py              # start Orbit when you log in (--remove to undo)

Before starting the services, start_orbit syncs the shared data with GitHub
(src/orbit/datasync.py), so a fresh clone begins with the full histories and
the silver cache instead of downloading them again.

Each background process is started detached with its output in
data/logs/<name>.out, and its pid is kept in data/run/<name>.json so it can be
found and stopped again. Safe to run twice: anything already running is left
alone. Standard library only, so it works before anything else is installed.

Autostart, per OS, all per-user and without admin rights:
    Windows  a small .cmd in the Startup folder
    macOS    a LaunchAgent (~/Library/LaunchAgents/com.orbit.start.plist)
    Linux    an XDG autostart entry (~/.config/autostart/orbit.desktop)
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from orbit.fsutil import alive

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RUN_DIR = DATA / "run"
LOG_DIR = DATA / "logs"
WEB = ROOT / "web"
WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"


@dataclass(frozen=True)
class Service:
    name: str
    args: list[str]  # after the python executable
    what: str


API = Service("api", ["-m", "orbit.api"], "API + web terminal")
RUNNER = Service("runner", ["-m", "orbit.runner.loop"], "runner (hourly data, daily analysis at 00:30 UTC)")
SILVER = Service("silver", [str(ROOT / "scripts" / "backfill_silver.py")], "silver download (resumes where it stopped)")
SERVICES = [API, RUNNER, SILVER]


def python() -> str:
    """The project's own interpreter (.venv), falling back to the one running this."""
    venv = ROOT / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
    return str(venv if venv.exists() else Path(sys.executable))


def api_url() -> str:
    host = os.getenv("ORBIT_API_HOST", "127.0.0.1")
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{os.getenv('ORBIT_API_PORT', '8000')}"


# ---------------------------------------------------------------- processes


def command_of(pid: int) -> str:
    """The process's command line (or image path on Windows), '' if unknown."""
    try:
        if WINDOWS:
            import ctypes
            from ctypes import wintypes

            k32 = ctypes.windll.kernel32
            handle = k32.OpenProcess(0x1000, False, pid)
            if not handle:
                return ""
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            ok = k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            k32.CloseHandle(handle)
            return buf.value if ok else ""
        proc = Path(f"/proc/{pid}/cmdline")
        if proc.exists():
            return proc.read_bytes().replace(b"\0", b" ").decode(errors="replace")
        out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _looks_like(pid: int, service: Service) -> bool:
    """Guard against a recycled pid: the process must at least be Python (and, where visible, this service)."""
    cmd = command_of(pid).lower()
    if not cmd:
        return True  # can't tell; trust the pid file
    if "python" not in cmd:
        return False
    return WINDOWS or service.args[-1].lower() in cmd


def _pid_file(service: Service) -> Path:
    return RUN_DIR / f"{service.name}.json"


def running_pid(service: Service) -> int | None:
    """The pid of this service if it's running (started here, or the runner by any means)."""
    candidates = []
    try:
        candidates.append(int(json.loads(_pid_file(service).read_text(encoding="utf-8"))["pid"]))
    except (OSError, ValueError, KeyError):
        pass
    if service is RUNNER:
        try:
            candidates.append(int(json.loads((DATA / "runner_status.json").read_text(encoding="utf-8"))["pid"]))
        except (OSError, ValueError, KeyError):
            pass
    return next((p for p in candidates if alive(p) and _looks_like(p, service)), None)


def claim(service: Service) -> None:
    """Record this process as the running `service` (for one started by hand, not by start_orbit)."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    current = running_pid(service)
    if current in (os.getpid(), os.getppid()):
        return  # start_orbit already recorded us (or the launcher stub that started us)
    _pid_file(service).write_text(json.dumps({"pid": os.getpid(), "args": service.args, "started_at": time.time()}), encoding="utf-8")


def api_responding(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(api_url() + "/api/system", timeout=timeout) as r:
            return r.status == 200
    except OSError:
        return False


def spawn(service: Service) -> int:
    """Start a service detached from this console, output to data/logs/<name>.out."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    out = open(LOG_DIR / f"{service.name}.out", "ab")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    kwargs: dict = {"cwd": ROOT, "stdin": subprocess.DEVNULL, "stdout": out, "stderr": subprocess.STDOUT, "env": env}
    if WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW | 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([python(), *service.args], **kwargs)
    _pid_file(service).write_text(json.dumps({"pid": proc.pid, "args": service.args, "started_at": time.time()}), encoding="utf-8")
    return proc.pid


def terminate(pid: int, wait: float = 10.0) -> None:
    if WINDOWS:
        # Not /T: an analysis run the runner started must be left to finish. The venv's python.exe
        # stub holds its real interpreter in a kill-on-close job, so this still takes both.
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        deadline = time.time() + wait
        while time.time() < deadline and alive(pid):
            time.sleep(0.2)
        return
    try:
        os.killpg(pid, signal.SIGTERM)  # its own session: take any children with it
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
    deadline = time.time() + wait
    while time.time() < deadline and alive(pid):
        time.sleep(0.2)
    if alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


# ---------------------------------------------------------------- web build


def _newest_mtime(folder: Path) -> float:
    return max((p.stat().st_mtime for p in folder.rglob("*") if p.is_file()), default=0.0)


def build_web_if_stale(say=print) -> None:
    """Rebuild web/dist when the web sources are newer than the last build (needs Node/npm)."""
    dist = WEB / "dist" / "index.html"
    sources = [WEB / "src", WEB / "index.html", WEB / "package.json"]
    newest = max(_newest_mtime(s) if s.is_dir() else (s.stat().st_mtime if s.exists() else 0.0) for s in sources)
    if dist.exists() and dist.stat().st_mtime >= newest:
        return
    npm = shutil.which("npm")
    if not npm:
        say("! Node.js/npm not found, so the web terminal can't be built. Install Node 20+ (nodejs.org) and run this again."
            if not dist.exists() else "! Web sources changed but npm isn't installed; serving the previous build.")
        return
    say("Building the web terminal...")
    if not (WEB / "node_modules").exists():
        subprocess.run([npm, "ci", "--no-fund", "--no-audit"], cwd=WEB, check=False)
    result = subprocess.run([npm, "run", "build"], cwd=WEB, capture_output=True, text=True)
    if result.returncode:
        say("! Web build failed:\n" + (result.stdout + result.stderr)[-2000:])


def sync_data(say=print) -> None:
    """Pull (and push) the shared data branch. A failure is a warning, never a reason not to start."""
    say("Syncing data with GitHub (the first time on a new machine can take a few minutes)...")
    try:
        out = subprocess.run([python(), "-m", "orbit.datasync"], cwd=ROOT, capture_output=True, text=True, timeout=900,
                             encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired:
        say("! Data sync took too long; starting with the data already here. Run python scripts/sync_data.py later.")
        return
    for line in (out.stdout + out.stderr).strip().splitlines()[-4:]:
        say(("! " if out.returncode else "") + line)


def silver_complete() -> bool:
    check = "from orbit.data.history import silver_cache_complete as c; import sys; sys.exit(0 if c() else 1)"
    return subprocess.run([python(), "-c", check], cwd=ROOT, capture_output=True).returncode == 0


# ---------------------------------------------------------------- commands


def start(open_browser: bool = True, say=print) -> int:
    if not (ROOT / ".venv").exists() and not shutil.which("uv"):
        say("No .venv yet. Install uv (docs.astral.sh/uv), then run 'uv sync --extra dev' in " + str(ROOT))
        return 1
    if not (ROOT / ".venv").exists():
        say("Setting up the Python environment (uv sync)...")
        subprocess.run(["uv", "sync", "--extra", "dev"], cwd=ROOT, check=True)
    build_web_if_stale(say)
    if not running_pid(RUNNER):
        sync_data(say)  # while the runner is up, it syncs on its own schedule

    if running_pid(API) or api_responding():
        say(f"API already running at {api_url()}.")
    else:
        say(f"Started the {API.what} (pid {spawn(API)}).")
    if pid := running_pid(RUNNER):
        say(f"Runner already running (pid {pid}).")
    else:
        say(f"Started the {RUNNER.what} (pid {spawn(RUNNER)}).")
    if running_pid(SILVER):
        say("Silver download already running.")
    elif not silver_complete():
        say(f"Started the {SILVER.what} (pid {spawn(SILVER)}).")

    for _ in range(60):
        if api_responding():
            break
        time.sleep(1)
    else:
        say(f"! The API didn't answer within a minute. See {LOG_DIR / 'api.out'}")
        return 1
    say(f"Orbit is at {api_url()}")
    if open_browser:
        webbrowser.open(api_url())
    return 0


def stop(say=print) -> int:
    stopped = 0
    for service in SERVICES:
        pid = running_pid(service)
        if pid:
            terminate(pid)
            say(f"Stopped the {service.name} (pid {pid}).")
            stopped += 1
        _pid_file(service).unlink(missing_ok=True)
    if api_responding(timeout=1):
        say(f"! Something is still serving {api_url()} that wasn't started by start_orbit; stop it where it was started.")
    if not stopped:
        say("Nothing to stop.")
    say("An analysis run already in progress finishes on its own; the next one starts fresh if you stop it.")
    return 0


def status(say=print) -> int:
    for service in SERVICES:
        pid = running_pid(service)
        if service is API and not pid and api_responding():
            say(f"api      running (not started by start_orbit) at {api_url()}")
        elif service is SILVER and not pid:
            say(f"silver   {'complete' if silver_complete() else 'not running, incomplete: start_orbit resumes it'}")
        else:
            say(f"{service.name:8s} {'running, pid ' + str(pid) if pid else 'stopped'}")
    say(f"web      {'built' if (WEB / 'dist' / 'index.html').exists() else 'not built (needs Node/npm)'}")
    try:
        last = json.loads((DATA / "run" / "sync.json").read_text(encoding="utf-8")).get("last_success", "never")
    except (OSError, ValueError):
        last = "never"
    say(f"data sync last {last} (python scripts/sync_data.py --status)")
    auto = autostart_path()
    say(f"autostart {'on (' + str(auto) + ')' if auto.exists() else 'off'}")
    return 0


# ---------------------------------------------------------------- autostart


def autostart_path() -> Path:
    home = Path.home()
    if WINDOWS:
        return Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Microsoft/Windows/Start Menu/Programs/Startup/Orbit.cmd"
    if MAC:
        return home / "Library/LaunchAgents/com.orbit.start.plist"
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "autostart/orbit.desktop"


def install_autostart(say=print) -> int:
    path = autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    script = ROOT / "scripts" / "start_orbit.py"
    py = python()
    if WINDOWS:
        pyw = Path(py).with_name("pythonw.exe")
        path.write_text(f'@start "" "{pyw if pyw.exists() else py}" "{script}" --no-browser\r\n', encoding="utf-8")
    elif MAC:
        path.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.orbit.start</string>
  <key>ProgramArguments</key>
  <array><string>{py}</string><string>{script}</string><string>--no-browser</string></array>
  <key>WorkingDirectory</key><string>{ROOT}</string>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{LOG_DIR / 'autostart.out'}</string>
  <key>StandardErrorPath</key><string>{LOG_DIR / 'autostart.out'}</string>
</dict>
</plist>
""",
            encoding="utf-8",
        )
    else:
        path.write_text(
            f"[Desktop Entry]\nType=Application\nName=Orbit\nComment=Start Orbit (API + runner)\n"
            f'Exec="{py}" "{script}" --no-browser\nPath={ROOT}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n',
            encoding="utf-8",
        )
    say(f"Orbit will start when you log in ({path}). Undo with: python scripts/autostart.py --remove")
    return 0


def remove_autostart(say=print) -> int:
    path = autostart_path()
    if path.exists():
        path.unlink()
        say(f"Removed {path}. Orbit no longer starts at login.")
    else:
        say("Autostart wasn't set up.")
    return 0
