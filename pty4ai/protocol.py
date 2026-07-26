"""Newline-delimited JSON framing over a unix socket.

One JSON object per line, both directions. Kept deliberately dumb: no length
prefixes, no batching. Request/response pairing is 1:1 per connection — a client
opens a connection, sends one request line, reads one response line, closes (or
reuses the socket for another op; see client.Client).
"""

from __future__ import annotations

import json
import socket
from typing import Any

ENCODING = "utf-8"
RECV_CHUNK = 65536


def send_line(sock: socket.socket, obj: dict[str, Any]) -> None:
    payload = json.dumps(obj, separators=(",", ":")).encode(ENCODING) + b"\n"
    sock.sendall(payload)


class LineReader:
    """Buffers bytes off a socket and yields complete newline-terminated JSON objects."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = b""

    def read_obj(self) -> dict[str, Any] | None:
        """Block until one full line arrives; return None on clean EOF before any data."""
        while b"\n" not in self._buf:
            chunk = self._sock.recv(RECV_CHUNK)
            if not chunk:
                if self._buf:
                    raise ConnectionError("peer closed mid-message")
                return None
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return json.loads(line.decode(ENCODING))
