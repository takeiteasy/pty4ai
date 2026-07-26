# CLI reference

Every command prints exactly one JSON object to stdout and exits non-zero
(with `{"error": "..."}` on stdout) on failure. The daemon autostarts on first
use — there's nothing to launch manually.

## `spawn`

```
pty4ai spawn [--cwd DIR] [--rows N] [--cols N] [--env KEY=VALUE ...] -- CMD [ARGS...]
```

Starts a new session. Returns a session summary (`session_id`, `pid`, `alive`,
`rows`, `cols`, `created_at`, `exit`). `--env` may be repeated.

```
$ pty4ai spawn --rows 40 --cols 100 -- python3 -i
{"session_id": "d95f4dfca776", "argv": ["python3", "-i"], "pid": 83851, ...}
```

## `send`

```
pty4ai send SESSION_ID TEXT [--no-enter]
```

Writes `TEXT` followed by `\r` (unless `--no-enter`). This is literal text —
for control/navigation keys use `keys`.

## `keys`

```
pty4ai keys SESSION_ID NAME [NAME ...]
```

Sends one or more named keys in sequence, e.g. `pty4ai keys $SID C-c Enter`.
See `docs/keys.md` or `pty4ai list-keys` for the full table.

## `read`

```
pty4ai read SESSION_ID [--since N] [--idle-ms N] [--timeout-ms N] [--expect REGEX]
```

Waits for output to settle (see `docs/architecture.md#read-semantics-idle-quiescence`)
and returns the raw bytes written since cursor `--since` (default `0`, i.e.
from the start). The response's `since` field is the next cursor to pass in;
`reason` is one of `idle` (new data, then settled — reads without `--expect`
only), `quiet` (no new data — reads without `--expect` only; returns once
`idle_ms` of silence has passed, not the full timeout), `expect` (pattern
matched), `timeout` (idle-based reads: still producing output past
`idle_ms`/`timeout_ms`; `--expect` reads: pattern never matched before
`timeout_ms`), or `eof`.

```
$ pty4ai read $SID --since 0
{"session_id": "...", "data": "...", "since": 42, "truncated": false, "reason": "idle", "alive": true, "exit": null}
```

## `screen`

```
pty4ai screen SESSION_ID
```

Returns the currently rendered terminal grid: `lines` (list of strings),
`cursor` (`x`, `y`, `hidden`), `alt_screen`, `title`, `rows`, `cols`. Use this
for full-screen/TUI programs where the raw byte stream is just escape codes.

## `wait`

```
pty4ai wait SESSION_ID [--timeout-ms N]
```

Blocks until the session exits or the timeout elapses. Returns `alive` and,
once exited, `exit` (`{"code": ...}` or `{"signal": ...}`, one always `null`).

## `resize`

```
pty4ai resize SESSION_ID ROWS COLS
```

Updates the pty window size (`TIOCSWINSZ`) and the daemon's screen model to
match. Programs that redraw on `SIGWINCH` (most curses apps) will re-layout.

## `list`

```
pty4ai list
```

Returns all known sessions (including recently-exited ones still tracked by
the daemon) as summaries.

## `kill`

```
pty4ai kill SESSION_ID [--signal NAME] [--grace-seconds N]
```

Without `--signal`: sends `SIGTERM` to the session's process group, waits
`--grace-seconds` (default `0.5`), then `SIGKILL` if it's still alive. With
`--signal` (e.g. `INT`, `KILL`): sends exactly that signal once, no grace
period.

## `shutdown`

```
pty4ai shutdown
```

Stops the daemon and every session it owns (sessions do not survive a daemon
restart — see `docs/architecture.md`).

## `ping`

```
pty4ai ping
```

Autostarts the daemon if needed and confirms it's responsive. Useful as a
readiness check.

## `list-keys`

```
pty4ai list-keys
```

Prints every recognized key name for `keys` — doesn't touch the daemon.
