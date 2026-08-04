"""
midchip.chips | sound chip profiles
----------
sound-chip profiles that restrict/remap synthesis to retro
hardware limitations!!
"""
from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    ATTACK, RELEASE, ALL_WAVES,
    NES_CPU_CLOCK_NTSC, GB_CPU_CLOCK,
    NES_PULSE_DIVISOR, NES_TRIANGLE_DIVISOR, NES_PERIOD_BITS,
    VRC6_SAW_DIVISOR, VRC6_PERIOD_BITS,
    GB_PULSE_DIVISOR, GB_WAVE_DIVISOR, GB_PERIOD_BITS,
    FDS_PITCH_BITS, FDS_PITCH_SCALE,
)


@dataclass
class ChipProfile:
    name:               str
    label:              str
    supported_waves:    frozenset[str]
    wave_remap:         dict[str, str]
    channel_wave_force: dict[int, str]
    max_channels:       int | None   = None
    attack:             float        = ATTACK
    release:            float        = RELEASE
    triangle_fixed_vel: float | None = None
    freq_min:           float        = 0.0
    freq_max:           float        = 25000.0
    lowpass_hz:         float | None = None
    wave_voice_limit:   dict[str, int] | None = None
    triangle_steps:     int | None   = None

    # ── real-hardware behavior switches ─────────────────────────────────
    # "nes" (2A03/VRC6/2A03+FDS), "gb" (DMG), or "spc" (SPC700) - turns on
    # register-quantized frequencies, real LFSR noise, hardware-stepped
    # envelopes, etc. in synth.py/waveforms.py. None = the old freeform
    # generic synthesis (used when the user picks "no chip").
    hw_family: str | None = None


_2A03_WAVES = frozenset({"pulse12", "pulse25", "square", "triangle", "noise"})

CHIP_PROFILES: dict[str, ChipProfile] = {

    # ── NES RP2A03 APU ────────────────────────────────────────────────────────
    "2a03": ChipProfile(
        name="2a03", label="NES 2A03",
        supported_waves=_2A03_WAVES,
        wave_remap={
            "saw": "pulse25", "half_saw": "pulse12", "ring_mod": "pulse25",
            "pwm": "square", "additive": "triangle",
            "sine": "triangle", "fm_bell": "triangle", "supersaw": "pulse25"
        },
        channel_wave_force={9: "noise"},
        max_channels=5,
        attack=0.002, release=0.010,
        triangle_fixed_vel=1.0,
        freq_min=27.3, freq_max=12429.0,
        wave_voice_limit={"__pulse__": 2, "triangle": 1, "noise": 1, "dmc": 1},
        triangle_steps=32,
        hw_family="nes",
    ),

    "vrc6": ChipProfile(
        name="vrc6", label="Konami VRC6",
        supported_waves=_2A03_WAVES | frozenset({"saw"}),
        wave_remap={
            "half_saw": "saw", "ring_mod": "saw", "pwm": "pulse25",
            "additive": "triangle",
            "sine": "triangle", "fm_bell": "triangle", "supersaw": "saw"
        },
        channel_wave_force={9: "noise"},
        max_channels=8,
        attack=0.002, release=0.020,
        triangle_fixed_vel=1.0,
        freq_min=27.3, freq_max=16000.0,
        wave_voice_limit={"__pulse__": 4, "triangle": 1, "noise": 1, "dmc": 1, "saw": 1},
        triangle_steps=32,
        hw_family="nes",
    ),

    "2a03fds": ChipProfile(
        name="2a03fds", label="NES 2A03 + FDS",
        supported_waves=_2A03_WAVES | frozenset({"additive"}),
        wave_remap={
            "saw": "pulse25", "half_saw": "pulse12", "supersaw": "pulse25",
            "ring_mod": "additive",  # FDS modulation table ≈ wavetable FM
            "pwm": "square",
            "sine": "triangle",
            "fm_bell": "additive",   # FDS wavetable channel can approximate a bell shape
        },
        channel_wave_force={9: "noise"},
        max_channels=6,
        attack=0.002, release=0.020,
        triangle_fixed_vel=1.0,
        freq_min=27.3, freq_max=12429.0,
        wave_voice_limit={"__pulse__": 2, "triangle": 1, "noise": 1, "dmc": 1, "additive": 1},
        triangle_steps=32,
        hw_family="nes",
    ),

    "spc700": ChipProfile(
        name="spc700", label="SNES SPC700",
        supported_waves=ALL_WAVES,  # sample-based: anything goes
        wave_remap={},
        channel_wave_force={9: "noise"},
        max_channels=8,
        attack=0.008, release=0.150,
        triangle_fixed_vel=None,
        freq_min=14.0, freq_max=16000.0,
        lowpass_hz=14000.0,  # Gaussian interpolation roll-off approximation
        wave_voice_limit=None,
        triangle_steps=None,
        hw_family="spc",
    ),

    "dmg": ChipProfile(
        name="dmg", label="Game Boy DMG",
        supported_waves=frozenset({"pulse12", "pulse25", "square", "additive", "noise"}),
        wave_remap={
            "triangle": "additive",  # wavetable channel can hold a triangle table
            "saw": "pulse25", "half_saw": "pulse12", "ring_mod": "square", "pwm": "pulse25",
            "sine": "additive", "fm_bell": "additive", "supersaw": "pulse25"
        },
        channel_wave_force={9: "noise"},
        max_channels=4,
        attack=0.001, release=0.008,
        triangle_fixed_vel=None,
        freq_min=65.0, freq_max=6000.0,
        wave_voice_limit={"__pulse__": 2, "additive": 1, "noise": 1},
        triangle_steps=32,
        hw_family="gb",
    ),
}

