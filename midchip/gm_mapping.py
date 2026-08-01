"""
midchip.gm_mapping | midi prog. number -> chiptune wave
----------
covers full GM instrument set (0-127) (yes that took me forever),
all chopped up into families (families that vary too much get a per-prog lookup instead)
"""
from __future__ import annotations

from .constants import WAVE_REPLACEMENTS

# Synth Lead (80-87): Square / Sawtooth / Calliope / Chiff / Charang / Voice / Fifths / Bass+Lead
_SYNTH_LEAD_WAVES = {
    80: "square",   81: "supersaw",  82: "sine",     83: "pulse12",
    84: "half_saw", 85: "pwm",       86: "ring_mod", 87: "triangle",
}

# Synth Pad (88-95): New Age / Warm / Polysynth / Choir / Bowed / Metallic / Halo / Sweep
_SYNTH_PAD_WAVES = {
    88: "sine", 89: "triangle", 90: "pwm",      91: "sine",
    92: "saw",  93: "fm_bell",  94: "additive", 95: "pwm",
}

# Ethnic (104-111): Sitar / Banjo / Shamisen / Koto / Kalimba / Bagpipe / Fiddle / Shanai
_ETHNIC_WAVES = {
    104: "pulse12", 105: "pulse25", 106: "pulse12", 107: "pulse25",
    108: "fm_bell", 109: "saw",     110: "saw",     111: "pulse12",
}

# Percussive (112-119): Tinkle Bell / Agogo / Steel Drums / Woodblock / Taiko /
#                        Melodic Tom / Synth Drum / Reverse Cymbal
_PERCUSSIVE_WAVES = {
    112: "fm_bell", 113: "fm_bell", 114: "fm_bell", 115: "square",
    116: "noise",   117: "noise",   118: "square",  119: "noise",
}


def instrument_to_wave(program: int, channel: int) -> str:
    """map a GM prog. num (0-127) to the wave that best
    matches the real sound."""
    if channel == 9:           # GM percussion key map; always unpitched drum kit
        return "noise"
    if 0 <= program <= 7:      # pianos
        return "square"
    if 8 <= program <= 15:     # chromatic percussion (yes, even the glock, as in the gun /j)
        return "fm_bell"
    if 16 <= program <= 23:    # organs
        return "additive"
    if 24 <= program <= 31:    # guitars
        return "pulse25"
    if 32 <= program <= 39:    # bass
        return "triangle"
    if 40 <= program <= 47:    # strings
        return "saw"
    if 48 <= program <= 55:    # ensembles/choir
        return "pwm"
    if 56 <= program <= 63:    # brass
        return "half_saw"
    if 64 <= program <= 71:    # reed
        return "pulse12"
    if 72 <= program <= 79:    # pipe (NOT THE CRACK KIND.)
        return "sine"
    if 80 <= program <= 87:    # synth lead
        return _SYNTH_LEAD_WAVES.get(program, "square")
    if 88 <= program <= 95:    # synth pad
        return _SYNTH_PAD_WAVES.get(program, "pwm")
    if 96 <= program <= 103:   # synth effects
        return "ring_mod"
    if 104 <= program <= 111:  # ethnic
        return _ETHNIC_WAVES.get(program, "saw")
    if 112 <= program <= 119:  # percussive
        return _PERCUSSIVE_WAVES.get(program, "noise")
    if 120 <= program <= 127:  # sound effects
        return "noise"
    return "square" # return a square and give up if we can't find anything else


def resolve_wave_type(wave: str, disabled: set[str]) -> str:
    """walk WAVE_REPLACEMENTS until we land on a wave that isn't disabled. (or just fallback to square)"""
    seen: set[str] = set()
    while wave in disabled:
        if wave in seen:
            return "square"
        seen.add(wave)
        wave = WAVE_REPLACEMENTS.get(wave, "square")
    return wave
