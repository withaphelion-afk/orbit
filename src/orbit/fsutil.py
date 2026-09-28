"""Small file-system helpers shared by processes that write the same files:
atomic writes (readers never see half a file), a cross-process lock, and a
"is this process alive" check. Standard library only.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

WINDOWS = sys.platform == "win32"


def atomic_write_bytes(path: Path, data: bytes, attempts: int = 20) -> None:
    """Write `data` to `path` via a temp file and a rename.

    On Windows a rename onto a file another process has open fails for a
    moment, so it is retried briefly instead of giving up.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    for k in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if k == attempts - 1:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.1 * (k + 1))


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def alive(pid: int) -> bool:
    """True if a process with this pid is running."""
    if pid <= 0:
        return False
    if WINDOWS:
        import ctypes

        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
        k32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class LockTimeout(TimeoutError):
    pass


def _try_lock(fd: int) -> bool:
    try:
        if WINDOWS:
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    try:
        if WINDOWS:
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def file_lock(path: Path, timeout: float = 60.0):
    """Hold an exclusive lock across processes (and threads), using the OS's own file lock.

    The operating system releases the lock the moment its holder exits or is
    killed, so a crashed process can never leave everyone else waiting. The
    lock file itself stays in place; only the lock on it matters.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + timeout
        while not _try_lock(fd):
            if time.monotonic() > deadline:
                raise LockTimeout(f"{path} is held by another process")
            time.sleep(0.1)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)
