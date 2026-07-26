"""Integration tests: real daemon, real socket, real pty children. Each test
targets one failure mode called out in the plan."""

from __future__ import annotations

import signal
import time

from .conftest import python_argv


def test_echo_prompt_round_trip(client):
    s = client.spawn(python_argv("echo_prompt.py"))
    sid = s["session_id"]
    r = client.read(sid)
    assert "> " in r["data"]

    client.send(sid, "hello world")
    r = client.read(sid, since=r["since"])
    assert "you said: hello world" in r["data"]

    client.send(sid, "quit")
    w = client.wait(sid, timeout_ms=3000)
    assert w["alive"] is False
    assert w["exit"]["code"] == 0


def test_slow_output_quiescence_returns_full_burst_not_partial(client):
    """A naive single fixed-delay read would either cut a chunk in half or return
    early; idle-quiescence with a longer idle window than the writer's pause
    should return the complete run once it truly goes quiet."""
    s = client.spawn(python_argv("slow_output.py"))
    sid = s["session_id"]
    r = client.read(sid, idle_ms=800, timeout_ms=5000)
    assert "chunk 1" in r["data"]
    assert "chunk 2" in r["data"]
    assert "chunk 3" in r["data"]
    assert "done" in r["data"]
    client.wait(sid, timeout_ms=2000)


def test_curses_screen_view_renders_banner(client):
    s = client.spawn(python_argv("curses_app.py"), rows=10, cols=40)
    sid = s["session_id"]
    client.read(sid, idle_ms=300, timeout_ms=3000)
    view = client.screen(sid)
    lines = view["lines"]
    assert any("PTY4AI CURSES FIXTURE" in line for line in lines)
    assert any("count=0" in line for line in lines)

    client.send(sid, "q", enter=False)
    w = client.wait(sid, timeout_ms=3000)
    assert w["alive"] is False


def test_curses_screen_reports_alt_screen(client):
    """pyte stores DECSET private modes (like 1049, the alt-screen mode) shifted
    left 5 bits in screen.mode -- a plain `1049 in screen.mode` check silently
    always reads False. Regression test for that."""
    s = client.spawn(python_argv("curses_app.py"), rows=10, cols=40)
    sid = s["session_id"]
    client.read(sid, timeout_ms=2000)
    view = client.screen(sid)
    assert view["alt_screen"] is True
    client.send(sid, "q", enter=False)
    client.wait(sid, timeout_ms=2000)


def test_password_prompt_input_delivered_without_echo(client):
    s = client.spawn(python_argv("password.py"))
    sid = s["session_id"]
    r = client.read(sid)
    assert "password:" in r["data"]

    client.send(sid, "secret123")
    r2 = client.read(sid, since=r["since"], timeout_ms=3000)
    # the password itself must never appear in the output stream
    assert "secret123" not in r2["data"]
    assert "length=9" in r2["data"]


def test_control_c_byte_vs_real_signal(client):
    s = client.spawn(python_argv("stubborn.py"))
    sid = s["session_id"]
    r = client.read(sid, timeout_ms=3000)
    assert "ready" in r["data"]

    # keys C-c writes 0x03 into the pty; the process traps SIGINT and survives.
    client.keys(sid, ["C-c"])
    r2 = client.read(sid, since=r["since"], timeout_ms=3000)
    assert "caught signal, hits=1" in r2["data"]
    assert client.list()["sessions"][0]["alive"] is True

    # kill --signal KILL bypasses trapping entirely.
    client.kill(sid, signal="KILL")
    w = client.wait(sid, timeout_ms=3000)
    assert w["alive"] is False
    assert w["exit"]["signal"] == signal.SIGKILL


def test_quick_exit_does_not_crash_daemon(client):
    s = client.spawn(python_argv("quick_exit.py"))
    sid = s["session_id"]
    r = client.read(sid, timeout_ms=3000)
    assert "bye" in r["data"]
    w = client.wait(sid, timeout_ms=2000)
    assert w["exit"]["code"] == 0

    # daemon must still be responsive after a race-the-exit read
    assert client.ping()["ok"] is True


