"""A single pty-backed child process, its output ring, and its rendered screen.

Only ever touched from the daemon's single event-loop thread — no locking.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field

import pyte
from ptyprocess import PtyProcess

from .ring import RingBuffer

DEFAULT_ROWS = 24
DEFAULT_COLS = 80
DEFAULT_RING_CAPACITY = 1024 * 1024  # 1 MiB of raw scrollback per session

# Pinned so TUI output is reproducible regardless of the daemon's own environment.
_BASE_ENV = {
    "TERM": "xterm-256color",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}


@dataclass
class ExitInfo:
    code: int | None = None
    signal: int | None = None

    def to_dict(self) -> dict | None:
        if self.code is None and self.signal is None:
            return None
        return {"code": self.code, "signal": self.signal}


@dataclass
class Session:
    id: str
    argv: list[str]
    rows: int = DEFAULT_ROWS
    cols: int = DEFAULT_COLS
    cwd: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    ring_capacity: int = DEFAULT_RING_CAPACITY

    def __post_init__(self) -> None:
        env = dict(os.environ)
        env.update(_BASE_ENV)
        env["COLUMNS"] = str(self.cols)
        env["LINES"] = str(self.rows)
        env.update(self.extra_env)

        self.proc = PtyProcess.spawn(
            self.argv,
            cwd=self.cwd,
            env=env,
            dimensions=(self.rows, self.cols),
        )
        self.fd = self.proc.fd
        self.pid = self.proc.pid

        self.ring = RingBuffer(self.ring_capacity)
        self.screen = pyte.HistoryScreen(self.cols, self.rows, history=2000)
        self.stream = pyte.Stream(self.screen)

        self.alive = True
        self.exit_info = ExitInfo()
        self.created_at = time.time()
        self.last_data_ts = self.created_at

    # -- output ----------------------------------------------------------

    def drain(self) -> None:
        """Called when self.fd is readable. Pull whatever's available into the ring
        and screen. Treats EOFError (raised by ptyprocess, including on the macOS
        EIO-after-exit quirk) as a clean child-exit signal, not a daemon error."""
        try:
            data = self.proc.read(65536)
        except EOFError:
            self._reap()
            return
        if data:
            self.ring.append(data)
            self.last_data_ts = time.time()
            try:
                self.stream.feed(data.decode("utf-8", errors="replace"))
            except Exception:
                # A malformed escape sequence should never take the daemon down.
                pass
        if not self.proc.isalive():
            self._reap()

    def _reap(self) -> None:
        if not self.alive:
            return
        self.alive = False
        try:
            self.proc.wait()
        except Exception:
            pass
        self.exit_info = ExitInfo(code=self.proc.exitstatus, signal=self.proc.signalstatus)

    # -- input -------------------------------------------------------------

    def write(self, data: bytes) -> None:
        if not self.alive:
            raise BrokenPipeError(f"session {self.id} is not alive")
        self.proc.write(data)

    # -- control -------------------------------------------------------------

    def resize(self, rows: int, cols: int) -> None:
        self.rows, self.cols = rows, cols
        if self.alive:
            self.proc.setwinsize(rows, cols)
        self.screen.resize(lines=rows, columns=cols)

    def send_signal(self, sig: int) -> None:
        """Signal the whole process group, not just the child, so pipelines and
        subshells spawned by the child are reached too."""
        if not self.alive:
            return
        try:
            os.killpg(self.pid, sig)
        except ProcessLookupError:
            pass

    def kill(self, grace_seconds: float = 0.0) -> None:
        self.send_signal(signal.SIGTERM)
        if grace_seconds:
            time.sleep(grace_seconds)
            if self.alive and self.proc.isalive():
                self.send_signal(signal.SIGKILL)

    # -- views -------------------------------------------------------------

    def screen_view(self) -> dict:
        cursor = self.screen.cursor
        return {
            "lines": self.screen.display,
            "cursor": {"x": cursor.x, "y": cursor.y, "hidden": cursor.hidden},
            # 1049 is xterm's "save cursor + switch to alt screen" mode. pyte
            # stores private (DECSET) mode numbers shifted left 5 bits in
            # screen.mode, to distinguish them from ANSI mode numbers.
            "alt_screen": (1049 << 5) in self.screen.mode,
            "title": getattr(self.screen, "title", ""),
            "rows": self.rows,
            "cols": self.cols,
        }

    def to_summary(self) -> dict:
        return {
            "session_id": self.id,
            "argv": self.argv,
            "pid": self.pid,
            "alive": self.alive,
            "rows": self.rows,
            "cols": self.cols,
            "created_at": self.created_at,
            "exit": self.exit_info.to_dict(),
        }
