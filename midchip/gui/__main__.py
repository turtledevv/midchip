from __future__ import annotations

import json
import os
import queue
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

from midchip.resources import asset_path

from midchip.cli_common import (
    ALL_WAVES, CHIP_PROFILES, MASTER_VOLUME,
    REVERB_MIX, REVERB_DECAY, VIBRATO_RATE_HZ, VIBRATO_DEPTH_SEMITONES,
)
from midchip import FPS

# Mirrors midchip.viz.app's own defaults; not imported directly so this
# launcher doesn't pick up a pygame dependency just to read two numbers.
VIZ_DEFAULT_WIDTH = 1280
VIZ_DEFAULT_HEIGHT = 720

ANSI_PATTERN = re.compile(r"\x1b\[([0-9;]*)m")

NO_CHIP = "<none, default>"
MAX_RECENT_FILES = 8

def _cli_command(module: str) -> list[str]:
    """Build the argv prefix for launching a midchip CLI entry point.

    - Running from source: `sys.executable -m <module>`, same as always.
    - Running as a frozen --onefile PyInstaller binary: shell out to a
      sibling binary (`midchip` / `midchip-viz`) placed flat next to this
      one, e.g.:

          dist/
          ├── midchip[.exe]
          ├── midchip-viz[.exe]
          └── midchip-gui[.exe]      <- we are this one

      In a frozen app, sys.executable reliably points at the actual
      launched binary (PyInstaller's own bootloader/executable), unlike
      sys.argv[0], which can be a relative path or a symlink name.
    """
    if getattr(sys, "frozen", False):
        bin_dir = Path(sys.executable).resolve().parent

        # "midchip" -> "midchip", "midchip.viz" -> "midchip-viz"
        binary_name = module.replace(".", "-")
        if sys.platform == "win32":
            binary_name += ".exe"

        binary_path = bin_dir / binary_name
        if not binary_path.exists():
            raise FileNotFoundError(
                f"Expected sibling binary not found: {binary_path}\n"
                f"'{binary_name}' must be built and placed next to "
                f"'{Path(sys.executable).name}'."
            )
        return [str(binary_path)]

    return [sys.executable, "-m", module]


def _default_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / "midchip"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "midchip"
    # Linux and other Unix-likes: follow the XDG base directory spec.
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "midchip"


CONFIG_PATH = _default_config_dir() / "gui_settings.json"

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

BG = "#1e1e2e"          # window background
BG_RAISED = "#242438"   # header / status strip
SURFACE = "#282839"     # panels, entries, list boxes
SURFACE_HI = "#45475a"  # hovered/active surface
BORDER = "#3a3a4d"
FG = "#cdd6f4"           # primary text
FG_MUTED = "#a6adc8"     # secondary text
FG_DIM = "#6c7086"        # tertiary / disabled text
ACCENT = "#89b4fa"       # links/selection/accent
ACCENT_ACTIVE = "#74c7ec"
DANGER = "#f38ba8"
DANGER_ACTIVE = "#eb6f92"
SUCCESS = "#a6e3a1"
WARNING = "#f9e2af"

# Standard 16-color ANSI palette (tuned to sit well on the dark background).
ANSI_COLORS = {
    "30": "#1e1e2e", "31": "#f38ba8", "32": "#a6e3a1", "33": "#f9e2af",
    "34": "#89b4fa", "35": "#f5c2e7", "36": "#94e2d5", "37": "#cdd6f4",
    "90": "#6c7086", "91": "#f38ba8", "92": "#a6e3a1", "93": "#f9e2af",
    "94": "#89b4fa", "95": "#f5c2e7", "96": "#94e2d5", "97": "#ffffff",
}


