#!/usr/bin/env python3
"""Prompts for a line, echoes it back, loops until 'quit'. Basic round-trip fixture."""
import sys

while True:
    try:
        line = input("> ")
    except EOFError:
        break
    if line.strip() == "quit":
        print("bye")
        break
    print(f"you said: {line}")
    sys.stdout.flush()
