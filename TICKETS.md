# Tickets

No `.hut.scfg` in this repo, so tracked here per project convention.

## Open

- **MCP server wrapper.** v1 ships a JSON CLI + Python library only. A thin
  MCP server over `pty4ai.client.Client` would let MCP-capable agents call
  `spawn`/`send`/`read`/`screen` as native tools instead of shelling out.
  Deferred out of v1 scope by design (see plan).

- **Session persistence across daemon restart.** Currently the daemon owns
  every session's process group directly; daemon death kills all sessions.
  Re-attaching sessions across a daemon restart (tmux-like) needs fd passing
  or a per-session helper process — meaningfully more machinery than v1's
  single-process model. Deferred out of v1 scope by design (see plan).

- **Session recording/replay.** No way to save a session's byte stream +
  timing for later replay/diffing. Would be useful for regression-testing a
  TUI's output across changes. Not designed yet.

- **Windows support.** `ptyprocess` and the pty model here are POSIX-only.
  Out of scope for v1; would need ConPTY.

- **`Daemon.sessions` never evicts.** Exited sessions stay in memory forever
  (each holding a capped-but-nonzero ring buffer plus a pyte screen with 2000
  lines of scrollback), so `list` shows full history but a long-running
  daemon's memory grows unbounded with session count. Needs a cap or TTL on
  dead sessions.

- **A daemon reaper for orphaned children.** A session leader that ignores or
  blocks SIGHUP survives a daemon `SIGKILL`/crash as an orphan holding its
  pty open (verified: `signal.signal(SIGHUP, SIG_IGN)` in a spawned child,
  then `kill -9` the daemon — child is reparented to init and keeps running).
  The daemon has no mechanism today to notice or clean these up on next
  startup.

## Notes

- `pty4ai/paths.py::socket_path()` raises if the resolved path exceeds ~100
  bytes (AF_UNIX's `sun_path` limit). This is a real constraint, not a bug —
  if you hit it, set `XDG_RUNTIME_DIR` to something shorter.
