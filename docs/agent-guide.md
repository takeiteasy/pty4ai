# Agent guide

The pattern for testing an interactive program: spawn it, then repeatedly
send input and read output, tracking your read cursor. This is true whether
you're driving pty4ai from shell commands or from the Python `Client`.

## The read-loop pattern

```
spawn -> sid
since = 0
loop:
    read(sid, since=since)   # blocks until idle/quiet/expect/timeout; returns data + new since
    since = response.since
    ...decide what to send based on response.data or a `screen` call...
    send / keys
kill(sid)  # or let it exit and `wait`
```

Always carry `since` forward from the previous `read`'s response — don't
re-read from `0` each time, or you'll see the same output repeatedly (each
call is non-destructive by design, precisely so a retried call can't lose
data, but that means *you* own advancing the cursor).

## Shell example

```sh
SID=$(pty4ai spawn -- python3 -i | jq -r .session_id)
pty4ai read "$SID"                        # banner + first prompt
pty4ai send "$SID" "2 + 2"
SINCE=$(pty4ai read "$SID" --since 0 | jq -r .since)
pty4ai read "$SID" --since "$SINCE"       # nothing new yet -> returns quickly with reason "quiet"
pty4ai kill "$SID"
```

In practice you'll usually just re-read with the `since` from the previous
response rather than round-tripping through `jq` twice as above.

## Python example

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

- **REPLs, shells, prompts**: use `read` and match on `data`. It's the raw
  byte stream, echo included — a program that echoes your input back will
  show up in the next `read`.
- **Full-screen/TUI programs** (curses apps, vim, htop, fzf): `read`'s raw
  bytes are cursor-movement escape codes, not something to pattern-match on.
  Use `screen` instead — it gives you the currently rendered grid (`lines`,
  `cursor`) as pyte would draw it.
- Not sure which you're driving? Call `screen` — if `alt_screen` is `true`,
  treat it as full-screen.

## Sending input

- Literal text (including single characters like `q` or `y`): `send(sid,
  text, enter=True|False)`. `enter=True` (the default) appends `\r`.
- Control/navigation/function keys: `keys(sid, ["C-c", "Enter", "Up"])` — see
  `docs/keys.md`.
- Passwords/hidden prompts: `send` still works; the tty simply won't echo it
  back, so it won't appear in your next `read`.

## Stopping a session that won't listen

`keys(sid, ["C-c"])` sends the *byte* Ctrl-C, which the line discipline turns
into a real SIGINT for well-behaved programs — but a program can trap it (see
`tests/fixtures/stubborn.py`) and keep running.
`kill(sid)` sends `SIGTERM` to the whole process group, escalating to
`SIGKILL` after a grace period, and is the reliable way to end a stuck
session. Always `kill` (or let-exit-and-`wait`) sessions you're done with —
the daemon's lifetime isn't yours to manage, but sessions are.

## Timeouts and geometry

- `read`'s default `timeout_ms` is 10s, but for a no-`--expect` read it only
  bounds output that's *already started*: a program slow to produce its
  first byte settles as `quiet` after `idle_ms` regardless of `timeout_ms`
  (idle quiescence, not the timeout, is what fires). Raising `timeout_ms`
  does nothing for that case. If you're waiting on a specific slow-to-appear
  string, use `--expect` — it skips idle quiescence entirely and holds out
  for the pattern up to `timeout_ms`. Otherwise, just re-read.
- `spawn` defaults to 24x80; pass `rows`/`cols` (or call `resize` later) if
  the program's layout depends on a specific size.
