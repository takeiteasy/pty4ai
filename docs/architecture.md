# Architecture

## Why not tmux

tmux is built for humans: its output is meant to be read on a terminal, its
session model is meant to be attached to interactively, and getting structured
state out of it means parsing `tmux capture-pane` text. pty4ai is built the
other way around — a daemon that owns real pseudo-terminals directly, with a
JSON-in/JSON-out interface designed for a program (an agent) to drive.

## Components

```
agent ──shell──> pty4ai CLI ──unix socket (ndjson)──> daemon
                                                        └─ Session (per pty)
                                                             ├─ master fd  (selectors loop)
                                                             ├─ RingBuffer (raw bytes + seq)
                                                             └─ pyte.HistoryScreen + Stream
```

- **`pty4ai/daemon.py`** — a single-threaded `selectors` event loop. It multiplexes
  the listening socket, every open client connection, and every session's pty
  master fd. Single-threaded means no locking anywhere in the session/ring/screen
  code. Trade-off: `Session.write` (backing `send`/`keys`) writes to the pty
  master fd with a blocking call — fine for agent-sized input, but a very
  large `send` to a child that isn't reading its stdin could stall the whole
  daemon, including other sessions, until the write completes.
- **`pty4ai/session.py`** — owns one child process via `ptyprocess.PtyProcess`. Each
  session has its own process group (`setsid`), so `kill`/`keys C-c` can target the
  whole group, not just the immediate child.
- **`pty4ai/ring.py`** — a bounded byte ring with a monotonically increasing
  sequence number (total bytes ever written). `read(since=N)` is a stable cursor:
  it means "everything after byte N" regardless of how much has since been
  trimmed from the ring's front.
- **`pty4ai/keys.py`** — maps key names (`Enter`, `C-c`, `Up`, `F5`, ...) to the
  bytes a real terminal would send for them.
- **`pty4ai/protocol.py`** — newline-delimited JSON framing shared by client and
  daemon.
- **`pty4ai/client.py`** — the library surface (`Client`). Opens one socket
  connection per request/response pair; autostarts the daemon (`python -m
  pty4ai.daemon`, detached via `start_new_session=True`) if nothing answers at the
  resolved socket path.
- **`pty4ai/cli.py`** — argparse wrapper around `Client`, printing one JSON object
  per invocation.

## Read semantics: idle quiescence

`read` doesn't return the instant it's called — full-screen and slow-writing
programs don't finish producing output atomically. The daemon waits, per request:

1. `expect` (a regex) matched output written since the caller's cursor
   (`since`), **or**
2. no new data has arrived for `idle_ms` (default 300ms) — **only when
   `expect` is not set**. An explicit `expect` means wait for that pattern or
   time out, full stop; it never settles early just because things have gone
   quiet, matching or not, **or**
3. `timeout_ms` (default 10s) elapsed overall.

The response's `reason` field tells you which of these ended the wait:
`expect`, `idle` (no `expect`, settled *with* new data since your cursor),
`quiet` (no `expect`, settled with *no* new data — the common "did anything
change?" case, answered fast rather than waiting out the full timeout),
`timeout` (still producing output past `idle_ms`, or an `expect` that never
matched), or `eof` (the session exited).

The daemon drains every session's pty fd on every loop iteration regardless of
whether a `read` is pending on it, so a slow reader on one session never causes
another session's output to back up.

## Screen rendering

Every session is fed through a `pyte.HistoryScreen`, independent of whether the
program is line-oriented or full-screen. `screen` returns the current rendered
grid (`lines`, `cursor`, `alt_screen`, `title`) — this is what makes curses/vim/
htop-style programs testable instead of just a wall of escape codes. `read`
still gives you the raw byte stream when that's what you actually want (e.g. to
assert byte-for-byte on a REPL's output).

## Process lifecycle

- The daemon is the parent of every session's process group. Sessions do not
  survive a daemon restart in v1 (see `TICKETS.md`). On `shutdown` or a
  caught signal (SIGTERM/SIGINT), the daemon explicitly kills every session.
  On an *uncaught* death (SIGKILL, crash), it doesn't get the chance — but
  closing the pty master fd still makes the kernel deliver SIGHUP to the
  session's foreground process group (standard pty hangup behavior), which
  kills any child that hasn't specifically ignored SIGHUP. A child that
  does ignore it (or backgrounds itself) survives as an orphan. Verified:
  spawn `python3` with `signal.signal(SIGHUP, SIG_IGN)`, `kill -9` the
  daemon — the child is reparented to init and keeps running.
- `keys C-c` writes byte `0x03` into the pty; the line discipline turns that
  into `SIGINT` for the foreground process *if the terminal is in canonical/
  cooked mode with signal generation on* — a program can still trap or ignore
  it. `kill --signal INT` (or the default `kill`, which tries `SIGTERM` then
  `SIGKILL` after a grace period) sends a real signal straight to the whole
  process group. Use the byte for "what a user pressing Ctrl-C would send";
  use `kill` for "make this stop, guaranteed".
- On macOS, reading a pty master after its child has exited raises
  `OSError(EIO)` rather than returning EOF. `ptyprocess` normalizes this into
  `EOFError`, which `Session.drain()` treats as a clean exit — this is the
  detail most naive pty wrappers get wrong and crash on.

## Determinism

Every session gets a pinned environment (`TERM=xterm-256color`,
`LANG=C.UTF-8`, `COLUMNS`/`LINES` matching the requested geometry) merged with
the caller's overrides, so the same command produces the same TUI layout
regardless of the daemon's own environment.
