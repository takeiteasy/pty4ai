#!/usr/bin/env python3
"""Traps SIGINT/SIGTERM and keeps running, printing each attempt. Pairs with
test_control_c_byte_vs_real_signal: `keys C-c` writes byte 0x03, which the
line discipline turns into a SIGINT this process catches and survives (proving
the byte reaches the program and is treated as a real signal, not swallowed);
`kill --signal KILL` is not catchable, so it's the only one of the two
guaranteed to actually end a stubborn process."""
import signal
import sys
import time

hits = 0


def handle(signum, frame):
    global hits
    hits += 1
    print(f"caught signal, hits={hits}", flush=True)


signal.signal(signal.SIGINT, handle)
signal.signal(signal.SIGTERM, handle)

print("ready", flush=True)
while True:
    time.sleep(0.1)
