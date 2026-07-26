"""Client library: talks to the daemon over its unix socket, auto-starting it if
nothing answers. Backs both the CLI (cli.py) and direct library use.

One socket connection per request/response pair — see protocol.py for why.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from typing import Any

from . import paths
from .errors import DaemonError, Pty4aiError, SessionNotFound
from .protocol import LineReader, send_line

CONNECT_RETRY_INTERVAL = 0.05
AUTOSTART_TIMEOUT = 5.0


def _try_connect() -> socket.socket | None:
    sock_path = paths.socket_path()
    if not sock_path.exists():
        return None
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(sock_path))
        return sock
    except OSError:
        sock.close()
        return None


def _autostart_daemon() -> None:
    subprocess.Popen(
        [sys.executable, "-m", "pty4ai.daemon"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + AUTOSTART_TIMEOUT
    while time.time() < deadline:
        sock = _try_connect()
        if sock is not None:
            sock.close()
            return
        time.sleep(CONNECT_RETRY_INTERVAL)
    raise Pty4aiError("timed out waiting for daemon to start")


class Client:
    """Not thread-safe; open one per caller. Each request opens its own connection,
    so instances are cheap and hold no persistent socket between calls."""

    def __init__(self, autostart: bool = True) -> None:
        self._autostart = autostart

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def _request(self, op: str, **params: Any) -> dict[str, Any]:
        sock = _try_connect()
        if sock is None:
            if not self._autostart:
                raise Pty4aiError("daemon not running and autostart=False")
            _autostart_daemon()
            sock = _try_connect()
            if sock is None:
                raise Pty4aiError("daemon did not come up")
        try:
            send_line(sock, {"op": op, **params})
            reply = LineReader(sock).read_obj()
        finally:
            sock.close()
        if reply is None:
            raise DaemonError(f"daemon closed connection without responding to {op!r}")
        if "error" in reply:
            msg = reply["error"]
            if "no such session" in msg:
                raise SessionNotFound(msg)
            raise DaemonError(msg)
        return reply

    # -- ops -------------------------------------------------------------

    def spawn(
        self,
        argv: list[str],
        *,
        rows: int = 24,
        cols: int = 80,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict:
        return self._request("spawn", argv=argv, rows=rows, cols=cols, cwd=cwd, env=env)

    def send(self, session_id: str, text: str, *, enter: bool = True) -> dict:
        return self._request("send", session_id=session_id, text=text, enter=enter)

    def keys(self, session_id: str, names: list[str]) -> dict:
        return self._request("keys", session_id=session_id, names=names)

    def read(
        self,
        session_id: str,
        *,
        since: int = 0,
        idle_ms: int = 300,
        timeout_ms: int = 10_000,
        expect: str | None = None,
    ) -> dict:
        return self._request(
            "read",
            session_id=session_id,
            since=since,
            idle_ms=idle_ms,
            timeout_ms=timeout_ms,
            expect=expect,
        )

    def screen(self, session_id: str) -> dict:
        return self._request("screen", session_id=session_id)

    def wait(self, session_id: str, *, timeout_ms: int = 10_000) -> dict:
        return self._request("wait", session_id=session_id, timeout_ms=timeout_ms)

    def resize(self, session_id: str, rows: int, cols: int) -> dict:
        return self._request("resize", session_id=session_id, rows=rows, cols=cols)

    def list(self) -> dict:
        return self._request("list")

    def kill(self, session_id: str, *, signal: str | None = None, grace_seconds: float = 0.5) -> dict:
        return self._request("kill", session_id=session_id, signal=signal, grace_seconds=grace_seconds)

    def shutdown(self) -> dict:
        return self._request("shutdown")

    def ping(self) -> dict:
        return self._request("ping")
