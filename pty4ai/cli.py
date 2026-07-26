"""JSON-emitting CLI over the daemon. Every subcommand prints one JSON object to
stdout and exits non-zero on error (with `{"error": ...}` on stdout).

    pty4ai spawn -- python3 -i
    pty4ai send <id> "2+2"
    pty4ai read <id>
    pty4ai screen <id>
    pty4ai keys <id> C-c Enter
    pty4ai kill <id>
"""

from __future__ import annotations

import argparse
import json
import sys

from .client import Client
from .errors import Pty4aiError
from .keys import available_keys


def _print(obj: dict) -> None:
    print(json.dumps(obj, indent=None, default=str))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pty4ai", description="Test interactive CLI programs over real ptys.")
    sub = p.add_subparsers(dest="cmd", required=True)

    spawn = sub.add_parser("spawn", help="start a new session")
    spawn.add_argument("argv", nargs=argparse.REMAINDER, help="command and args, e.g. -- python3 -i")
    spawn.add_argument("--cwd", default=None)
    spawn.add_argument("--rows", type=int, default=24)
    spawn.add_argument("--cols", type=int, default=80)
    spawn.add_argument("--env", action="append", default=[], help="KEY=VALUE, repeatable")

    send = sub.add_parser("send", help="write text (+ Enter by default)")
    send.add_argument("session_id")
    send.add_argument("text")
    send.add_argument("--no-enter", action="store_true")

    keys = sub.add_parser("keys", help="send named keys, e.g. C-c Enter Up")
    keys.add_argument("session_id")
    keys.add_argument("names", nargs="+")

    read = sub.add_parser("read", help="read output since a cursor, waiting for idle/expect/timeout")
    read.add_argument("session_id")
    read.add_argument("--since", type=int, default=0)
    read.add_argument("--idle-ms", type=int, default=300)
    read.add_argument("--timeout-ms", type=int, default=10_000)
    read.add_argument("--expect", default=None, help="regex; return as soon as it matches new output")

    screen = sub.add_parser("screen", help="rendered screen grid (for full-screen/TUI programs)")
    screen.add_argument("session_id")

    wait = sub.add_parser("wait", help="block until the session exits or timeout")
    wait.add_argument("session_id")
    wait.add_argument("--timeout-ms", type=int, default=10_000)

    resize = sub.add_parser("resize", help="change terminal size")
    resize.add_argument("session_id")
    resize.add_argument("rows", type=int)
    resize.add_argument("cols", type=int)

    sub.add_parser("list", help="list sessions")

    kill = sub.add_parser("kill", help="terminate a session's process group")
    kill.add_argument("session_id")
    kill.add_argument("--signal", default=None, help="e.g. INT, KILL; default TERM then KILL after grace")
    kill.add_argument("--grace-seconds", type=float, default=0.5)

    sub.add_parser("shutdown", help="stop the daemon and all sessions")
    sub.add_parser("ping", help="check the daemon is up (autostarts it)")
    sub.add_parser("list-keys", help="list recognized key names for `keys`")

    return p


def _parse_env(pairs: list[str]) -> dict[str, str]:
    out = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        out[key] = value
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "list-keys":
        _print({"keys": available_keys()})
        return 0

    client = Client()
    try:
        if args.cmd == "spawn":
            command = args.argv
            if command and command[0] == "--":
                command = command[1:]
            if not command:
                _print({"error": "spawn requires a command, e.g. `pty4ai spawn -- python3 -i`"})
                return 2
            result = client.spawn(command, rows=args.rows, cols=args.cols, cwd=args.cwd, env=_parse_env(args.env))
        elif args.cmd == "send":
            result = client.send(args.session_id, args.text, enter=not args.no_enter)
        elif args.cmd == "keys":
            result = client.keys(args.session_id, args.names)
        elif args.cmd == "read":
            result = client.read(
                args.session_id,
                since=args.since,
                idle_ms=args.idle_ms,
                timeout_ms=args.timeout_ms,
                expect=args.expect,
            )
        elif args.cmd == "screen":
            result = client.screen(args.session_id)
        elif args.cmd == "wait":
            result = client.wait(args.session_id, timeout_ms=args.timeout_ms)
        elif args.cmd == "resize":
            result = client.resize(args.session_id, args.rows, args.cols)
        elif args.cmd == "list":
            result = client.list()
        elif args.cmd == "kill":
            result = client.kill(args.session_id, signal=args.signal, grace_seconds=args.grace_seconds)
        elif args.cmd == "shutdown":
            result = client.shutdown()
        elif args.cmd == "ping":
            result = client.ping()
        else:  # pragma: no cover - argparse enforces choices
            _print({"error": f"unknown command {args.cmd!r}"})
            return 2
    except Pty4aiError as exc:
        _print({"error": str(exc)})
        return 1

    _print(result)
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
