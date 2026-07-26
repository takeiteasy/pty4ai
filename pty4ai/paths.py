"""Resolve where the daemon's socket, PID file, and log live.

Uses $XDG_RUNTIME_DIR when set (typically tmpfs, cleaned on reboot); falls back to
~/.local/state/pty4ai otherwise. The directory is created with mode 0700 so socket
access is restricted to the owning user.
"""

from __future__ import annotations

import os
from pathlib import Path


def state_dir() -> Path:
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(xdg) / "pty4ai" if xdg else Path.home() / ".local" / "state" / "pty4ai"
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    return base


def socket_path() -> Path:
    path = state_dir() / "daemon.sock"
    # AF_UNIX's sun_path is ~104 bytes on macOS / ~108 on Linux; past that,
    # bind()/connect() fail with a low-level OSError that just looks like the
    # daemon never came up. Fail loudly here instead.
    if len(str(path).encode()) > 100:
        raise OSError(
            f"pty4ai state dir socket path too long for AF_UNIX ({path}); "
            "set XDG_RUNTIME_DIR to something shorter"
        )
    return path


def pid_path() -> Path:
    return state_dir() / "daemon.pid"


def log_path() -> Path:
    return state_dir() / "daemon.log"
