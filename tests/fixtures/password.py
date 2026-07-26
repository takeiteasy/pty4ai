#!/usr/bin/env python3
"""getpass-style prompt with echo disabled. Proves `send` still delivers input
even though the tty won't echo it back in `read` output."""
from getpass import getpass

pw = getpass("password: ")
print(f"\nlength={len(pw)}")
