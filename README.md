# pty4ai

A daemon and CLI that lets an agent test interactive command-line programs —
prompts, confirmations, passwords, full-screen TUIs — over real
pseudo-terminals. No tmux, no screen-scraping human-oriented output: spawn a
program, send input across multiple turns, and read back either the raw byte
stream or a rendered screen grid.

```sh
pty4ai spawn -- python3 -i
pty4ai send <session_id> "2 + 2"
pty4ai read <session_id>
```

The daemon autostarts on first use. See `docs/agent-guide.md` for the
read-loop pattern, `docs/cli.md` for the full command reference, and
`docs/architecture.md` for how it's built.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Test

```sh
.venv/bin/pytest -q
```

## Docs

- [`docs/agent-guide.md`](docs/agent-guide.md) — how to drive it as an agent
- [`docs/cli.md`](docs/cli.md) — command reference
- [`docs/keys.md`](docs/keys.md) — named key table
- [`docs/architecture.md`](docs/architecture.md) — how it's built, and why

## Status

v1: line-oriented and full-screen (TUI) programs both supported, single
daemon owns all sessions (no restart persistence), JSON CLI + Python library.
See `TICKETS.md` for known gaps.

## License

```

The MIT License (MIT)

Copyright (c) 2026 George Watson

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
