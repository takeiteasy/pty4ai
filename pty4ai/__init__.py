"""pty4ai: a daemon + CLI/library for driving interactive CLI programs over real ptys.

Public library surface:

    from pty4ai import Client

    with Client() as c:
        sid = c.spawn(["python3", "-i"])["session_id"]
        c.send(sid, "2+2")
        print(c.read(sid)["data"])
        c.kill(sid)
"""

from .client import Client
from .errors import Pty4aiError, SessionNotFound

__all__ = ["Client", "Pty4aiError", "SessionNotFound"]

__version__ = "0.1.0"
