"""Exceptions shared by the client library and CLI."""


class Pty4aiError(Exception):
    """Base class for all pty4ai errors raised to callers."""


class SessionNotFound(Pty4aiError):
    """Raised when an operation references a session id the daemon doesn't know."""


class DaemonError(Pty4aiError):
    """Raised when the daemon reports a generic failure for a request."""


class ProtocolError(Pty4aiError):
    """Raised on malformed requests/responses at the ndjson framing layer."""
