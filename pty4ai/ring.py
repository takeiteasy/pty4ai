"""A bounded byte ring with a monotonic sequence number.

`seq` is the total number of bytes ever appended (a byte offset, not a slot index),
so `read_since(seq)` is a stable cursor an agent can keep across calls: it always
means "everything written after byte N", regardless of how much has since been
trimmed from the front of the ring.
"""

from __future__ import annotations


class RingBuffer:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._buf = bytearray()
        self._base = 0  # seq of self._buf[0]

    @property
    def seq(self) -> int:
        """Total bytes written so far == seq of the next byte to be appended."""
        return self._base + len(self._buf)

    def append(self, data: bytes) -> None:
        if not data:
            return
        self._buf.extend(data)
        overflow = len(self._buf) - self.capacity
        if overflow > 0:
            del self._buf[:overflow]
            self._base += overflow

    def read_since(self, since: int) -> tuple[bytes, int, bool]:
        """Return (data, new_since, truncated).

        `truncated` is True when `since` points before what the ring still holds,
        meaning some bytes between `since` and the returned data were dropped.
        """
        since = max(since, 0)
        truncated = since < self._base
        start = max(since, self._base)
        data = bytes(self._buf[start - self._base :])
        return data, self.seq, truncated