def ansi_256_to_hex(n: int) -> str:
    """Approximate conversion of an xterm 256-color index to hex."""
    if n < 16:
        base = list(ANSI_COLORS.values())
        return base[n % len(base)]
    if n < 232:
        n -= 16
        r, g, b = (n // 36) % 6, (n // 6) % 6, n % 6
        scale = lambda v: 0 if v == 0 else 55 + v * 40
        return f"#{scale(r):02x}{scale(g):02x}{scale(b):02x}"
    gray = 8 + (n - 232) * 10
    return f"#{gray:02x}{gray:02x}{gray:02x}"


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _pick_font(root: tk.Tk, candidates: list[str], fallback: str) -> str:
    """Return the first font family from `candidates` that's actually
    installed, falling back to a Tk-generic family that always exists."""
    available = {f.lower() for f in font.families(root)}
    for name in candidates:
        if name.lower() in available:
            return name
    return fallback


def pick_mono_font(root: tk.Tk) -> str:
    return _pick_font(
        root,
        [
            "DejaVu Sans Mono",   # common on Linux
            "Consolas",           # Windows
            "Menlo",               # macOS
            "SF Mono",             # macOS
            "Cascadia Mono",      # modern Windows Terminal default
            "Courier New",        # near-universal fallback
        ],
        fallback="TkFixedFont",
    )


def pick_ui_font(root: tk.Tk) -> str:
    return _pick_font(
        root,
        [
            "Segoe UI",   # Windows
            "SF Pro Text",  # macOS (rarely exposed to Tk, but try)
            "Helvetica Neue",  # macOS
            "DejaVu Sans",  # Linux
            "Helvetica",
            "Arial",
        ],
        fallback="TkDefaultFont",
    )


def apply_dark_theme(root: tk.Tk, base_font: font.Font) -> ttk.Style:
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(bg=BG)
    style.configure(".", background=BG, foreground=FG, font=base_font)
    bold_base = (base_font.actual("family"), base_font.actual("size"), "bold")

    style.configure("TFrame", background=BG)
    style.configure("Raised.TFrame", background=BG_RAISED)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Raised.TLabel", background=BG_RAISED, foreground=FG)
    style.configure("Muted.TLabel", background=BG, foreground=FG_MUTED)
    style.configure("Muted.Raised.TLabel", background=BG_RAISED, foreground=FG_MUTED)
    style.configure("Heading.TLabel", background=BG_RAISED, foreground=FG, font=bold_base)

    style.configure(
        "TLabelframe", background=BG, foreground=FG_MUTED, bordercolor=BORDER
    )
    style.configure(
        "TLabelframe.Label", background=BG, foreground=ACCENT, font=bold_base
    )

    style.configure(
        "TButton",
        background=SURFACE,
        foreground=FG,
        bordercolor=BORDER,
        focusthickness=0,
        padding=(10, 6),
    )
    style.map(
        "TButton",
        background=[("active", SURFACE_HI), ("disabled", SURFACE)],
        foreground=[("disabled", FG_DIM)],
    )

    style.configure(
        "Toolbar.TButton",
        background=BG_RAISED,
        foreground=FG_MUTED,
        bordercolor=BORDER,
        padding=(8, 4),
    )
    style.map(
        "Toolbar.TButton",
        background=[("active", SURFACE_HI)],
        foreground=[("active", FG)],
    )

    style.configure(
        "Accent.TButton", background=ACCENT, foreground="#1e1e2e", padding=(10, 6)
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_ACTIVE), ("disabled", SURFACE)],
        foreground=[("disabled", FG_DIM)],
    )

    style.configure(
        "Danger.TButton", background=DANGER, foreground="#1e1e2e", padding=(10, 6)
    )
    style.map(
        "Danger.TButton",
        background=[("active", DANGER_ACTIVE), ("disabled", SURFACE)],
        foreground=[("disabled", FG_DIM)],
    )

    style.configure(
        "TEntry",
        fieldbackground=SURFACE,
        foreground=FG,
        insertcolor=FG,
        bordercolor=BORDER,
        padding=6,
    )
    style.map("TEntry", fieldbackground=[("disabled", BG)])

    style.configure(
        "TCombobox",
        fieldbackground=SURFACE,
        background=SURFACE,
        foreground=FG,
        arrowcolor=FG_MUTED,
        bordercolor=BORDER,
        padding=6,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", SURFACE)],
        foreground=[("readonly", FG)],
    )
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#1e1e2e")
    root.option_add("*TCombobox*Listbox.font", base_font)

    style.configure(
        "TSpinbox",
        fieldbackground=SURFACE,
        foreground=FG,
        arrowcolor=FG_MUTED,
        bordercolor=BORDER,
        padding=6,
    )

    style.configure(
        "TCheckbutton", background=BG, foreground=FG, focuscolor=BG, padding=4
    )
    style.map(
        "TCheckbutton",
        background=[("active", BG)],
        indicatorcolor=[("selected", ACCENT), ("!selected", SURFACE)],
    )

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background=SURFACE,
        foreground=FG_MUTED,
        padding=(18, 9),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG)],
        foreground=[("selected", FG)],
    )

    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", background=BG, sashthickness=6)

    style.configure(
        "Vertical.TScrollbar",
        background=SURFACE,
        troughcolor=BG,
        bordercolor=BG,
        arrowcolor=FG_MUTED,
    )
    style.map("Vertical.TScrollbar", background=[("active", SURFACE_HI)])

    style.configure("TSeparator", background=BORDER)

    return style


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

class Settings:
    """Small JSON-backed store for GUI preferences (last file, options, etc.).
    Failure to read/write is non-fatal -- the app just falls back to defaults."""

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.data: dict = {}
        self.load()

    def load(self):
        try:
            self.data = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.data = {}

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2))
        except OSError:
            pass  # Non-critical: settings just won't persist this run.

    def for_tab(self, module: str) -> dict:
        return self.data.setdefault(module, {})


class StatusDot(tk.Canvas):
    """A tiny colored circle used as a per-tab running-state indicator."""

    def __init__(self, parent, size=10):
        super().__init__(
            parent, width=size, height=size, bg=BG, highlightthickness=0
        )
        self.size = size
        self._id = self.create_oval(1, 1, size - 1, size - 1, fill=FG_DIM, outline="")

    def set_color(self, color: str):
        self.itemconfig(self._id, fill=color)


