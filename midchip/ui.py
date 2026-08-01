"""
midchip.ui | fancy ANSI/icon shit
----------
a simple module to centralize colors, icons, and other stuff
that makes logging look super cool. and stuff.
"""
from __future__ import annotations

import os
import sys


def _supports_color(stream) -> bool:
    """best-effort check for if stream can render ANSI escapes."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR") is not None:
        return True
    if os.environ.get("MIDCHIP_GUI") is not None:
        return True
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if sys.platform == "win32":
        # windows terminal, conemu, and ansicon all announce themselves (yay!)
        # these terminals (most of the time) don't understand escape codes, so fallback to plain text
        return bool(os.environ.get("WT_SESSION") or os.environ.get("ANSICON"))
    return True


COLOR = _supports_color(sys.stderr)


class _C:
    RESET = "\033[0m" if COLOR else ""
    BOLD = "\033[1m" if COLOR else ""
    DIM = "\033[2m" if COLOR else ""
    RED = "\033[38;2;255;99;99m" if COLOR else ""
    GREEN = "\033[38;2;48;244;140m" if COLOR else ""
    YELLOW = "\033[38;2;255;196;77m" if COLOR else ""
    CYAN = "\033[38;2;110;220;255m" if COLOR else ""
    MAGENTA = "\033[38;2;255;152;238m" if COLOR else ""
    GRAY = "\033[38;2;150;150;150m" if COLOR else ""


def _line(msg: str, *, icon: str, color: str, fallback: str, bold: bool = False) -> str:
    if COLOR:
        weight = _C.BOLD if bold else ""
        return f"{color}{icon}{_C.RESET} {weight}{msg}{_C.RESET}"
    return f"{fallback} {msg}"


def step(msg: str) -> None:
    print(_line(msg, icon="▸", color=_C.MAGENTA, fallback="==>", bold=True), file=sys.stderr)


def info(msg: str) -> None:
    print(_line(msg, icon="ℹ", color=_C.CYAN, fallback="[i]"), file=sys.stderr)


def success(msg: str) -> None:
    print(_line(msg, icon="✓", color=_C.GREEN, fallback="[OK]", bold=True), file=sys.stderr)


def warn(msg: str) -> None:
    print(_line(msg, icon="⚠", color=_C.YELLOW, fallback="[WARN]"), file=sys.stderr)


def note(msg: str) -> None:
    print(_line(msg, icon="·", color=_C.GRAY, fallback="[note]"), file=sys.stderr)


def error(msg: str) -> str:
    return _line(msg, icon="✗", color=_C.RED, fallback="[ERROR]", bold=True)


def blank() -> None:
    print(file=sys.stderr)


def progress_bar(
    i: int, total: int, *, label: str = "Rendering", width: int = 40,
    show_count: bool = False,
) -> str:
    """cool progress bar using carriage returns (reminder: use `end=""` and `flush=True`!!!)"""
    if total <= 0:
        return ""
    pct = min(100, int(100 * i / total))
    filled = pct * width // 100
    count = f" {i}/{total}" if show_count else ""
    if COLOR:
        bar = f"{_C.GREEN}{'█' * filled}{_C.GRAY}{'░' * (width - filled)}{_C.RESET}"
        head = f"{_C.MAGENTA}▸{_C.RESET} {_C.BOLD}{label}{_C.RESET}"
    else:
        bar = "#" * filled + "-" * (width - filled)
        head = f"==> {label}"
    return f"\r{head} [{bar}] {pct:3d}%{count}"
