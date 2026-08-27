"""
midchip.resources | locate bundled non-code assets (icons, etc.)
----------
Both the Tk GUI and the pygame visualizer need to load the app icon at
runtime. Running from source, that's just a path relative to this file.
Running as a PyInstaller build, --add-data copies land under
sys._MEIPASS instead -- see scripts/midchip.spec.
"""
from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> Path | None:
    """Return the path to a bundled asset (e.g. "midchip.png"), or None
    if it isn't present. Never raises -- callers should treat a missing
    icon as cosmetic, not fatal."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", ""))
    else:
        # source checkout: midchip/resources.py -> project root
        base = Path(__file__).resolve().parent.parent

    candidates = [
        base / "assets" / name,
        base / name,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None