class Terminal(tk.Frame):
    """A read-only text widget that understands a useful subset of ANSI SGR codes."""

    DEFAULT_FG = FG
    DEFAULT_BG = BG

    def __init__(self, parent):
        super().__init__(parent, bg=BG)

        mono = pick_mono_font(parent)
        self.base_font = font.Font(family=mono, size=10)
        self.bold_font = font.Font(family=mono, size=10, weight="bold")
        self.italic_font = font.Font(family=mono, size=10, slant="italic")
        self.bold_italic_font = font.Font(
            family=mono, size=10, weight="bold", slant="italic"
        )

        # -- toolbar --------------------------------------------------
        toolbar = ttk.Frame(self, style="Raised.TFrame")
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="Output", style="Heading.TLabel").pack(
            side="left", padx=(10, 0), pady=6
        )

        self.status_label = ttk.Label(toolbar, text="Idle", style="Muted.Raised.TLabel")
        self.status_label.pack(side="left", padx=(12, 0))

        ttk.Button(
            toolbar, text="Copy", style="Toolbar.TButton", command=self.copy_to_clipboard
        ).pack(side="right", padx=(0, 8), pady=4)
        ttk.Button(
            toolbar, text="Clear", style="Toolbar.TButton", command=self.clear
        ).pack(side="right", padx=(0, 4), pady=4)

        ttk.Separator(self).pack(fill="x")

        # -- text area --------------------------------------------------
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        self.text = tk.Text(
            body,
            bg=self.DEFAULT_BG,
            fg=self.DEFAULT_FG,
            insertbackground=FG,
            selectbackground=SURFACE_HI,
            selectforeground=FG,
            font=self.base_font,
            wrap="word",
            state="disabled",
            relief="flat",
            padx=10,
            pady=8,
            highlightthickness=0,
        )

        # Fixed-width tab stops (8 monospace columns), so tab-aligned output
        # (tables, column dumps, etc.) actually lines up instead of using
        # Tk's default proportional tab stops.
        char_width = self.base_font.measure("0")
        self.text.configure(tabs=(char_width * 8,), tabstyle="tabular")

        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        self._tags: dict[tuple, str] = {}
        self.reset()

    # -- state / styling -------------------------------------------------

    def reset(self):
        self.state = {
            "fg": self.DEFAULT_FG,
            "bg": self.DEFAULT_BG,
            "bold": False,
            "italic": False,
            "underline": False,
        }

    def _font_for_state(self) -> font.Font:
        bold, italic = self.state["bold"], self.state["italic"]
        if bold and italic:
            return self.bold_italic_font
        if bold:
            return self.bold_font
        if italic:
            return self.italic_font
        return self.base_font

    def _tag(self) -> str:
        key = tuple(self.state.items())

        name = self._tags.get(key)
        if name is None:
            name = f"ansi_{len(self._tags)}"
            self.text.tag_configure(
                name,
                foreground=self.state["fg"],
                background=self.state["bg"],
                font=self._font_for_state(),
                underline=self.state["underline"],
            )
            self._tags[key] = name

        return name

    def _apply_ansi(self, codes: list[str]):
        if not codes or codes == [""]:
            codes = ["0"]

        i = 0
        while i < len(codes):
            c = codes[i]

            if c == "0":
                self.reset()
            elif c == "1":
                self.state["bold"] = True
            elif c == "3":
                self.state["italic"] = True
            elif c == "4":
                self.state["underline"] = True
            elif c == "22":
                self.state["bold"] = False
            elif c == "23":
                self.state["italic"] = False
            elif c == "24":
                self.state["underline"] = False
            elif c in ("38", "48") and i + 1 < len(codes):
                target = "fg" if c == "38" else "bg"
                mode = codes[i + 1]

                if mode == "2" and i + 4 < len(codes):
                    r, g, b = codes[i + 2:i + 5]
                    self.state[target] = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
                    i += 4
                elif mode == "5" and i + 2 < len(codes):
                    self.state[target] = ansi_256_to_hex(int(codes[i + 2]))
                    i += 2
            elif c in ANSI_COLORS:
                self.state["fg"] = ANSI_COLORS[c]

            i += 1

    # -- public API --------------------------------------------------------

    def write(self, data: str):
        """Append text. Safe to call only from the main/UI thread."""
        self.text.config(state="normal")

        pos = 0
        for match in ANSI_PATTERN.finditer(data):
            if match.start() > pos:
                self._write_plain(data[pos:match.start()])
            self._apply_ansi(match.group(1).split(";"))
            pos = match.end()

        if pos < len(data):
            self._write_plain(data[pos:])

        self.text.see("end")
        self.text.config(state="disabled")

    def _write_plain(self, chunk: str):
        """Insert non-ANSI-escape text, treating \\r as 'return to start of
        the current line' like a real terminal (used by progress bars)."""
        # \r\n is a normal newline, not an overwrite -- keep it intact.
        chunk = chunk.replace("\r\n", "\n")

        segments = chunk.split("\r")
        for i, segment in enumerate(segments):
            if i > 0:
                # A bare \r: wipe everything typed since the last newline.
                self.text.delete("end linestart", "end")
            if segment:
                self.text.insert("end", segment, self._tag())

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    def copy_to_clipboard(self):
        content = self.text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)

    def write_command(self, cmd: list[str]):
        """Print the invoked command as a shell-prompt-style line, e.g. `$ foo bar`."""
        rendered = " ".join(shlex.quote(part) for part in cmd)
        self.text.config(state="normal")
        self.text.insert("end", "$ ", self._system_tag(bold=True, color=ACCENT))
        self.text.insert("end", rendered + "\n", self._system_tag(bold=False, color=FG_MUTED))
        self.text.see("end")
        self.text.config(state="disabled")

    def write_status(self, message: str, ok: bool):
        """Print a bold status line (e.g. exit code) in green or red."""
        color = SUCCESS if ok else DANGER
        self.text.config(state="normal")
        self.text.insert("end", message + "\n", self._system_tag(bold=True, color=color))
        self.text.see("end")
        self.text.config(state="disabled")

    def set_status(self, text: str, color: str = FG_MUTED):
        self.status_label.config(text=text, foreground=color, background=BG_RAISED)

    def _system_tag(self, *, bold: bool, color: str) -> str:
        """Tag for GUI-generated lines (command echo, exit status) -- kept
        separate from the ANSI-driven tag cache so it never collides with
        colors chosen by the subprocess's own output."""
        key = ("__system__", bold, color)
        name = self._tags.get(key)
        if name is None:
            name = f"sys_{len(self._tags)}"
            self.text.tag_configure(
                name,
                foreground=color,
                font=self.bold_font if bold else self.base_font,
            )
            self._tags[key] = name
        return name


