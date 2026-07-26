"""Named keys -> the bytes a terminal would actually send for them.

Covers control characters, common editing/navigation keys (assuming a VT100/xterm
application), and function keys. Names are case-insensitive; aliases are provided
for the common spellings agents are likely to reach for.

Escape sequences here assume DECCKM (cursor keys mode) is *not* set, which is the
default and what nearly everything expects outside of full-screen editors that
explicitly switch modes — those switches are handled by the pty/pyte side, not here.
"""

from __future__ import annotations

# Control characters: C-a .. C-z, plus a few named ones.
_CONTROL = {f"c-{chr(c)}": bytes([c - ord("a") + 1]) for c in range(ord("a"), ord("z") + 1)}

_NAMED: dict[str, bytes] = {
    "enter": b"\r",
    "return": b"\r",
    "tab": b"\t",
    "backspace": b"\x7f",
    "escape": b"\x1b",
    "esc": b"\x1b",
    "space": b" ",
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
    "pageup": b"\x1b[5~",
    "pagedown": b"\x1b[6~",
    "insert": b"\x1b[2~",
    "delete": b"\x1b[3~",
    "backtab": b"\x1b[Z",
    "c-space": b"\x00",
    "c-@": b"\x00",
    "c-\\": b"\x1c",
    "c-]": b"\x1d",
    "c-^": b"\x1e",
    "c-_": b"\x1f",
}
_NAMED.update({f"f{n}": seq for n, seq in {
    1: b"\x1bOP", 2: b"\x1bOQ", 3: b"\x1bOR", 4: b"\x1bOS",
    5: b"\x1b[15~", 6: b"\x1b[17~", 7: b"\x1b[18~", 8: b"\x1b[19~",
    9: b"\x1b[20~", 10: b"\x1b[21~", 11: b"\x1b[23~", 12: b"\x1b[24~",
}.items()})
_NAMED.update(_CONTROL)

# Common aliases.
_ALIASES = {
    "^c": "c-c",
    "^d": "c-d",
    "^z": "c-z",
    "del": "delete",
    "bs": "backspace",
}


class UnknownKey(ValueError):
    pass


def key_bytes(name: str) -> bytes:
    """Resolve a key name (case-insensitive) to the bytes to write to the pty."""
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    try:
        return _NAMED[key]
    except KeyError as exc:
        raise UnknownKey(f"unknown key name: {name!r}") from exc


def available_keys() -> list[str]:
    return sorted(_NAMED.keys())
