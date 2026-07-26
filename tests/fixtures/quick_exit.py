#!/usr/bin/env python3
"""Prints one line and exits immediately. Proves the daemon treats a pty read
racing the child's exit as a clean EOF (ptyprocess normalizes the macOS
EIO-after-exit quirk into EOFError; session.drain() must not crash on it)."""
print("bye")
