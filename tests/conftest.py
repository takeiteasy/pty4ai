"""Test-wide fixtures: an isolated daemon (own XDG_RUNTIME_DIR, own event-loop
thread) so tests never touch a daemon a human might have running, plus an
orphan-process guard that fails the run if any fixture child outlives its test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def python_argv(fixture_name: str, *extra: str) -> list[str]:
    return [sys.executable, str(FIXTURES_DIR / fixture_name), *extra]


@pytest.fixture()
def isolated_state(monkeypatch):
    """Point pty4ai at a throwaway state dir for the duration of one test.

    Deliberately NOT pytest's `tmp_path`: it nests under a per-test directory
    name and easily exceeds AF_UNIX's ~104-byte sun_path limit on macOS, which
    makes bind()/connect() fail and manifests as a confusing autostart
    timeout. tempfile.mkdtemp() at the top of /tmp stays short.
    """
    d = tempfile.mkdtemp(prefix="pty4ai-test-")
    monkeypatch.setenv("XDG_RUNTIME_DIR", d)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def client(isolated_state):
    from pty4ai.client import Client

    c = Client()
    c.ping()  # forces autostart against the isolated socket path
    yield c
    try:
        c.shutdown()
    except Exception:
        pass
    # Give the daemon a moment to reap children and remove its socket/pid files.
    time.sleep(0.2)


@pytest.fixture(autouse=True)
def no_orphan_processes():
    before = _descendant_pids()
    yield
    # Daemon teardown (in the `client` fixture) already had time to run; this is
    # a last-resort check that nothing fixture-related was left behind.
    time.sleep(0.1)
    leaked = _descendant_pids() - before
    for pid in leaked:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    assert not leaked, f"orphaned processes left running: {leaked}"


def _descendant_pids() -> set[int]:
    try:
        out = subprocess.run(
            ["pgrep", "-P", str(os.getpid())], capture_output=True, text=True
        ).stdout
        direct = {int(p) for p in out.split()}
    except FileNotFoundError:
        return set()
    all_pids = set(direct)
    frontier = list(direct)
    while frontier:
        pid = frontier.pop()
        out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
        for p in out.split():
            ip = int(p)
            if ip not in all_pids:
                all_pids.add(ip)
                frontier.append(ip)
    return all_pids
