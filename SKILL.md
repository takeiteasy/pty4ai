---
name: pty4ai
description: Drive interactive command-line programs (prompts, confirmations, passwords, full-screen TUIs like vim/htop/fzf) over real pseudo-terminals via the pty4ai daemon + CLI. Use whenever you need to spawn and interact with a program that reads from a tty, rather than a plain subprocess — testing a REPL, answering interactive prompts, or driving a curses/full-screen app.
---

# pty4ai

A daemon and CLI that gives an agent a real pseudo-terminal to drive an
interactive program over — spawn it, send input across multiple turns, read
back raw bytes or a rendered screen grid. No tmux, no screen-scraping.

Install (from this repo):

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The `pty4ai` daemon autostarts on first use of the CLI or `Client` — nothing
to launch manually.

## The read-loop pattern

Every interaction follows: spawn, then repeatedly send input and read output,
tracking your read cursor (`since`).

```
spawn -> sid
since = 0
loop:
    read(sid, since=since)   # blocks until idle/quiet/expect/timeout
    since = response.since
    ...decide what to send based on response.data or a `screen` call...
    send / keys
kill(sid)  # or let it exit and `wait`
```

Always carry `since` forward from the previous `read`'s response — each
`read` is non-destructive, so re-reading from `0` replays old output.

## Shell usage

```sh
SID=$(pty4ai spawn -- python3 -i | jq -r .session_id)
pty4ai read "$SID"
pty4ai send "$SID" "2 + 2"
pty4ai read "$SID" --since "$(pty4ai read "$SID" | jq -r .since)"
pty4ai kill "$SID"
```

In practice, re-read using the `since` from the previous response rather than
round-tripping through `jq` twice.

## Python usage

```python
from pty4ai import Client

with Client() as c:
    s = c.spawn(["python3", "-i"])
    sid = s["session_id"]
    r = c.read(sid)
    c.send(sid, "2 + 2")
    r = c.read(sid, since=r["since"])
    assert "4" in r["data"]
    c.kill(sid)
```

## Line-oriented vs. full-screen programs

- **REPLs, shells, prompts**: use `read` and match on `data` (raw byte
  stream, echo included).
- **Full-screen/TUI programs** (curses apps, vim, htop, fzf): `read`'s raw
  bytes are escape codes. Use `screen` instead — it returns the currently
  rendered grid (`lines`, `cursor`) as pyte would draw it.
- Not sure which you're driving? Call `screen` — if `alt_screen` is `true`,
  treat it as full-screen.

## Sending input

- Literal text (including single characters like `q` or `y`):
  `send(sid, text, enter=True|False)`. `enter=True` (default) appends `\r`.
- Control/navigation/function keys: `keys(sid, ["C-c", "Enter", "Up"])`. Run
  `pty4ai list-keys` for the full table.
- Passwords/hidden prompts: `send` still works; the tty won't echo it back,
  so it won't appear in your next `read`.

## Stopping a session

`keys(sid, ["C-c"])` sends the byte a terminal Ctrl-C would send — a program
can trap or ignore it. `kill(sid)` sends `SIGTERM` to the whole process
group, escalating to `SIGKILL` after a grace period, and is the reliable way
to end a stuck session. Always `kill` (or let-exit-and-`wait`) sessions
you're done with.

## Timeouts

`read`'s `timeout_ms` (default 10s) only bounds output that's already
started — a program slow to produce its first byte settles as `quiet` after
`idle_ms` (default 300ms) regardless of `timeout_ms`. If you're waiting on a
specific slow-to-appear string, use `--expect REGEX` — it skips idle
quiescence and holds out for the pattern up to `timeout_ms`.

## Command reference

| command | purpose |
|---|---|
| `spawn -- CMD [ARGS...]` | start a session, returns `session_id` |
| `send SID TEXT [--no-enter]` | write literal text |
| `keys SID NAME [NAME ...]` | send named control/navigation keys |
| `read SID [--since N] [--idle-ms N] [--timeout-ms N] [--expect REGEX]` | wait for output to settle, return bytes since cursor |
| `screen SID` | rendered grid for full-screen programs |
| `resize SID ROWS COLS` | change pty window size |
| `wait SID [--timeout-ms N]` | block until session exits |
| `list` | all known sessions |
| `kill SID [--signal NAME] [--grace-seconds N]` | end a session |
| `shutdown` | stop the daemon and every session |
| `ping` | readiness check |
| `list-keys` | print all recognized key names |

Full detail on each command: `docs/cli.md`. Key names: `docs/keys.md`. How
it's built: `docs/architecture.md`.