PULSE_VARIANTS = frozenset({"square", "pulse25", "pulse12"})


def quantize_frequency(chip: ChipProfile | None, wave_type: str, freq: float) -> float:
    """Snap `freq` (Hz) to the nearest pitch the real chip's frequency
    divider can actually produce.

    This is the single biggest lever for "sounds like it's really running
    on the hardware": every one of these chips tunes its oscillators with a
    fixed-point N-bit period register driving an integer clock divider, so
    they can *only* land on whatever discrete frequency that division works
    out to - never an arbitrary continuous Hz value the way a software synth
    can. That's exactly why real NES/GB music has its own characteristic
    "slightly off" microtonal wobble in the low register: A4 might be spot
    on, but the note a fifth below it can be several cents flat because nothing
    in the divider table lands closer. Skipping this step is why a lot of
    "NES-style" synths sound like a synth doing NES *timbres* instead of an
    actual 2A03: continuous pitch is something the real chip cannot do.

    Sources: nesdev.org/wiki/APU_Pulse, APU_Triangle, VRC6_audio, FDS_audio;
    gbdev.io/pandocs/Audio_Registers.html.
    """
    if chip is None or chip.hw_family is None or freq <= 0:
        return freq

    if chip.hw_family == "nes":
        if wave_type == "triangle":
            divisor, bits = NES_TRIANGLE_DIVISOR, NES_PERIOD_BITS
        elif wave_type == "saw" and chip.name == "vrc6":
            divisor, bits = VRC6_SAW_DIVISOR, VRC6_PERIOD_BITS
        elif wave_type in PULSE_VARIANTS:
            divisor, bits = NES_PULSE_DIVISOR, NES_PERIOD_BITS
        elif wave_type == "additive" and chip.name == "2a03fds":
            # FDS wavetable channel: Hz = fCPU * (pitch / 65536), 12-bit pitch
            pitch = round(freq * FDS_PITCH_SCALE / NES_CPU_CLOCK_NTSC)
            pitch = max(1, min(pitch, (1 << FDS_PITCH_BITS) - 1))
            return NES_CPU_CLOCK_NTSC * pitch / FDS_PITCH_SCALE
        else:
            return freq  # noise handled separately (it's not a "pitch" in the normal sense)
        period = round(NES_CPU_CLOCK_NTSC / (divisor * freq) - 1)
        period = max(0, min(period, (1 << bits) - 1))
        return NES_CPU_CLOCK_NTSC / (divisor * (period + 1))

    if chip.hw_family == "gb":
        if wave_type == "additive":       # channel 3 wavetable (triangle remap)
            divisor = GB_WAVE_DIVISOR
        elif wave_type in PULSE_VARIANTS:
            divisor = GB_PULSE_DIVISOR
        else:
            return freq
        x = round(2048 - GB_CPU_CLOCK / (divisor * freq))
        x = max(0, min(x, (1 << GB_PERIOD_BITS) - 1))
        return GB_CPU_CLOCK / (divisor * (2048 - x))

    return freq


