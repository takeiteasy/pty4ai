"""The daemon: a single-threaded event loop over one listening socket, N client
connections, and N pty master fds, plus a list of pending read/wait operations
that complete asynchronously (idle-quiescence / expect / timeout).

Started via `pty4ai.daemon.main()`, normally auto-spawned by client.Client when
no daemon is reachable at the resolved socket path.
"""

from __future__ import annotations

import logging
import os
import re
import selectors
import signal
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from . import paths
from .protocol import LineReader, send_line
from .session import DEFAULT_COLS, DEFAULT_ROWS, Session

log = logging.getLogger("pty4ai.daemon")

DEFAULT_IDLE_MS = 300
DEFAULT_TIMEOUT_MS = 10_000
POLL_INTERVAL_WITH_PENDING = 0.05  # seconds; how often pending ops are re-checked


@dataclass
class ConnState:
    sock: socket.socket
    reader: LineReader
    awaiting_response: bool = False


@dataclass
class PendingRead:
    conn: ConnState
    session_id: str
    since: int
    idle_ms: int
    timeout_ms: int
    expect: re.Pattern | None
    start_ts: float = field(default_factory=time.time)

    def check(self, session: Session | None) -> dict | None:
        now = time.time()
        elapsed_ms = (now - self.start_ts) * 1000

        if session is None:
            # Unreachable today (sessions are never evicted, see TICKETS.md);
            # kept shaped like _result so an eviction landing later can't
            # silently hand callers a response missing `since`/`data`.
            return {
                "session_id": self.session_id,
                "data": "",
                "since": self.since,
                "truncated": False,
                "reason": "eof",
                "alive": False,
                "exit": None,
                "session_gone": True,
            }

        data, new_seq, truncated = session.ring.read_since(self.since)
        has_data = new_seq > self.since

        if self.expect is not None and data:
            text = data.decode("utf-8", errors="replace")
            if self.expect.search(text):
                return self._result(data, new_seq, truncated, "expect", session)

        if not session.alive:
            return self._result(data, new_seq, truncated, "eof", session)

        # Idle quiescence only applies when the caller isn't waiting on a
        # specific `expect` pattern -- an explicit expect means "wait for
        # this, or time out" full stop, never bail out early just because
        # it's gone quiet (matched or not). Without expect, a caller asking
        # "did anything change?" on an already-settled session should get a
        # fast "quiet"/"idle" answer rather than the full timeout every time.
        if self.expect is None:
            # The clock starts at whichever is later, the session's last
            # write or this request's own arrival -- never at session
            # creation, or a read arriving well after spawn on a program
            # that's simply slow to print its first output would return an
            # instant false "quiet".
            idle_since = max(session.last_data_ts, self.start_ts)
            idle_for_ms = (now - idle_since) * 1000
            if idle_for_ms >= self.idle_ms:
                reason = "idle" if has_data else "quiet"
                return self._result(data, new_seq, truncated, reason, session)

        if elapsed_ms >= self.timeout_ms:
            return self._result(data, new_seq, truncated, "timeout", session)

        return None

    def _result(self, data: bytes, new_seq: int, truncated: bool, reason: str, session: Session) -> dict:
        return {
            "session_id": self.session_id,
            "data": data.decode("utf-8", errors="replace"),
            "since": new_seq,
            "truncated": truncated,
            "reason": reason,
            "alive": session.alive,
            "exit": session.exit_info.to_dict(),
        }


@dataclass
class PendingWait:
    conn: ConnState
    session_id: str
    timeout_ms: int
    start_ts: float = field(default_factory=time.time)

    def check(self, session: Session | None) -> dict | None:
        if session is None:
            return {"session_id": self.session_id, "alive": False, "exit": None, "reason": "eof"}
        if not session.alive:
            return {
                "session_id": self.session_id,
                "alive": False,
                "exit": session.exit_info.to_dict(),
                "reason": "exited",
            }
        if (time.time() - self.start_ts) * 1000 >= self.timeout_ms:
            return {"session_id": self.session_id, "alive": True, "exit": None, "reason": "timeout"}
        return None


