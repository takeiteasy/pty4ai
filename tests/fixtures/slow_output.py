#!/usr/bin/env python3
"""Writes a few lines with pauses between them. Proves quiescence-based `read`
beats a naive fixed sleep: a client using idle detection sees each burst
separately instead of racing the writer or over-waiting."""
import sys
import time

for i in range(1, 4):
    print(f"chunk {i}")
    sys.stdout.flush()
    time.sleep(0.5)
print("done")
