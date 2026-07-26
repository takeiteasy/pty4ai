# Key names

For `pty4ai keys SESSION_ID NAME [NAME ...]` (and the library's `Client.keys`).
Names are case-insensitive. Run `pty4ai list-keys` for the exact live list —
this is the human-readable version of `pty4ai/keys.py`.

For literal text (including single printable characters like `q`), use `send`
instead — `keys` is only for control characters and named
navigation/function keys.

## Control characters

`C-a` through `C-z` send byte `0x01`–`0x1a`. A few extras: `C-space`/`C-@`
(`0x00`), `` C-\ `` (`0x1c`), `C-]` (`0x1d`), `C-^` (`0x1e`), `C-_` (`0x1f`).
Aliases `^c`, `^d`, `^z` map to the equivalent `C-x` form.

`C-c` sends the byte a terminal would send for Ctrl-C (`0x03`) — it does
**not** send `SIGINT` directly. Whether the program reacts depends on its
terminal mode and whether it traps the signal the line discipline generates.
For "guaranteed to stop", use `pty4ai kill --signal INT` (or plain `kill`,
which escalates to `SIGKILL`), which signals the process group directly. See
`docs/architecture.md` for the full explanation.

## Named keys

| name | bytes | | name | bytes |
|---|---|---|---|---|
| `enter` / `return` | `\r` | | `home` | `ESC [ H` |
| `tab` | `\t` | | `end` | `ESC [ F` |
| `backspace` / `bs` | `0x7f` | | `pageup` | `ESC [ 5 ~` |
| `escape` / `esc` | `0x1b` | | `pagedown` | `ESC [ 6 ~` |
| `space` | ` ` | | `insert` | `ESC [ 2 ~` |
| `up` | `ESC [ A` | | `delete` / `del` | `ESC [ 3 ~` |
| `down` | `ESC [ B` | | `backtab` | `ESC [ Z` |
| `left` | `ESC [ D` | | `f1`–`f12` | xterm function-key sequences |
| `right` | `ESC [ C` | | | |

Arrow-key sequences assume DECCKM (cursor keys mode) is *off*, the default —
correct for shells and most programs outside full-screen editors that
explicitly switch modes.

## Adding a key

Edit `pty4ai/keys.py`'s `_NAMED` (or `_ALIASES` for a shorthand) and add a
case in `tests/test_keys.py`.