def wave_pool_key(chip: ChipProfile, wt: str) -> str:
    if chip.wave_voice_limit and wt in PULSE_VARIANTS and "__pulse__" in chip.wave_voice_limit:
        return "__pulse__"
    return wt


def assign_voice_slots(intervals: list, chip: ChipProfile | None):
    """Assign each NoteInterval a virtual hardware voice slot, respecting the
    chip's per-wave voice pool caps (e.g. only 2 pulse channels on NES).
    Returns (remapped_intervals, used_voice_indices).

    When every slot in a pool is busy and a new note needs one, the
    soonest-ending occupant is stolen - and that occupant's own
    NoteInterval is truncated to end exactly when the stealing note starts.
    Real hardware only has as many oscillators as it has oscillators: a
    third note on a 2-voice pulse pool doesn't ring out under the new note,
    it gets physically cut off by it. Without this truncation the voice
    pool assignment was cosmetic - render_audio mixes by absolute time
    regardless of channel, so a "stolen" note kept sounding in full and
    just quietly overlapped whatever stole its slot instead of actually
    being restricted to the chip's real polyphony.
    """
    if chip is None:
        return intervals, {iv.channel for iv in intervals}

    intervals = sorted(intervals, key=lambda iv: iv.start_time)
    max_voices = chip.max_channels or None

    if chip.wave_voice_limit:
        # Each slot holds (end_time, occupant_iv_or_None).
        pool_slots: dict[str, list[list]] = {}
        seen: set[str] = set()
        for wt, cap in chip.wave_voice_limit.items():
            key = wave_pool_key(chip, wt)
            if key not in seen:
                pool_slots[key] = [[0.0, None] for _ in range(cap)]
                seen.add(key)
        fallback_pool: list[list] = []
    else:
        pool_slots = {}
        fallback_pool = [[0.0, None] for _ in range(max_voices or 64)]

    pool_base: dict[str, int] = {}
    next_slot = 0
    for key, slots in pool_slots.items():
        pool_base[key] = next_slot
        next_slot += len(slots)

    remapped = []
    for iv in intervals:
        wt = iv.wave_type
        if pool_slots:
            key = wave_pool_key(chip, wt)
            if key not in pool_slots:
                continue
            slots, base = pool_slots[key], pool_base[key]
        else:
            slots, base = fallback_pool, 0

        free = [i for i in range(len(slots)) if slots[i][0] <= iv.start_time]
        if free:
            best = min(free, key=lambda i: slots[i][0])
        else:
            # No free voice: steal the *least important* occupant rather
            # than whichever one simply happens to end soonest. Picking by
            # soonest-end alone makes the stolen voice hop unpredictably
            # from note to note as new notes arrive, so instead of one
            # clean cutoff you hear a scatter of little truncations across
            # several voices. Priority instead mirrors how real
            # synths/samplers pick a steal target: quietest note loses
            # first (least audible impact), and among equally-quiet notes
            # the oldest one loses (it's already been heard, so cutting it
            # reads as natural decay rather than an interruption). This
            # keeps loud, freshly-triggered notes essentially safe from
            # being stolen, which is what makes the swapping feel stable
            # instead of erratic.
            best = min(
                range(len(slots)),
                key=lambda i: (slots[i][1].velocity, slots[i][1].start_time)
                if slots[i][1] is not None
                else (-1.0, -1.0),
            )
            occupant = slots[best][1]
            if occupant is not None and occupant.end_time > iv.start_time:
                occupant.end_time = iv.start_time

        new_iv = iv.__class__(
            iv.start_time, iv.end_time, base + best, iv.note, iv.velocity, iv.wave_type,
            retrigger=getattr(iv, "retrigger", False),
        )
        slots[best] = [new_iv.end_time, new_iv]
        remapped.append(new_iv)

    used_voices = {iv.channel for iv in remapped}
    if pool_slots:
        used_voices |= set(range(next_slot))  # show every hardware slot, even silent ones

    return remapped, used_voices