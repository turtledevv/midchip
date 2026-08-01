"""
midchip.chips | sound chip profiles
----------
sound-chip profiles that restrict/remap synthesis to retro
hardware limitations!!
"""
from __future__ import annotations

from dataclasses import dataclass

from .constants import ATTACK, RELEASE, ALL_WAVES


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
    ),
}

PULSE_VARIANTS = frozenset({"square", "pulse25", "pulse12"})


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
            # No free voice: steal whichever occupant ends soonest, and
            # actually cut it off at the moment it gets stolen, rather than
            # leaving it to keep sounding underneath the note that took its
            # slot - that's the whole point of a hardware voice limit.
            best = min(range(len(slots)), key=lambda i: slots[i][0])
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