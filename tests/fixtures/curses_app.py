#!/usr/bin/env python3
"""Minimal full-screen curses app: draws a banner + a counter, quits on 'q'.
Proves the `screen` view renders alt-screen/cursor-addressed output usefully,
and that `resize` propagates (the banner re-centers)."""
import curses


def main(stdscr: "curses._CursesWindow") -> None:
    curses.curs_set(0)
    stdscr.nodelay(False)
    count = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        banner = "PTY4AI CURSES FIXTURE"
        stdscr.addstr(0, max(0, (w - len(banner)) // 2), banner)
        stdscr.addstr(2, 2, f"count={count}")
        stdscr.addstr(h - 1, 2, "press q to quit")
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break
        count += 1


if __name__ == "__main__":
    curses.wrapper(main)
