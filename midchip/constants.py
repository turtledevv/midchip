"""
midchip.constants | shared numbers for parsing, synthesis, and chips
----------
just a bunch of numbers and lists and such
"""
from __future__ import annotations

SAMPLE_RATE = 44100
NYQUIST     = SAMPLE_RATE / 2.0

MASTER_VOLUME = 0.2
ATTACK        = 0.01
RELEASE       = 0.05

# retriggered notes (aka rt notes) (same key re-struck before note-off arrived) replaces
# a pitch the ear is already hearing instead of starting from silence.
# giving an rt note the same full attack ramp as a fresh note sound off is a bad idea;
# this instead shortens the attack and such to make it sound cleaner
RETRIGGER_ATTACK = 0.002

# shitty dirty hack that's been left over from the first ever version of midchip.
WAVE_LOUDNESS: dict[str, float] = {
    "square": 1.0, "triangle": 1.0, "saw": 1.0, "noise": 0.8,
    "pulse25": 1.0, "pulse12": 1.0, "pwm": 1.0, "additive": 1.0,
    "half_saw": 1.0, "ring_mod": 1.0,
    "sine": 1.0, "fm_bell": 0.9, "supersaw": 1.0,
}

ALL_WAVES: frozenset[str] = frozenset(WAVE_LOUDNESS)

# some waveforms pierce at high pitches; so we pull them back to save our ears
HF_HARSH: frozenset[str] = frozenset({
    "triangle", "ring_mod", "additive", "half_saw", "pulse25", "pulse12",
    "fm_bell", "square",
})
HF_THRESH = 1600.0   # hz, rolloff onset (roughly G6)
HF_ALPHA  = 0.35     # 1.0 = -6 dB/oct, 0.5 = -3 dB/oct
HF_FLOOR  = 0.6

# ~2-4kHz is where human hearing is most sensitive, and blah blah blah
# read comments for presence_gain() in synth.py for more info
PRESENCE_CENTER = 2700.0
PRESENCE_WIDTH  = 900.0
PRESENCE_DEPTH  = 0.5

# wave fallback chain
WAVE_REPLACEMENTS: dict[str, str] = {
    "square":   "triangle",
    "triangle": "square",
    "saw":      "triangle",
    "noise":    "square",
    "pulse25":  "square",
    "pulse12":  "square",
    "pwm":      "square",
    "additive": "triangle",
    "half_saw": "saw",
    "ring_mod": "square",
    "sine":     "triangle",
    "fm_bell":  "additive",
    "supersaw": "saw",
}

# GM percussion note num. -> drum category
GM_DRUM_MAP: dict[int, str] = {
    35: "kick", 36: "kick",
    37: "snare", 38: "snare", 40: "snare",
    41: "tom", 43: "tom", 45: "tom", 47: "tom", 48: "tom", 50: "tom",
    42: "hihat_closed", 44: "hihat_closed",
    46: "hihat_open",
    49: "cymbal", 51: "cymbal", 52: "cymbal", 53: "cymbal",
    55: "cymbal", 57: "cymbal", 59: "cymbal",
}

# per-category envelope (seconds).
DRUM_ATTACK: dict[str, float] = {
    "kick": 0.002, "snare": 0.002, "tom": 0.003,
    "hihat_closed": 0.001, "hihat_open": 0.001, "cymbal": 0.002,
    "default": 0.002,
}
DRUM_RELEASE: dict[str, float] = {
    "kick": 0.15, "snare": 0.09, "tom": 0.12,
    "hihat_closed": 0.04, "hihat_open": 0.25, "cymbal": 0.4,
    "default": 0.06,
}

# per-category loudness.
DRUM_LOUDNESS: dict[str, float] = {
    "kick": 0.95, "snare": 0.65, "tom": 0.8,
    "hihat_closed": 0.35, "hihat_open": 0.4, "cymbal": 0.45,
    "default": 0.55,
}


KICK_TONE_START_HZ = 150.0
KICK_TONE_END_HZ   = 45.0
KICK_TONE_MIX      = 0.6   # 1.0 = all pitched thump, 0.0 = all noise body
KICK_PITCH_DECAY   = 0.05  # seconds; how fast sweep collapses to KICK_TONE_END_HZ


PITCH_BEND_RANGE_SEMITONES = 2.0


VIBRATO_RATE_HZ         = 5.5   # Hz, typical vocal/instrumental vibrato rate
VIBRATO_DEPTH_SEMITONES = 0.35  # peak pitch swing once fully ramped in, at VIBRATO_REF_HZ
VIBRATO_DELAY           = 0.08  # seconds before vibrato starts ramping in
VIBRATO_RAMP            = 0.15  # seconds to reach full depth after the delay

VIBRATO_REF_HZ          = 440.0  # A4 - depth is unscaled (1.0x) at this pitch
VIBRATO_REGISTER_EXP    = 0.2
VIBRATO_SCALE_MIN       = 0.75
VIBRATO_SCALE_MAX       = 1.25

PAN_DEFAULT = 0.5   # channel's pan absent any CC10 message in the file

REVERB_COMB_DELAYS_MS    = (29.7, 37.1, 41.1, 43.7)
REVERB_ALLPASS_DELAYS_MS = (5.0, 1.7)
REVERB_ALLPASS_GAIN      = 0.5
REVERB_DECAY             = 0.55  # comb feedback gain - higher = longer tail
REVERB_STEREO_SPREAD_MS  = 0.8   # per-channel delay offset for stereo width
REVERB_MIX               = 0.22  # wet/dry blend
REVERB_TAIL_SECONDS      = 1.5   # extra buffer padding so the tail isn't cut off

DISP_SAMPLES = 512   # oscilloscope x-res per channel
FPS          = 120