class Daemon:
    def __init__(self) -> None:
        self.sel = selectors.DefaultSelector()
        self.sessions: dict[str, Session] = {}
        self.conns: dict[int, ConnState] = {}
        self.pending: list[PendingRead | PendingWait] = []
        self.listener: socket.socket | None = None
        self._stop = False

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        sock_path = paths.socket_path()
        if sock_path.exists():
            sock_path.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(sock_path))
        os.chmod(sock_path, 0o600)
        listener.listen(64)
        listener.setblocking(False)
        self.listener = listener
        self.sel.register(listener, selectors.EVENT_READ, self._accept)

        paths.pid_path().write_text(str(os.getpid()))
        signal.signal(signal.SIGTERM, lambda *_: self._request_stop())
        signal.signal(signal.SIGINT, lambda *_: self._request_stop())
        log.info("daemon listening on %s pid=%d", sock_path, os.getpid())

    def _request_stop(self) -> None:
        self._stop = True

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop:
                timeout = POLL_INTERVAL_WITH_PENDING if self.pending else None
                events = self.sel.select(timeout=timeout)
                for key, _mask in events:
                    callback: Callable[[], None] = key.data
                    try:
                        callback()
                    except Exception:
                        log.exception("handler error on fd=%s", key.fd)
                self._service_pending()
        finally:
            self._shutdown_all()

    # -- socket plumbing -------------------------------------------------------------

    def _accept(self) -> None:
        assert self.listener is not None
        try:
            sock, _ = self.listener.accept()
        except OSError:
            return
        sock.setblocking(False)
        state = ConnState(sock=sock, reader=LineReader(sock))
        self.conns[sock.fileno()] = state
        self.sel.register(sock, selectors.EVENT_READ, lambda: self._on_conn_readable(state))

    def _on_conn_readable(self, state: ConnState) -> None:
        try:
            obj = state.reader.read_obj()
        except (ConnectionError, OSError):
            self._close_conn(state)
            return
        if obj is None:
            self._close_conn(state)
            return
        self._dispatch(state, obj)

    def _close_conn(self, state: ConnState) -> None:
        fd = state.sock.fileno()
        try:
            self.sel.unregister(state.sock)
        except (KeyError, ValueError, OSError):
            pass
        self.conns.pop(fd, None)
        try:
            state.sock.close()
        except OSError:
            pass

    def _respond(self, state: ConnState, obj: dict[str, Any]) -> None:
        try:
            send_line(state.sock, obj)
        except OSError:
            pass
        self._close_conn(state)

    # -- session fd plumbing -------------------------------------------------------------

    def _register_session_fd(self, session: Session) -> None:
        self.sel.register(session.fd, selectors.EVENT_READ, lambda: self._on_session_readable(session))

    def _on_session_readable(self, session: Session) -> None:
        was_alive = session.alive
        session.drain()
        if was_alive and not session.alive:
            try:
                self.sel.unregister(session.fd)
            except (KeyError, ValueError, OSError):
                pass

    def _service_pending(self) -> None:
        if not self.pending:
            return
        still_pending = []
        for op in self.pending:
            session = self.sessions.get(op.session_id)
            result = op.check(session)
            if result is None:
                still_pending.append(op)
            else:
                self._respond(op.conn, result)
        self.pending = still_pending

    # -- request dispatch -------------------------------------------------------------

    def _dispatch(self, state: ConnState, req: dict[str, Any]) -> None:
        op = req.get("op")
        handler = getattr(self, f"_op_{op}", None)
        if handler is None:
            self._respond(state, {"error": f"unknown op: {op!r}"})
            return
        try:
            handler(state, req)
        except Exception as exc:  # never let a bad request kill the daemon
            log.exception("op %s failed", op)
            self._respond(state, {"error": str(exc)})

    def _get_session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"no such session: {session_id}")
        return session

    def _op_spawn(self, state: ConnState, req: dict[str, Any]) -> None:
        sid = uuid.uuid4().hex[:12]
        session = Session(
            id=sid,
            argv=req["argv"],
            rows=req.get("rows", DEFAULT_ROWS),
            cols=req.get("cols", DEFAULT_COLS),
            cwd=req.get("cwd"),
            extra_env=req.get("env") or {},
        )
        self.sessions[sid] = session
        self._register_session_fd(session)
        self._respond(state, session.to_summary())

    def _op_send(self, state: ConnState, req: dict[str, Any]) -> None:
        session = self._get_session(req["session_id"])
        text = req.get("text", "")
        data = text.encode("utf-8")
        if req.get("enter", True):
            data += b"\r"
        session.write(data)
        self._respond(state, {"session_id": session.id, "written": len(data)})

    def _op_keys(self, state: ConnState, req: dict[str, Any]) -> None:
        from .keys import key_bytes

        session = self._get_session(req["session_id"])
        for name in req["names"]:
            session.write(key_bytes(name))
        self._respond(state, {"session_id": session.id, "sent": req["names"]})

    def _op_read(self, state: ConnState, req: dict[str, Any]) -> None:
        session = self._get_session(req["session_id"])
        op = PendingRead(
            conn=state,
            session_id=session.id,
            since=req.get("since", 0),
            idle_ms=req.get("idle_ms", DEFAULT_IDLE_MS),
            timeout_ms=req.get("timeout_ms", DEFAULT_TIMEOUT_MS),
            expect=re.compile(req["expect"]) if req.get("expect") else None,
        )
        result = op.check(session)
        if result is not None:
            self._respond(state, result)
        else:
            self.pending.append(op)

    def _op_screen(self, state: ConnState, req: dict[str, Any]) -> None:
        session = self._get_session(req["session_id"])
        view = session.screen_view()
        view["session_id"] = session.id
        view["alive"] = session.alive
        self._respond(state, view)

    def _op_wait(self, state: ConnState, req: dict[str, Any]) -> None:
        session = self._get_session(req["session_id"])
        op = PendingWait(conn=state, session_id=session.id, timeout_ms=req.get("timeout_ms", DEFAULT_TIMEOUT_MS))
        result = op.check(session)
        if result is not None:
            self._respond(state, result)
        else:
            self.pending.append(op)

    def _op_resize(self, state: ConnState, req: dict[str, Any]) -> None:
        session = self._get_session(req["session_id"])
        session.resize(req["rows"], req["cols"])
        self._respond(state, session.to_summary())

    def _op_list(self, state: ConnState, req: dict[str, Any]) -> None:
        self._respond(state, {"sessions": [s.to_summary() for s in self.sessions.values()]})

    def _op_kill(self, state: ConnState, req: dict[str, Any]) -> None:
        session = self._get_session(req["session_id"])
        sig = req.get("signal")
        if sig:
            session.send_signal(getattr(signal, f"SIG{sig}") if isinstance(sig, str) else sig)
        else:
            session.kill(grace_seconds=req.get("grace_seconds", 0.5))
        self._respond(state, session.to_summary())

    def _op_shutdown(self, state: ConnState, req: dict[str, Any]) -> None:
        self._respond(state, {"ok": True})
        self._request_stop()

    def _op_ping(self, state: ConnState, req: dict[str, Any]) -> None:
        self._respond(state, {"ok": True, "pid": os.getpid()})

    # -- teardown -------------------------------------------------------------

    def _shutdown_all(self) -> None:
        for session in self.sessions.values():
            if session.alive:
                session.kill(grace_seconds=0.3)
        for op in self.pending:
            try:
                send_line(op.conn.sock, {"error": "daemon shutting down"})
            except OSError:
                pass
        try:
            if self.listener:
                self.listener.close()
        except OSError:
            pass
        sock_path = paths.socket_path()
        pid_path = paths.pid_path()
        for p in (sock_path, pid_path):
            try:
                p.unlink()
            except OSError:
                pass


def main() -> None:
    logging.basicConfig(
        filename=str(paths.log_path()),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    Daemon().run_forever()


if __name__ == "__main__":
    main()
