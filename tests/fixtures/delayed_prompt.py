#!/usr/bin/env python3
"""Sleeps ~1s before printing anything. Proves a `read` arriving after spawn but
before the program has produced output waits idle_ms from when the read call
itself arrived -- not from spawn time -- so it doesn't falsely report "quiet"
before the program has had a chance to speak."""
import sys
import time

time.sleep(1.0)
print("ready", flush=True)
