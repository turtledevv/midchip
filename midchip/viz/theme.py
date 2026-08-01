"""
midchip.viz.theme | colors for visualizer
----------
Catppuccin Mocha palette used by the visualizer :D
"""

BASE    = (30, 30, 46)
MANTLE  = (24, 24, 37)
SURFACE = (49, 50, 68)
TEXT    = (205, 214, 244)
SUBTEXT = (166, 173, 200)
OVERLAY = (108, 112, 134)
BLUE    = (137, 180, 250)

WAVE_COLORS: dict[str, tuple[int, int, int]] = {
    "square":   (137, 180, 250),  # blue
    "triangle": (166, 227, 161),  # green
    "saw":      (250, 179, 135),  # peach
    "noise":    (243, 139, 168),  # red
    "pulse25":  (137, 220, 235),  # sky
    "pulse12":  (116, 199, 236),  # sapphire
    "pwm":      (203, 166, 247),  # mauve
    "additive": (249, 226, 175),  # yellow
    "half_saw": (235, 160, 172),  # maroon
    "ring_mod": (148, 226, 213),  # teal
    "sine":     (180, 190, 254),  # lavender
    "fm_bell":  (245, 194, 231),  # pink
    "supersaw": (245, 194, 231),  # pink, but again
}


def wave_color(wave_type: str) -> tuple[int, int, int]:
    return WAVE_COLORS.get(wave_type, TEXT)