class MidchipTab(ttk.Frame):
    def __init__(self, parent, module: str, launch, stop, settings: Settings):
        super().__init__(parent)

        self.module = module
        self.launch_callback = launch
        self.stop_callback = stop
        self.settings = settings
        self._saved = settings.for_tab(module)

        self.midi = tk.StringVar(value=self._saved.get("midi", ""))
        self.chip = tk.StringVar(value=self._saved.get("chip", NO_CHIP))
        self.no_chip_limits = tk.BooleanVar(value=self._saved.get("no_chip_limits", False))

        self.reverb = tk.BooleanVar(value=self._saved.get("reverb", False))
        self.vibrato = tk.BooleanVar(value=self._saved.get("vibrato", False))
        self.stereo = tk.BooleanVar(value=self._saved.get("stereo", True))

        self.volume = tk.DoubleVar(value=self._saved.get("volume", MASTER_VOLUME))

        self.substitute = tk.StringVar(value=self._saved.get("substitute", ""))

        self.unison = tk.IntVar(value=self._saved.get("unison", 1))
        self.detune = tk.DoubleVar(value=self._saved.get("detune", 8.0))
        self.workers = tk.IntVar(value=self._saved.get("workers", 0))

        self.no_dither = tk.BooleanVar(value=self._saved.get("no_dither", False))
        self.no_rms_fix = tk.BooleanVar(value=self._saved.get("no_rms_fix", False))
        self.seed = tk.StringVar(value=self._saved.get("seed", ""))

        self.attack = tk.StringVar(value=self._saved.get("attack", ""))
        self.release = tk.StringVar(value=self._saved.get("release", ""))

        self.normalize_target = tk.DoubleVar(value=self._saved.get("normalize_target", 0.35))
        self.limiter_threshold = tk.DoubleVar(value=self._saved.get("limiter_threshold", 0.7))

        self.reverb_mix = tk.DoubleVar(value=self._saved.get("reverb_mix", REVERB_MIX))
        self.reverb_decay = tk.DoubleVar(value=self._saved.get("reverb_decay", REVERB_DECAY))

        self.vibrato_depth = tk.DoubleVar(
            value=self._saved.get("vibrato_depth", VIBRATO_DEPTH_SEMITONES)
        )
        self.vibrato_rate = tk.DoubleVar(
            value=self._saved.get("vibrato_rate", VIBRATO_RATE_HZ)
        )

        # -- output / export (module-specific: "midchip" renders a .wav,
        # "midchip.viz" either plays live or exports a .mp4) --------------
        self.output = tk.StringVar(value=self._saved.get("output", ""))
        self.play = tk.BooleanVar(value=self._saved.get("play", False))
        self.export = tk.StringVar(value=self._saved.get("export", ""))
        self.width = tk.IntVar(value=self._saved.get("width", VIZ_DEFAULT_WIDTH))
        self.height = tk.IntVar(value=self._saved.get("height", VIZ_DEFAULT_HEIGHT))
        self.fps = tk.IntVar(value=self._saved.get("fps", FPS))

        self.recent_files: list[str] = self._saved.get("recent_files", [])

        self.advanced_open = False

        # -- scrollable body -------------------------------------------
        # there are enough option rows now (esp. with Advanced open) that
        # this can run taller than the window; wrap everything in a
        # canvas + scrollbar instead of letting it get clipped.
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        vscroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vscroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)

        self.inner = ttk.Frame(self.canvas, padding=16)
        self._inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._inner_window, width=e.width),
        )

        self.inner.columnconfigure(0, weight=1)
        self._build()

        # bind the wheel directly on every widget in the tab instead of the
        # canvas itself: self.inner (and everything inside it) is a real
        # widget stacked on top of the canvas, so Enter/Leave land on
        # whichever of *those* is under the cursor, not on the canvas -
        # the canvas basically never sees the mouse, so a canvas-only
        # binding never fires.
        self._bind_mousewheel_recursive(self.inner)

    def _bind_mousewheel_recursive(self, widget):
        # skip widgets that already scroll themselves on the wheel (the
        # wave-disable listbox and its own scrollbar) so we don't fight
        # their native behavior.
        if not isinstance(widget, (tk.Listbox, ttk.Scrollbar)):
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
            widget.bind("<Button-4>", self._on_mousewheel, add="+")
            widget.bind("<Button-5>", self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build(self):
        row = 0

        input_frame = ttk.Labelframe(self.inner, text="Input", padding=12)
        input_frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        input_frame.columnconfigure(1, weight=1)
        row += 1

        ttk.Label(input_frame, text="MIDI file").grid(row=0, column=0, sticky="w", pady=4)
        self.midi_combo = ttk.Combobox(
            input_frame, textvariable=self.midi, values=self.recent_files
        )
        self.midi_combo.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(input_frame, text="Browse...", command=self._pick_file).grid(
            row=0, column=2
        )

        ttk.Label(input_frame, text="Chip").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            input_frame,
            textvariable=self.chip,
            values=[NO_CHIP] + sorted(CHIP_PROFILES),
            state="readonly",
        ).grid(row=1, column=1, columnspan=2, sticky="ew", padx=8)

        ttk.Checkbutton(
            input_frame, text="No channel limits (ignore chip's polyphony cap)",
            variable=self.no_chip_limits,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        output_frame = ttk.Labelframe(self.inner, text="Output", padding=12)
        output_frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        output_frame.columnconfigure(1, weight=1)
        row += 1

        if self.module == "midchip.viz":
            ttk.Label(output_frame, text="Export video").grid(row=0, column=0, sticky="w", pady=4)
            ttk.Entry(output_frame, textvariable=self.export).grid(
                row=0, column=1, sticky="ew", padx=8
            )
            ttk.Button(
                output_frame, text="Browse...", command=self._pick_export
            ).grid(row=0, column=2)
            ttk.Label(
                output_frame, text="Leave blank to open a live window instead",
                style="Muted.TLabel",
            ).grid(row=1, column=1, sticky="w", padx=8)

            for r, text, var, lo, hi in (
                (2, "Width", self.width, 64, 7680),
                (3, "Height", self.height, 64, 4320),
                (4, "FPS", self.fps, 1, 240),
            ):
                ttk.Label(output_frame, text=text).grid(row=r, column=0, sticky="w", pady=4)
                ttk.Spinbox(
                    output_frame, textvariable=var, from_=lo, to=hi, width=8
                ).grid(row=r, column=1, sticky="w", padx=8)
        else:
            ttk.Label(output_frame, text="Save to .wav").grid(row=0, column=0, sticky="w", pady=4)
            ttk.Entry(output_frame, textvariable=self.output).grid(
                row=0, column=1, sticky="ew", padx=8
            )
            ttk.Button(
                output_frame, text="Browse...", command=self._pick_output
            ).grid(row=0, column=2)
            ttk.Checkbutton(
                output_frame, text="Play back audio (always on if no file is saved)",
                variable=self.play,
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        options_frame = ttk.Labelframe(self.inner, text="Options", padding=12)
        options_frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        options_frame.columnconfigure(3, weight=1)
        row += 1

        for i, (text, var) in enumerate(
            (
                ("Reverb", self.reverb),
                ("Vibrato", self.vibrato),
                ("Stereo", self.stereo),
            )
        ):
            ttk.Checkbutton(options_frame, text=text, variable=var).grid(
                row=0, column=i, sticky="w", padx=(0 if i == 0 else 16, 0)
            )

        ttk.Label(options_frame, text="Volume").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(
            options_frame, textvariable=self.volume, from_=0.0, to=1.0,
            increment=0.05, width=6,
        ).grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))

        self.advanced_btn = ttk.Button(
            self.inner, text="\u25b6  Advanced options", command=self._toggle_advanced
        )
        self.advanced_btn.grid(row=row, column=0, sticky="w")
        row += 1

        self.advanced = ttk.Labelframe(self.inner, text="Advanced", padding=12)
        self.advanced.columnconfigure(1, weight=1)
        self._advanced_row = row
        row += 1

        ttk.Label(self.advanced, text="Disable waves").grid(row=0, column=0, sticky="nw", pady=4)
        list_wrap = ttk.Frame(self.advanced)
        list_wrap.grid(row=0, column=1, sticky="ew", padx=8)
        self.disable = tk.Listbox(
            list_wrap,
            selectmode="multiple",
            height=6,
            exportselection=False,
            font=(pick_mono_font(self), 10),
            bg=SURFACE,
            fg=FG,
            selectbackground=ACCENT,
            selectforeground="#1e1e2e",
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        wave_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.disable.yview)
        self.disable.configure(yscrollcommand=wave_scroll.set)
        self.disable.pack(side="left", fill="both", expand=True)
        wave_scroll.pack(side="right", fill="y")
        for wave in sorted(ALL_WAVES):
            self.disable.insert("end", wave)
        for i, wave in enumerate(sorted(ALL_WAVES)):
            if wave in self._saved.get("disabled_waves", []):
                self.disable.selection_set(i)

        ttk.Label(self.advanced, text="Substitutions").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(self.advanced, textvariable=self.substitute).grid(
            row=1, column=1, sticky="ew", padx=8
        )

        for r, text, var, lo, hi in (
            (2, "Unison", self.unison, 1, 8),
            (3, "Workers", self.workers, 0, 32),
        ):
            ttk.Label(self.advanced, text=text).grid(row=r, column=0, sticky="w", pady=4)
            ttk.Spinbox(
                self.advanced, textvariable=var, from_=lo, to=hi, width=6
            ).grid(row=r, column=1, sticky="w", padx=8)

        for r, text, var, lo, hi, inc in (
            (4, "Detune (cents)", self.detune, 0.0, 100.0, 0.5),
            (5, "Normalize target", self.normalize_target, 0.0, 2.0, 0.05),
            (6, "Limiter threshold", self.limiter_threshold, 0.0, 1.0, 0.05),
            (7, "Reverb mix", self.reverb_mix, 0.0, 1.0, 0.05),
            (8, "Reverb decay", self.reverb_decay, 0.0, 0.95, 0.05),
            (9, "Vibrato depth (semitones)", self.vibrato_depth, 0.0, 12.0, 0.05),
            (10, "Vibrato rate (Hz)", self.vibrato_rate, 0.0, 20.0, 0.1),
        ):
            ttk.Label(self.advanced, text=text).grid(row=r, column=0, sticky="w", pady=4)
            ttk.Spinbox(
                self.advanced, textvariable=var, from_=lo, to=hi, increment=inc, width=8
            ).grid(row=r, column=1, sticky="w", padx=8)

        ttk.Label(self.advanced, text="Attack (s, blank=default)").grid(
            row=11, column=0, sticky="w", pady=4
        )
        ttk.Entry(self.advanced, textvariable=self.attack, width=10).grid(
            row=11, column=1, sticky="w", padx=8
        )

        ttk.Label(self.advanced, text="Release (s, blank=default)").grid(
            row=12, column=0, sticky="w", pady=4
        )
        ttk.Entry(self.advanced, textvariable=self.release, width=10).grid(
            row=12, column=1, sticky="w", padx=8
        )

        ttk.Label(self.advanced, text="Seed (blank=random)").grid(
            row=13, column=0, sticky="w", pady=4
        )
        ttk.Entry(self.advanced, textvariable=self.seed, width=10).grid(
            row=13, column=1, sticky="w", padx=8
        )

        ttk.Checkbutton(
            self.advanced, text="No dithering", variable=self.no_dither
        ).grid(row=14, column=0, sticky="w", pady=(8, 0))

        ttk.Checkbutton(
            self.advanced, text="No per-note RMS fix", variable=self.no_rms_fix
        ).grid(row=15, column=0, sticky="w", pady=(4, 0))

        if self._saved.get("advanced_open"):
            self._toggle_advanced()

        button_row = ttk.Frame(self.inner)
        button_row.grid(row=row, column=0, sticky="ew", pady=(16, 0))
        row += 1

        self.launch_btn = ttk.Button(
            button_row, text="\u25b6  Launch", style="Accent.TButton", command=self._on_launch
        )
        self.launch_btn.pack(side="left")

        self.exit_btn = ttk.Button(
            button_row,
            text="\u25a0  Exit",
            style="Danger.TButton",
            command=self._on_stop,
            state="disabled",
        )
        self.exit_btn.pack(side="left", padx=(8, 0))

        self.status_dot = StatusDot(button_row)
        self.status_dot.pack(side="left", padx=(12, 4))
        self.status_text = ttk.Label(button_row, text="Idle", style="Muted.TLabel")
        self.status_text.pack(side="left")

    def _toggle_advanced(self):
        self.advanced_open = not self.advanced_open

        if self.advanced_open:
            self.advanced.grid(row=self._advanced_row, column=0, sticky="ew", pady=(8, 0))
            self.advanced_btn.config(text="\u25bc  Advanced options")
        else:
            self.advanced.grid_forget()
            self.advanced_btn.config(text="\u25b6  Advanced options")

    def _pick_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("MIDI files", ("*.mid", "*.midi")), ("All files", "*.*")]
        )
        if path:
            self.midi.set(path)

    def _pick_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        if path:
            self.output.set(path)

    def _pick_export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if path:
            self.export.set(path)

    def _remember_file(self, path: str):
        self.recent_files = [path] + [p for p in self.recent_files if p != path]
        self.recent_files = self.recent_files[:MAX_RECENT_FILES]
        self.midi_combo.configure(values=self.recent_files)

    def _on_launch(self):
        path = self.midi.get().strip()
        if not path:
            messagebox.showerror("No MIDI file", "Please choose a MIDI file first.")
            return
        if not Path(path).is_file():
            messagebox.showerror("File not found", f"Can't find:\n{path}")
            return

        try:
            cmd = self._build_command()
        except FileNotFoundError as exc:
            messagebox.showerror("Can't launch", str(exc))
            return

        self._remember_file(path)
        self.save_settings()
        self.launch_callback(cmd, self)

    def _on_stop(self):
        self.stop_callback(self)

    def _build_command(self) -> list[str]:
        cmd = _cli_command(self.module) + [self.midi.get()]

        if self.chip.get() != NO_CHIP:
            cmd += ["--chip", self.chip.get()]

        if self.no_chip_limits.get():
            cmd.append("--no-chip-channel-limits")

        if self.reverb.get():
            cmd.append("--reverb")

        if self.vibrato.get():
            cmd.append("--vibrato")

        if not self.stereo.get():
            cmd.append("--mono")

        if self.volume.get() != MASTER_VOLUME:
            cmd += ["--volume", str(self.volume.get())]

        disabled = [self.disable.get(i) for i in self.disable.curselection()]
        if disabled:
            cmd += ["--disable", ",".join(disabled)]

        if self.substitute.get():
            cmd += ["--substitute", self.substitute.get()]

        if self.unison.get() != 1:
            cmd += ["--unison", str(self.unison.get())]

        if self.detune.get() != 8.0:
            cmd += ["--detune", str(self.detune.get())]

        if self.workers.get():
            cmd += ["--workers", str(self.workers.get())]

        if self.no_dither.get():
            cmd.append("--no-dither")

        if self.no_rms_fix.get():
            cmd.append("--no-rms-fix")

        if self.seed.get().strip():
            cmd += ["--seed", self.seed.get().strip()]

        if self.attack.get().strip():
            cmd += ["--attack", self.attack.get().strip()]

        if self.release.get().strip():
            cmd += ["--release", self.release.get().strip()]

        if self.normalize_target.get() != 0.35:
            cmd += ["--normalize-target", str(self.normalize_target.get())]

        if self.limiter_threshold.get() != 0.7:
            cmd += ["--limiter-threshold", str(self.limiter_threshold.get())]

        if self.reverb_mix.get() != REVERB_MIX:
            cmd += ["--reverb-mix", str(self.reverb_mix.get())]

        if self.reverb_decay.get() != REVERB_DECAY:
            cmd += ["--reverb-decay", str(self.reverb_decay.get())]

        if self.vibrato_depth.get() != VIBRATO_DEPTH_SEMITONES:
            cmd += ["--vibrato-depth", str(self.vibrato_depth.get())]

        if self.vibrato_rate.get() != VIBRATO_RATE_HZ:
            cmd += ["--vibrato-rate", str(self.vibrato_rate.get())]

        if self.module == "midchip.viz":
            if self.export.get().strip():
                cmd += ["--export", self.export.get().strip()]
            if self.width.get() != VIZ_DEFAULT_WIDTH:
                cmd += ["--width", str(self.width.get())]
            if self.height.get() != VIZ_DEFAULT_HEIGHT:
                cmd += ["--height", str(self.height.get())]
            if self.fps.get() != FPS:
                cmd += ["--fps", str(self.fps.get())]
        else:
            if self.output.get().strip():
                cmd += ["--output", self.output.get().strip()]
            if self.play.get():
                cmd.append("--play")

        return cmd

    def save_settings(self):
        disabled = [self.disable.get(i) for i in self.disable.curselection()]
        self._saved.update(
            midi=self.midi.get(),
            chip=self.chip.get(),
            no_chip_limits=self.no_chip_limits.get(),
            reverb=self.reverb.get(),
            vibrato=self.vibrato.get(),
            stereo=self.stereo.get(),
            volume=self.volume.get(),
            substitute=self.substitute.get(),
            unison=self.unison.get(),
            detune=self.detune.get(),
            workers=self.workers.get(),
            no_dither=self.no_dither.get(),
            no_rms_fix=self.no_rms_fix.get(),
            seed=self.seed.get(),
            attack=self.attack.get(),
            release=self.release.get(),
            normalize_target=self.normalize_target.get(),
            limiter_threshold=self.limiter_threshold.get(),
            reverb_mix=self.reverb_mix.get(),
            reverb_decay=self.reverb_decay.get(),
            vibrato_depth=self.vibrato_depth.get(),
            vibrato_rate=self.vibrato_rate.get(),
            output=self.output.get(),
            play=self.play.get(),
            export=self.export.get(),
            width=self.width.get(),
            height=self.height.get(),
            fps=self.fps.get(),
            disabled_waves=disabled,
            recent_files=self.recent_files,
            advanced_open=self.advanced_open,
        )
        self.settings.save()

    def set_running(self, running: bool):
        self.launch_btn.config(
            state="disabled" if running else "normal",
            text="Running..." if running else "\u25b6  Launch",
        )
        self.exit_btn.config(
            state="normal" if running else "disabled", text="\u25a0  Exit"
        )
        if running:
            self.status_dot.set_color(SUCCESS)
        else:
            self.status_dot.set_color(FG_DIM)
            self.status_text.config(text="Idle")

    def set_stopping(self):
        self.exit_btn.config(state="disabled", text="Stopping...")
        self.status_dot.set_color(WARNING)
        self.status_text.config(text="Stopping...")

    def set_elapsed(self, text: str):
        self.status_text.config(text=text)

    def set_finished(self, ok: bool):
        self.status_dot.set_color(SUCCESS if ok else DANGER)
        self.status_text.config(text="Done" if ok else "Failed")


