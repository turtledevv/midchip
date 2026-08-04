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


# ── hardware chip constants (2A03/VRC6/FDS/DMG) ─────────────────────────────
# CPU clocks and register-level facts used to make chip-restricted synthesis
# actually behave like the real silicon (discrete pitches, real LFSR noise,
# real wavetable widths, hardware envelope steps) instead of generic
# freeform synthesis. Sources: nesdev.org/wiki/APU_Pulse, APU_Triangle,
# APU_Noise, APU_Envelope, VRC6_audio, FDS_audio; gbdev.io/pandocs
# Audio_Registers.html, Audio_details.html.

NES_CPU_CLOCK_NTSC = 1_789_773   # Hz, RP2A03 NTSC CPU/APU clock
GB_CPU_CLOCK        = 4_194_304  # Hz, DMG CPU clock

# APU pulse/triangle timer: f = fCPU / (divisor * (period + 1)), period is an
# N-bit register (0..2^bits-1). Pulse divides by 16, triangle by 32 (the
# triangle's 32-step sequencer is clocked once per CPU cycle instead of once
# per APU cycle, so for the same period it lands an octave below the pulses).
NES_PULSE_DIVISOR    = 16
NES_TRIANGLE_DIVISOR = 32
NES_PERIOD_BITS      = 11

# VRC6 sawtooth: also an accumulator-based channel, but its 12-bit period
# register divides the CPU clock by 14 instead of 16 (nesdev VRC6_audio).
VRC6_SAW_DIVISOR = 14
VRC6_PERIOD_BITS = 12
# 8-bit accumulator adds its rate 6 times then resets on the 7th clock, and
# is read out as accum>>3 -> 7 distinct output levels (0, 1/6, ..., 1).
VRC6_SAW_STEPS = 7

# FDS (2C33) wave/modulation pitch: Hz = fCPU * pitch / 65536, pitch is a
# 12-bit register (nesdev FDS_audio "Main Unit" formula).
FDS_PITCH_BITS  = 12
FDS_PITCH_SCALE = 65536
# FDS wave RAM: 64 x 6-bit samples.
FDS_WAVETABLE_LEN = 64

# 2A03/VRC6/FDS noise channel: 15-bit Fibonacci LFSR, feedback = bit0 XOR
# bit(tap). "Long" (normal) mode taps bit 1 (32767-step hiss); "short" mode
# (mode flag set) taps bit 6 (93-step metallic buzz). NTSC noise period
# table is the 16 fixed reload values the 4-bit $400E rate selects between,
# in APU cycles (nesdev APU_Noise).
NES_NOISE_WIDTH     = 15
NES_NOISE_TAP_LONG  = 1
NES_NOISE_TAP_SHORT = 6
NES_NOISE_PERIODS_NTSC = (
    4, 8, 16, 32, 64, 96, 128, 160,
    202, 254, 380, 508, 762, 1016, 2034, 4068,
)

# Game Boy channel 4 (noise): also a 15-bit (or "narrow" 7-bit) LFSR,
# feedback = bit0 XOR bit1, fed into the top bit + (narrow mode only) bit 6.
# Clocked at fCPU / (divisor * 2^(shift+1)); divisor here is 8x the raw 3-bit
# "dividing ratio" field r from NR43 (r=0 counts as 0.5), giving the 8
# achievable divisors below and a max clock of 524288 Hz at r=0/shift=0
# (gbdev Audio_Registers.html). shift 14-15 stop the LFSR from being clocked
# at all, so 13 is the highest usable shift.
GB_NOISE_WIDTH     = 15
GB_NOISE_DIVISORS  = (4, 8, 16, 24, 32, 40, 48, 56)
GB_NOISE_SHIFT_MAX = 13

# Game Boy pulse/wave period: f = fCPU / (divisor * (2048 - x)), x is the
# 11-bit period register. The wave channel's divider free-runs twice as slow
# as the pulses' (clocked once per 2 dots vs. once per 4 dots), which is why
# an identical period value lands an octave lower on CH3 than on CH1/CH2.
GB_PULSE_DIVISOR  = 32
GB_WAVE_DIVISOR   = 64
GB_PERIOD_BITS    = 11
GB_WAVE_TABLE_LEN = 32   # CH3 wave RAM: 32 x 4-bit samples

# ── hardware-stepped envelopes / discrete volume levels ─────────────────────
HW_VOLUME_STEPS = 16     # 4-bit up/down envelope counter (both NES & GB)
NES_ENVELOPE_HZ = 240.0  # APU frame sequencer quarter-frame rate (NTSC)
GB_ENVELOPE_HZ  = 64.0   # DMG envelope sweep clock (gbdev Audio_Registers)
# DMG channel 3 has no envelope hardware, only a trigger-time volume
# right-shift with 4 discrete output levels: mute, 100%, 50%, 25% (NR32).
GB_WAVE_VOLUME_LEVELS = (0.0, 1.0, 0.5, 0.25)

# ── SPC700 (SNES S-DSP) representative ADSR shape ───────────────────────────
# Real hardware picks these off a 32-entry rate table per-instrument (so the
# exact numbers vary per game/patch); these are representative "typical
# chiptune instrument" values that give the right overall envelope
# character - linear attack, exponential decay to a sustain level,
# exponential release (snes.nesdev.org/wiki/DSP_envelopes).
SPC_ATTACK_TIME  = 0.01   # seconds
SPC_DECAY_TIME   = 0.05   # seconds
SPC_SUSTAIN_LVL  = 0.75   # fraction of full volume
SPC_RELEASE_TIME = 0.3    # seconds

# ── noise-channel drum presets (chip percussion) ────────────────────────────
# Real NES/GB chiptunes have no dedicated drum kit - every GM percussion hit
# routes through the single noise channel, just retuned to a different
# LFSR period/mode per drum category (see synth._generate_drum_wave). These
# target frequencies/modes are an artistic per-category choice (there's no
# single documented "correct" value), tuned to sit low + smooth for
# kicks/snares/toms and high + metallic ("short"/narrow mode) for hats/cymbal.
NES_DRUM_NOISE_PRESETS: dict[str, tuple[float, str]] = {
    "kick":         (60.0,   "long"),
    "snare":        (200.0,  "long"),
    "tom":          (110.0,  "long"),
    "hihat_closed": (4000.0, "short"),
    "hihat_open":   (4000.0, "short"),
    "cymbal":       (8000.0, "short"),
    "default":      (500.0,  "long"),
}
GB_DRUM_NOISE_PRESETS: dict[str, tuple[float, bool]] = {
    "kick":         (60.0,   False),
    "snare":        (200.0,  False),
    "tom":          (110.0,  False),
    "hihat_closed": (4000.0, True),
    "hihat_open":   (4000.0, True),
    "cymbal":       (8000.0, True),
    "default":      (500.0,  False),
}