def test_read_with_no_new_output_returns_quiet_fast(client):
    """A read that finds nothing new since the caller's cursor must settle in
    roughly idle_ms, not wait out the full timeout -- that's the difference
    between 'has anything changed?' costing ~0.1s vs. 10s."""
    s = client.spawn(python_argv("echo_prompt.py"))
    sid = s["session_id"]
    r1 = client.read(sid, idle_ms=100, timeout_ms=5000)  # banner + prompt

    start = time.monotonic()
    r2 = client.read(sid, since=r1["since"], idle_ms=100, timeout_ms=5000)
    elapsed = time.monotonic() - start

    assert r2["reason"] == "quiet"
    assert r2["data"] == ""
    assert elapsed < 2.0, f"quiet read took {elapsed:.2f}s, expected well under the 5s timeout"

    client.send(sid, "quit")
    client.wait(sid, timeout_ms=2000)


def test_quiet_clock_starts_at_read_not_at_spawn(client):
    """Regression: the idle clock for a "quiet" (no new data) result must be
    measured from whichever is later, the session's last write or this read's
    own arrival -- not from spawn time. Otherwise a read arriving well after
    spawn on a program that's simply slow to produce its first output would
    return an instant, false "quiet" before the program has had a chance to
    speak."""
    s = client.spawn(python_argv("delayed_prompt.py"))
    sid = s["session_id"]
    time.sleep(0.5)  # read arrives mid-delay, > idle_ms after spawn already

    start = time.monotonic()
    r = client.read(sid, idle_ms=300, timeout_ms=5000, expect="ready")
    elapsed = time.monotonic() - start

    assert "ready" in r["data"]
    assert r["reason"] == "expect"
    assert elapsed >= 0.25, f"returned in {elapsed:.2f}s -- looks like the pre-fix instant false quiet"

    client.wait(sid, timeout_ms=2000)


def test_quiet_clock_starts_at_read_not_at_spawn_no_expect(client):
    """Same regression as above, but through the actual no-`expect` quiet path
    the fix touches (the `expect`-set variant above never reaches the idle
    branch at all, since idle quiescence is skipped whenever `expect` is set)."""
    s = client.spawn(python_argv("delayed_prompt.py"))
    sid = s["session_id"]
    time.sleep(0.5)  # already > idle_ms past spawn by the time we read

    start = time.monotonic()
    r = client.read(sid, idle_ms=300, timeout_ms=5000)
    elapsed = time.monotonic() - start

    assert r["reason"] == "quiet"
    assert r["data"] == ""
    assert elapsed >= 0.25, f"returned in {elapsed:.2f}s -- looks like the pre-fix instant false quiet"

    client.wait(sid, timeout_ms=2000)


def test_read_since_cursor_avoids_rereading(client):
    s = client.spawn(python_argv("echo_prompt.py"))
    sid = s["session_id"]
    r1 = client.read(sid)
    client.send(sid, "one")
    r2 = client.read(sid, since=r1["since"])
    assert "you said: one" in r2["data"]
    assert "> " not in r2["data"] or r2["data"].count("you said:") == 1
    client.send(sid, "quit")
    client.wait(sid, timeout_ms=2000)


def test_list_and_kill(client):
    s = client.spawn(python_argv("stubborn.py"))
    sid = s["session_id"]
    client.read(sid, timeout_ms=2000)
    assert any(x["session_id"] == sid for x in client.list()["sessions"])
    client.kill(sid)
    w = client.wait(sid, timeout_ms=2000)
    assert w["alive"] is False


def test_resize_updates_dimensions(client):
    s = client.spawn(python_argv("curses_app.py"), rows=10, cols=40)
    sid = s["session_id"]
    client.read(sid, timeout_ms=2000)
    r = client.resize(sid, rows=20, cols=60)
    assert r["rows"] == 20 and r["cols"] == 60
    view = client.screen(sid)
    assert view["rows"] == 20 and view["cols"] == 60
    client.send(sid, "q", enter=False)
    client.wait(sid, timeout_ms=2000)
