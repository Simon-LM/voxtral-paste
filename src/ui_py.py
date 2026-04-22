#!/usr/bin/env python3
"""Shared ANSI colors and UI helpers for Python scripts.

Equivalent spirit to src/ui.sh for shell scripts.
"""

from __future__ import annotations

import sys

# Colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
BLINK = "\033[5m"
REVERSE = "\033[7m"

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
WHITE = "\033[97m"
BLUE = "\033[34m"
BCYAN = "\033[1;36m"
BGREEN = "\033[1;32m"
BYELLOW = "\033[1;33m"
BBLUE = "\033[1;34m"
BG_CYAN = "\033[46m"
BG_BLUE = "\033[44m"
BG_PURPLE = "\033[45m"

_SEP = "".join(["-" for _ in range(66)])


def header(title: str, emoji: str = "") -> None:
    """Print a section header, similar to _header in src/ui.sh."""
    prefix = f"{emoji}  " if emoji else ""
    print("", file=sys.stderr)
    print(f"{DIM}{_SEP}{RESET}", file=sys.stderr)
    print(f"  {BGREEN}{prefix}{title}{RESET}", file=sys.stderr)
    print(f"{DIM}{_SEP}{RESET}", file=sys.stderr)


def sep() -> None:
    print(f"{DIM}{_SEP}{RESET}", file=sys.stderr)


def process(message: str) -> None:
    print(f"  {BGREEN}⚡{RESET} {message}", file=sys.stderr)


def success(message: str) -> None:
    print(f"  {BGREEN}✓{RESET} {message}", file=sys.stderr)


def warn(message: str) -> None:
    print(f"  {BYELLOW}⚠{RESET}  {message}", file=sys.stderr)


def error(message: str) -> None:
    print(f"  {RED}✗{RESET} {message}", file=sys.stderr)


def info(message: str) -> None:
    print(f"  {CYAN}{message}{RESET}", file=sys.stderr)


def crucial(message: str) -> None:
    print(f"  {BCYAN}{message}{RESET}", file=sys.stderr)


def stop(message: str) -> None:
    print(f"  {BBLUE}{message}{RESET}", file=sys.stderr)

def debug(message: str) -> None:
    """Affiche un message discret en gris (DIM)."""
    print(f"  {DIM}{message}{RESET}", file=sys.stderr)