class App:
    STOP_GRACE_MS = 5000
    TICK_MS = 250

    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings()

        root.title("MidChip")
        root.geometry("640x600")
        root.minsize(560, 480)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # iconphoto sets both the window titlebar icon and (on
        # Linux/Windows) the taskbar icon. Keep a reference on self --
        # tk.PhotoImage has no Python-side owner otherwise and gets
        # garbage-collected out from under the window.
        icon_file = asset_path("midchip.png")
        if icon_file is not None:
            try:
                self._icon_image = tk.PhotoImage(file=str(icon_file))
                root.iconphoto(True, self._icon_image)
            except tk.TclError:
                pass  # missing/corrupt icon is cosmetic, never fatal

        base_font = font.Font(family=pick_ui_font(root), size=10)
        apply_dark_theme(root, base_font)

        # -- header -------------------------------------------------
        header = ttk.Frame(root, style="Raised.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="\u266b  MidChip", style="Heading.TLabel").pack(
            side="left", padx=12, pady=8
        )
        ttk.Separator(root).pack(fill="x")

        self.paned = ttk.PanedWindow(root, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(self.paned)
        self.terminal = Terminal(self.paned)

        self.paned.add(self.notebook, weight=1)
        self._terminal_shown = False

        self.notebook.add(
            MidchipTab(self.notebook, "midchip", self.launch, self.stop, self.settings),
            text="MidChip",
        )
        self.notebook.add(
            MidchipTab(
                self.notebook, "midchip.viz", self.launch, self.stop, self.settings
            ),
            text="MidChip (Visualizer)",
        )

        self.current_proc: subprocess.Popen | None = None
        self.current_tab: MidchipTab | None = None
        self._stop_requested = False
        self._run_started_at: float | None = None
        self._tick_job: str | None = None

    def _tabs(self) -> list[MidchipTab]:
        return [self.notebook.nametowidget(t) for t in self.notebook.tabs()]

    def _show_terminal(self):
        if self._terminal_shown:
            return
        self.paned.add(self.terminal, weight=1)
        self._terminal_shown = True
        self.root.geometry("1200x640")

    def launch(self, cmd: list[str], tab: MidchipTab):
        if self.current_proc is not None and self.current_proc.poll() is None:
            messagebox.showinfo(
                "Already running",
                "A process is already running. Use Exit to stop it before starting another.",
            )
            return

        self._show_terminal()
        self.terminal.clear()
        self.terminal.write_command(cmd)
        self.terminal.set_status("Running", ACCENT)
        tab.set_running(True)
        self.current_tab = tab
        self._run_started_at = time.monotonic()
        self._tick()

        env = os.environ.copy()
        env["MIDCHIP_GUI"] = "1"

        popen_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
        except OSError as exc:
            tab.set_running(False)
            tab.set_finished(ok=False)
            self.terminal.set_status("Idle")
            self.current_proc = None
            messagebox.showerror("Launch failed", str(exc))
            return

        self.current_proc = proc
        self._stop_requested = False

        out_queue: "queue.Queue[str | tuple[None, int]]" = queue.Queue()

        def reader():
            assert proc.stdout is not None
            for line in proc.stdout:
                out_queue.put(line)
            proc.stdout.close()
            proc.wait()
            out_queue.put((None, proc.returncode))  # sentinel: process finished

        threading.Thread(target=reader, daemon=True).start()
        self._poll_output(out_queue, tab)

    def stop(self, tab: MidchipTab):
        proc = self.current_proc
        if proc is None or proc.poll() is not None:
            return

        tab.set_stopping()
        self._stop_requested = True

        try:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_C_EVENT)
            else:
                proc.send_signal(signal.SIGINT)
        except (ProcessLookupError, OSError):
            # Signal delivery isn't guaranteed on every platform/setup
            # (e.g. a Windows child not in a console process group).
            # Fall back to a plain terminate request; the grace-period
            # timer below still force-kills if even that doesn't work.
            try:
                proc.terminate()
            except OSError:
                pass

        self.root.after(self.STOP_GRACE_MS, self._force_kill_if_alive, proc)

    def _force_kill_if_alive(self, proc: subprocess.Popen):
        if proc.poll() is None:
            proc.kill()

    def _tick(self):
        """Update the live 'Running for Ns' status while a process is active."""
        if self.current_proc is None or self.current_proc.poll() is not None:
            self._tick_job = None
            return

        if self._run_started_at is not None and self.current_tab is not None:
            elapsed = time.monotonic() - self._run_started_at
            text = f"Running \u00b7 {format_elapsed(elapsed)}"
            self.current_tab.set_elapsed(text)
            self.terminal.set_status(text, ACCENT)

        self._tick_job = self.root.after(self.TICK_MS, self._tick)

    def _poll_output(self, out_queue: "queue.Queue[str | tuple[None, int]]", tab: MidchipTab):
        """Drain the queue on the main thread so all Tk calls stay on the UI thread."""
        try:
            while True:
                item = out_queue.get_nowait()
                if isinstance(item, tuple):
                    _, code = item
                    self._report_exit(code, tab)
                    tab.set_running(False)
                    if self.current_tab is tab:
                        self.current_proc = None
                    return
                self.terminal.write(item)
        except queue.Empty:
            pass

        self.root.after(30, self._poll_output, out_queue, tab)

    def _report_exit(self, code: int | None, tab: MidchipTab):
        ok = code == 0
        if ok:
            self.terminal.write_status(f"Exited with code {code}", ok=True)
        elif self._stop_requested:
            # We asked it to stop (Exit button) -- report that plainly rather
            # than guessing at signal semantics, which differ across platforms
            # (POSIX encodes "killed by signal N" as -N; Windows does not).
            self.terminal.write_status("Stopped by user", ok=False)
        else:
            self.terminal.write_status(f"Exited with code {code}", ok=False)

        self.terminal.set_status("Idle")
        tab.set_finished(ok)

    def _on_close(self):
        proc = self.current_proc
        if proc is not None and proc.poll() is None:
            if not messagebox.askyesno(
                "Process still running",
                "A process is still running. Quit and stop it?",
            ):
                return
            try:
                proc.kill()
            except OSError:
                pass

        for tab in self._tabs():
            tab.save_settings()

        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()