"""
midchip.synth | turns noteintervals into PCM, aka "the big one"
----------
i would write a description here
if i wasn't lazy

k thx for understanding (or not) :P

"""
# TODO: actually write midchip.synth's docstring

from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from .constants import (
    SAMPLE_RATE, ATTACK, RELEASE, RETRIGGER_ATTACK, WAVE_LOUDNESS,
    HF_HARSH, HF_THRESH, HF_ALPHA, HF_FLOOR,
    PRESENCE_CENTER, PRESENCE_WIDTH, PRESENCE_DEPTH,
    GM_DRUM_MAP, DRUM_ATTACK, DRUM_RELEASE, DRUM_LOUDNESS,
    VIBRATO_RATE_HZ, VIBRATO_DEPTH_SEMITONES, VIBRATO_DELAY, VIBRATO_RAMP,
    VIBRATO_REF_HZ, VIBRATO_REGISTER_EXP, VIBRATO_SCALE_MIN, VIBRATO_SCALE_MAX,
    PAN_DEFAULT,
    REVERB_COMB_DELAYS_MS, REVERB_ALLPASS_DELAYS_MS, REVERB_ALLPASS_GAIN,
    REVERB_DECAY, REVERB_STEREO_SPREAD_MS, REVERB_MIX, REVERB_TAIL_SECONDS,
    HW_VOLUME_STEPS, NES_ENVELOPE_HZ, GB_ENVELOPE_HZ, GB_WAVE_VOLUME_LEVELS,
    SPC_ATTACK_TIME, SPC_DECAY_TIME, SPC_SUSTAIN_LVL, SPC_RELEASE_TIME,
    NES_DRUM_NOISE_PRESETS, GB_DRUM_NOISE_PRESETS,
)
from . import ui
from .waveforms import (
    generate as gen_wave, generate_drum, osc_triangle,
    osc_nes_noise, osc_gb_noise, osc_vrc6_saw, osc_fds_wave, osc_gb_wave,
)
from .chips import ChipProfile, quantize_frequency
from .midi_parser import NoteInterval


# if a midi file is below this many notes, it would be stupid to spin up
# a whole process pool for a short render; so for small files we stay single-process.
_MULTIPROCESS_NOTE_THRESHOLD = 300


def hf_gain(freq: float) -> float:
    # rolloff for wave types that get harsher at high pitch
    if freq <= HF_THRESH:
        return 1.0
    gain = (HF_THRESH / freq) ** HF_ALPHA
    return max(gain, HF_FLOOR)


def presence_gain(freq: float) -> float:
    # extra gain around ~2-4kHz alarm band, independent of wave type
    # basically no beeping.
    # same reason smoke detectors or microwaves use tones there.
    # da more you know!!11!1!1!!!
    x = (freq - PRESENCE_CENTER) / PRESENCE_WIDTH
    dip = PRESENCE_DEPTH * math.exp(-0.5 * x * x)
    return 1.0 - dip


def midi_to_freq(note: int, bend: float = 0.0) -> float:
    return 440.0 * (2 ** ((note - 69 + bend) / 12))


def _envelope(w: np.ndarray, attack: float, release: float,
              stepped_release_hz: float | None = None) -> np.ndarray:
    n = len(w)
    al = min(int(SAMPLE_RATE * attack), n)
    rl = min(int(SAMPLE_RATE * release), n - al)
    e = np.ones(n)
    if al > 0:
        e[:al] = np.linspace(0, 1, al)
    if rl > 0:
        if stepped_release_hz:
            # real 2A03/DMG volume envelopes are a literal 4-bit (16-level)
            # up/down counter clocked by the APU frame sequencer (240 Hz on
            # NES, 64 Hz on Game Boy) - there's no such thing as a smooth
            # fade on the actual silicon, just a discrete staircase.
            # (nesdev.org/wiki/APU_Envelope, gbdev.io/pandocs/Audio_details)
            samples_per_step = max(1, int(SAMPLE_RATE / stepped_release_hz))
            n_steps = rl // samples_per_step + 1
            rel = np.ones(rl)
            for i in range(n_steps):
                s = i * samples_per_step
                if s >= rl:
                    break
                e2 = min(s + samples_per_step, rl)
                rel[s:e2] = max(0.0, 1.0 - i / HW_VOLUME_STEPS)
            e[-rl:] = rel
        else:
            e[-rl:] = np.linspace(1, 0, rl)
    return w * e


def _spc_envelope(w: np.ndarray, attack: float, decay: float,
                   sustain_level: float, release: float) -> np.ndarray:
    """S-DSP ADSR: attack is LINEAR ramp-to-full; decay is an EXPONENTIAL
    slide from full down to the sustain level; release is a further
    EXPONENTIAL slide toward silence once the note ends. Real hardware
    drives this off a 32-entry rate/period table and the actual curve
    shape differs slightly per rate, but linear-attack /
    exponential-decay-and-release is the defining, audible shape of every
    SPC700 instrument envelope (snes.nesdev.org/wiki/DSP_envelopes).
    """
    n = len(w)
    al = min(int(SAMPLE_RATE * attack), n)
    dl = min(int(SAMPLE_RATE * decay), max(0, n - al))
    rl = min(int(SAMPLE_RATE * release), max(0, n - al - dl))
    sl = max(0, n - al - dl - rl)
    env = np.ones(n)
    if al > 0:
        env[:al] = np.linspace(0.0, 1.0, al)
    if dl > 0:
        sustain_level = min(max(sustain_level, 1e-3), 1.0)
        i = np.arange(dl)
        env[al:al + dl] = sustain_level + (1.0 - sustain_level) * (
            (sustain_level) ** (i / max(dl - 1, 1))
        )
    sustain_val = env[al + dl - 1] if dl > 0 else 1.0
    if sl > 0:
        env[al + dl:al + dl + sl] = sustain_val
    if rl > 0:
        i = np.arange(rl)
        env[al + dl + sl:] = sustain_val * (0.0035 ** (i / max(rl - 1, 1)))
    return w * env


def _generate_wave(wave_type: str, t_gen: np.ndarray, freq: float,
                    chip: "ChipProfile | None", triangle_steps: int | None) -> np.ndarray:
    """Pick a hardware-accurate oscillator when we know which real chip
    we're targeting; otherwise fall back to the generic band-limited
    waveform table (used for "no chip" freeform synthesis)."""
    fam = chip.hw_family if chip is not None else None

    if fam == "nes":
        if wave_type == "triangle":
            # raw, un-bandlimited 32-step staircase: real 2A03/VRC6/FDS
            # triangle hardware does NOT anti-alias itself, which is exactly
            # why it gets that characteristic gritty/aliased buzz up high
            # (famous e.g. in Mega Man 2's high triangle notes).
            return _osc_triangle_raw(t_gen, freq, triangle_steps)
        if wave_type == "saw" and chip.name == "vrc6":
            return osc_vrc6_saw(t_gen, freq)
        if wave_type == "additive" and chip.name == "2a03fds":
            return osc_fds_wave(t_gen, freq)
        if wave_type == "noise":
            return osc_nes_noise(t_gen, freq, mode="long")

    if fam == "gb":
        if wave_type == "additive":
            return osc_gb_wave(t_gen, freq)
        if wave_type == "noise":
            return osc_gb_noise(t_gen, freq, narrow=False)

    return gen_wave(wave_type, t_gen, freq, triangle_steps=triangle_steps)


def _osc_triangle_raw(t_gen: np.ndarray, freq: float, triangle_steps: int | None) -> np.ndarray:
    return osc_triangle(t_gen, freq, steps=triangle_steps, bandlimit=False)


def _generate_drum_wave(drum_category: str, t: np.ndarray, chip: "ChipProfile | None") -> np.ndarray:
    """Real NES/Famicom (and Game Boy) chiptunes don't have a "drum kit" -
    every percussion sound (kick, snare, hats, toms, cymbals) is the SAME
    single noise channel, just retuned to a different LFSR period/mode and
    given a different envelope shape. So on chips that only have that one
    noise channel, route GM percussion through the real hardware noise
    generator using representative period/mode presets per drum category,
    instead of a synthesized generic drum kit. (Chips with real sample
    playback - i.e. none modeled here without actual ROM data - or "no
    chip" freeform mode keep the synthesized kit, which is the closest
    stand-in without real drum samples.)
    """
    fam = chip.hw_family if chip is not None else None
    if fam == "nes":
        target_hz, mode = NES_DRUM_NOISE_PRESETS.get(drum_category, NES_DRUM_NOISE_PRESETS["default"])
        return osc_nes_noise(t, target_hz, mode=mode)
    if fam == "gb":
        target_hz, narrow = GB_DRUM_NOISE_PRESETS.get(drum_category, GB_DRUM_NOISE_PRESETS["default"])
        return osc_gb_noise(t, target_hz, narrow=narrow)
    return generate_drum(drum_category, t)


def _vibrato_ramp(t: np.ndarray) -> np.ndarray:
    # 0 until delay, then eases up to 1 over VIBRATO_RAMP seconds
    return np.clip((t - VIBRATO_DELAY) / max(VIBRATO_RAMP, 1e-6), 0.0, 1.0)


def _vibrato_depth_semitones(freq: float, depth_semitones: float) -> float:
    # fixed semitone swings don't feel like a fixed amount of vibrato
    # all around the keyboard; down low it sweeps a wider freq. range
    # for the ear to track, while way up high the same swing gets crowded
    # by the note's harmonics.

    # scale the configured depth by register so it reads as roughly
    # instead of applying ONE number to every note
    scale = (freq / VIBRATO_REF_HZ) ** VIBRATO_REGISTER_EXP
    scale = min(max(scale, VIBRATO_SCALE_MIN), VIBRATO_SCALE_MAX)
    return depth_semitones * scale


def _pitch_ratio_curve(
    t: np.ndarray,
    note_start_time: float,
    bend_times: np.ndarray | None,
    bend_semitones: np.ndarray | None,
    vibrato: bool,
    freq: float = VIBRATO_REF_HZ,
    vibrato_rate: float = VIBRATO_RATE_HZ,
    vibrato_depth: float = VIBRATO_DEPTH_SEMITONES,
) -> np.ndarray:
    """per-sample freq. multiplier for pitch-bend n shit"""
    semitone_shift = np.zeros_like(t)

    if bend_times is not None and len(bend_times) > 0:
        # a pitch wheel is a step control; holds whatever value it was last set to and only changes when
        # a new message arrives.

        # during most songs with pitch wheel bends, those messages arrive every ~10-15ms, so treating
        # consecutive messages as connected by a straight line reads as smooth and is pretty much right
        # but between gestures, once the wheel returns to center, there are no messages for however long,
        # and is linearly interpolating across the gap (wow big words) that makes a slow fake glide
        # towards whatever the next gesture turns out to be; detuning every note in-between.

        # zero-order hold (step to most recent message; 0.0
        # before the first one, aka what we're doing here),
        # reconstructs what the wheel actually was INSTEAD of smoothing across silence.

        # phew that was a lot. hope you understand that and read the whole thing
        # you did read all that, right?
        # ... RIGHT?
        abs_t = note_start_time + t
        idx = np.searchsorted(bend_times, abs_t, side="right") - 1
        shift = np.where(idx < 0, 0.0, bend_semitones[np.clip(idx, 0, len(bend_semitones) - 1)])
        semitone_shift = semitone_shift + shift

    if vibrato:
        ramp = _vibrato_ramp(t)
        depth = _vibrato_depth_semitones(freq, vibrato_depth)
        semitone_shift = semitone_shift + (
            depth * ramp * np.sin(2 * np.pi * vibrato_rate * t)
        )

    return 2.0 ** (semitone_shift / 12.0)


def render_note(
    freq: float, dur: float, wave_type: str, vel: float, *,
    rms_fix: bool = True,
    attack: float = ATTACK, release: float = RELEASE,
    triangle_steps: int | None = None,
    drum_category: str | None = None,
    note_start_time: float = 0.0,
    bend_times: np.ndarray | None = None,
    bend_semitones: np.ndarray | None = None,
    vibrato: bool = False,
    vibrato_rate: float = VIBRATO_RATE_HZ,
    vibrato_depth: float = VIBRATO_DEPTH_SEMITONES,
    unison_voices: int = 1,
    unison_detune_cents: float = 0.0,
    chip: "ChipProfile | None" = None,
) -> np.ndarray:
    l = max(0.01, dur)
    t = np.linspace(0, l, int(SAMPLE_RATE * l), False)
    if len(t) == 0:
        t = np.zeros(1)

    if drum_category is None and unison_voices > 1 and unison_detune_cents > 0:
        mid = (unison_voices - 1) / 2.0
        acc = np.zeros_like(t)
        for i in range(unison_voices):
            cents = (i - mid) * (unison_detune_cents / max(unison_voices - 1, 1)) * 2.0
            detuned_freq = freq * (2.0 ** (cents / 1200.0))
            acc = acc + render_note(
                detuned_freq, dur, wave_type, 1.0,
                rms_fix=False, attack=attack, release=release,
                triangle_steps=triangle_steps, drum_category=None,
                note_start_time=note_start_time,
                bend_times=bend_times, bend_semitones=bend_semitones,
                vibrato=vibrato, vibrato_rate=vibrato_rate, vibrato_depth=vibrato_depth,
                unison_voices=1, chip=chip,
            )
        w = acc / unison_voices
        if rms_fix:
            rms = np.sqrt(np.mean(w * w))
            if rms > 0:
                w = w / rms
        hf = hf_gain(freq) if wave_type in HF_HARSH else 1.0
        presence = presence_gain(freq)
        loudness = WAVE_LOUDNESS.get(wave_type, 1.0)
        return w * vel * loudness * hf * presence

    if drum_category is not None:
        w = _generate_drum_wave(drum_category, t, chip)
        w = _envelope(w, attack, release)
        if rms_fix:
            rms = np.sqrt(np.mean(w * w))
            if rms > 0:
                w = w / rms
        loudness = DRUM_LOUDNESS.get(drum_category, DRUM_LOUDNESS["default"])
        return w * vel * loudness

    t_gen = t
    has_bend = bend_times is not None and len(bend_times) > 0
    if has_bend or vibrato:
        ratio = _pitch_ratio_curve(
            t, note_start_time, bend_times, bend_semitones, vibrato, freq=freq,
            vibrato_rate=vibrato_rate, vibrato_depth=vibrato_depth,
        )
        t_gen = np.cumsum(ratio) / SAMPLE_RATE

    w = _generate_wave(wave_type, t_gen, freq, chip, triangle_steps)

    fam = chip.hw_family if chip is not None else None
    if fam == "spc":
        # real SPC700 instrument shaping: linear attack, exponential decay
        # to a sustain level, exponential release - not a symmetric fade.
        w = _spc_envelope(w, SPC_ATTACK_TIME, SPC_DECAY_TIME, SPC_SUSTAIN_LVL,
                           release if release > 0 else SPC_RELEASE_TIME)
    elif fam == "nes" and wave_type != "triangle":
        # 2A03/VRC6/FDS pulse+noise (+VRC6 saw) volume is a real 4-bit
        # hardware envelope counter, not a smooth fade - the triangle
        # channel has no volume envelope at all (see triangle_fixed_vel),
        # so it keeps the plain click-avoidance ramp instead.
        w = _envelope(w, attack, release, stepped_release_hz=NES_ENVELOPE_HZ)
    elif fam == "gb" and wave_type != "additive":
        # DMG pulse/noise envelope; the wave channel (mapped from
        # "additive") has no envelope hardware either - only a volume
        # right-shift set at trigger time (see the wave-channel velocity
        # quantization in _synthesize_note).
        w = _envelope(w, attack, release, stepped_release_hz=GB_ENVELOPE_HZ)
    else:
        w = _envelope(w, attack, release)

    if rms_fix:
        rms = np.sqrt(np.mean(w * w))
        if rms > 0:
            w = w / rms

    hf = hf_gain(freq) if wave_type in HF_HARSH else 1.0
    presence = presence_gain(freq)
    loudness = WAVE_LOUDNESS.get(wave_type, 1.0)
    return w * vel * loudness * hf * presence


def _comb_filter(x: np.ndarray, delay: int, feedback: float) -> np.ndarray:
    from scipy.signal import lfilter
    y = np.empty_like(x)
    for p in range(delay):
        y[p::delay] = lfilter([1.0], [1.0, -feedback], x[p::delay])
    return y


def _allpass_filter(x: np.ndarray, delay: int, gain: float) -> np.ndarray:
    # y[n] = -gain*x[n] + x[n-delay] + gain*y[n-delay]       ( i don't understand this shit )
    from scipy.signal import lfilter
    y = np.empty_like(x)
    for p in range(delay):
        y[p::delay] = lfilter([-gain, 1.0], [1.0, -gain], x[p::delay])
    return y


def _chorus_modulate(x: np.ndarray, rate: int, depth_ms: float, rate_hz: float, phase: float) -> np.ndarray:
    # Oh, you wanna know what's happening here?
    # Answer: I have no fucking idea
    n = len(x)
    if n == 0:
        return x
    t = np.arange(n) / rate
    delay_samples = (depth_ms / 1000.0) * rate * (0.5 + 0.5 * np.sin(2 * np.pi * rate_hz * t + phase))
    src_idx = np.clip(np.arange(n) - delay_samples, 0, n - 1)
    return np.interp(src_idx, np.arange(n), x)


def _reverb_channel(x: np.ndarray, rate: int, offset_ms: float, decay: float, chorus_phase: float = 0.0) -> np.ndarray:
    wet = np.zeros_like(x)
    for delay_ms in REVERB_COMB_DELAYS_MS:
        d = max(1, int(round((delay_ms + offset_ms) * rate / 1000.0)))
        wet = wet + _comb_filter(x, d, decay)
    wet = wet / len(REVERB_COMB_DELAYS_MS)
    for delay_ms in REVERB_ALLPASS_DELAYS_MS:
        d = max(1, int(round((delay_ms + offset_ms) * rate / 1000.0)))
        wet = _allpass_filter(wet, d, REVERB_ALLPASS_GAIN)
    wet = _chorus_modulate(wet, rate, depth_ms=2.5, rate_hz=0.27, phase=chorus_phase)
    return wet


def apply_reverb(
    out: np.ndarray, rate: int = SAMPLE_RATE,
    mix: float = REVERB_MIX, decay: float = REVERB_DECAY,
) -> np.ndarray:
    # I CAST MAGIC REVERB BULLSHIT, I GUESS

    # this blends schroder/moorer-style reverb tail into `out`.
    # all oscs render bone dry, so *theoretically* it should sound less
    # like a dogpile of instruments, however I haven't done much
    # testing without reverb; so that needs some fact-checking..
    # `mix` is the wet/dry blend (0 = dry, 1 = fully wet) and `decay` is the
    # comb-filter feedback gain driving tail length (higher = longer tail;
    # values close to/above 1.0 can runaway, so keep it under ~0.95).
    try:
        import scipy  # noqa: F401
    except ImportError:
        ui.note("--reverb needs scipy, which isn't installed; skipping.")
        return out

    if out.ndim == 2:
        spread = REVERB_STEREO_SPREAD_MS / 2.0
        wet_l = _reverb_channel(out[:, 0], rate, -spread, decay, chorus_phase=0.0)
        wet_r = _reverb_channel(out[:, 1], rate, spread, decay, chorus_phase=math.pi / 2.0)
        wet = np.stack([wet_l, wet_r], axis=1)
    else:
        wet = _reverb_channel(out, rate, 0.0, decay)

    return out * (1.0 - mix) + wet * mix


def _synthesize_note(
    iv: NoteInterval, *,
    chip, note_attack: float, note_release: float,
    bend_arrays: dict, cc_state: dict,
    vibrato: bool, rms_fix: bool,
    unison_voices: int, unison_detune_cents: float,
    vibrato_rate: float = VIBRATO_RATE_HZ,
    vibrato_depth: float = VIBRATO_DEPTH_SEMITONES,
) -> tuple[float, np.ndarray, float]:
    gain = 1.0
    pan = PAN_DEFAULT
    state = cc_state.get(iv.channel)
    if state is not None:
        times, vol_state, exp_state, pan_state = state
        idx = int(np.searchsorted(times, iv.start_time, side="right")) - 1
        if idx >= 0:
            gain *= float(vol_state[idx]) * float(exp_state[idx])
            pan = float(pan_state[idx])

    vel = iv.velocity * gain
    if chip is not None and chip.triangle_fixed_vel is not None and iv.wave_type == "triangle":
        vel = chip.triangle_fixed_vel * gain
    elif chip is not None and chip.hw_family == "gb" and iv.wave_type == "additive":
        # DMG channel 3's "volume" is a hardware right-shift of the 4-bit
        # wave sample - only 4 discrete output levels exist (mute/100%/50%/
        # 25%, NR32). snap to whichever of those the note's velocity is
        # closest to instead of a continuously variable gain.
        vel = min(GB_WAVE_VOLUME_LEVELS, key=lambda lv: abs(lv - vel))

    drum_category = (
        GM_DRUM_MAP.get(iv.note) if iv.wave_type == "noise" and iv.note in GM_DRUM_MAP else None
    )

    if drum_category is not None:
        d_attack = DRUM_ATTACK.get(drum_category, DRUM_ATTACK["default"])
        d_release = DRUM_RELEASE.get(drum_category, DRUM_RELEASE["default"])
        # drum tails ring out on their own; they shouldn't get truncated
        # just because the MIDI note-off arrived quickly, so the render
        # buffer is at least as long as the category's own envelope
        dur = max(iv.end_time - iv.start_time, d_attack + d_release)
    else:
        d_attack, d_release = note_attack, note_release
        if getattr(iv, "retrigger", False):
            # retriggered note, aka when a note is retriggered before note-off
            d_attack = min(d_attack, RETRIGGER_ATTACK)
        dur = iv.end_time - iv.start_time

    bend_t, bend_s = bend_arrays.get(iv.channel, (None, None))

    base_freq = midi_to_freq(iv.note)
    if chip is not None and drum_category is None:
        # snap to whatever discrete pitch the chip's real frequency-divider
        # register can actually produce (see chips.quantize_frequency) -
        # pitch bend/vibrato are then layered on top of that as a
        # continuous approximation of further register rewrites.
        base_freq = quantize_frequency(chip, iv.wave_type, base_freq)

    wave = render_note(
        base_freq, dur, iv.wave_type, vel,
        rms_fix=rms_fix, attack=d_attack, release=d_release,
        triangle_steps=chip.triangle_steps if chip else None,
        drum_category=drum_category,
        note_start_time=iv.start_time,
        bend_times=bend_t, bend_semitones=bend_s,
        vibrato=vibrato, vibrato_rate=vibrato_rate, vibrato_depth=vibrato_depth,
        unison_voices=unison_voices, unison_detune_cents=unison_detune_cents,
        chip=chip,
    )
    return iv.start_time, wave, pan


def _render_chunk_worker(payload):
    (chunk, chip, note_attack, note_release, bend_arrays, cc_state,
     vibrato, rms_fix, unison_voices, unison_detune_cents,
     vibrato_rate, vibrato_depth) = payload
    return [
        _synthesize_note(
            iv, chip=chip, note_attack=note_attack, note_release=note_release,
            bend_arrays=bend_arrays, cc_state=cc_state, vibrato=vibrato,
            rms_fix=rms_fix, unison_voices=unison_voices,
            unison_detune_cents=unison_detune_cents,
            vibrato_rate=vibrato_rate, vibrato_depth=vibrato_depth,
        )
        for iv in chunk
    ]


def _mix_note(out: np.ndarray, start_time: float, wave: np.ndarray, pan: float,
              stereo: bool, rate: int, n_samples: int) -> None:
    s = int(start_time * rate)
    e = min(s + len(wave), n_samples)
    seg = wave[:e - s]
    if stereo:
        # equal-power pan law;
        #   both channels sit at ~0.707 at dead
        #   center rather than 1.0/1.0, so a centered signal doesn't come
        #   out louder than a hard-panned one just for being split evenly
        theta = pan * (math.pi / 2.0)
        out[s:e, 0] += seg * math.cos(theta)
        out[s:e, 1] += seg * math.sin(theta)
    else:
        out[s:e] += seg


def render_audio(
    intervals: list[NoteInterval],
    total_time: float,
    volume: float = 0.2,
    rate: int = SAMPLE_RATE,
    rms_fix: bool = True,
    cc_by_channel=None,
    bend_by_channel=None,
    vibrato: bool = False,
    chip: "ChipProfile | None" = None,
    progress_cb=None,
    stereo: bool = True,
    reverb: bool = False,
    unison_voices: int = 1,
    unison_detune_cents: float = 0.0,
    dither: bool = True,
    workers: int | None = None,
    seed: int | None = None,
    attack: float | None = None,
    release: float | None = None,
    reverb_mix: float = REVERB_MIX,
    reverb_decay: float = REVERB_DECAY,
    normalize_target: float = 0.35,
    limiter_threshold: float = 0.7,
    vibrato_rate: float = VIBRATO_RATE_HZ,
    vibrato_depth: float = VIBRATO_DEPTH_SEMITONES,
) -> np.ndarray:
    note_attack = attack if attack is not None else (chip.attack if chip else ATTACK)
    note_release = release if release is not None else (chip.release if chip else RELEASE)
    max_release = max(note_release, max(DRUM_RELEASE.values()))
    tail = REVERB_TAIL_SECONDS if reverb else 0.0
    n_samples = int((total_time + max_release + tail) * rate) + 1
    out = np.zeros((n_samples, 2)) if stereo else np.zeros(n_samples)
    total = len(intervals)
    bend_arrays: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    if bend_by_channel:
        for ch, events in bend_by_channel.items():
            if events:
                times = np.array([e[0] for e in events], dtype=float)
                semis = np.array([e[1] for e in events], dtype=float)
                bend_arrays[ch] = (times, semis)

    cc_state: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    if cc_by_channel:
        for ch, events in cc_by_channel.items():
            if not events:
                continue
            times = np.empty(len(events))
            vol_state = np.empty(len(events))
            exp_state = np.empty(len(events))
            pan_state = np.empty(len(events))
            last_vol = last_exp = 1.0
            last_pan = PAN_DEFAULT
            for i, (t_evt, ctrl, val) in enumerate(events):
                if ctrl == 7:
                    last_vol = val
                elif ctrl == 11:
                    last_exp = val
                elif ctrl == 10:
                    last_pan = val
                times[i] = t_evt
                vol_state[i] = last_vol
                exp_state[i] = last_exp
                pan_state[i] = last_pan
            cc_state[ch] = (times, vol_state, exp_state, pan_state)

    n_cpus = os.cpu_count() or 1
    n_workers = workers if workers is not None else min(n_cpus, 8)
    use_mp = n_workers > 1 and total >= _MULTIPROCESS_NOTE_THRESHOLD

    if use_mp:
        chunks = [intervals[i::n_workers] for i in range(n_workers)]
        chunks = [c for c in chunks if c]
        payloads = [
            (chunk, chip, note_attack, note_release, bend_arrays, cc_state,
             vibrato, rms_fix, unison_voices, unison_detune_cents,
             vibrato_rate, vibrato_depth)
            for chunk in chunks
        ]
        try:
            done = 0
            with ProcessPoolExecutor(max_workers=len(chunks)) as ex:
                for batch in ex.map(_render_chunk_worker, payloads):
                    for start_time, wave, pan in batch:
                        _mix_note(out, start_time, wave, pan, stereo, rate, n_samples)
                    done += len(batch)
                    if progress_cb:
                        progress_cb(done, total)
        except Exception as e:
            ui.note(f"multi-process rendering unavailable ({e}); "
                    "falling back to single-process rendering.")
            use_mp = False
            out[:] = 0

    if not use_mp:
        for i, iv in enumerate(intervals):
            if progress_cb and i % 50 == 0:
                progress_cb(i, total)
            start_time, wave, pan = _synthesize_note(
                iv, chip=chip, note_attack=note_attack, note_release=note_release,
                bend_arrays=bend_arrays, cc_state=cc_state, vibrato=vibrato,
                rms_fix=rms_fix, unison_voices=unison_voices,
                unison_detune_cents=unison_detune_cents,
                vibrato_rate=vibrato_rate, vibrato_depth=vibrato_depth,
            )
            _mix_note(out, start_time, wave, pan, stereo, rate, n_samples)

    if progress_cb:
        progress_cb(total, total)

    mx = np.max(np.abs(out))
    if mx > 1:
        out /= mx

    if chip is not None and chip.lowpass_hz is not None:
        try:
            from scipy.signal import butter, sosfilt
            sos = butter(4, chip.lowpass_hz, btype="low", fs=rate, output="sos")
            out = sosfilt(sos, out, axis=0)
        except ImportError:
            pass  # scipy not installed; skip chip lowpass approx.

    if reverb:
        out = apply_reverb(out, rate, mix=reverb_mix, decay=reverb_decay)

    # --- polyphony-aware loudness norm. -----------------------
    #     each note in render_note() is rms-normalized on it's own, so
    #     overall mix depends on how many notes are stacked at once-
    #     independent oscs. summed together (partially) cancel by phase, so
    #     so dense chords/multiple tracks come out quieter than simple melodies
    #     (even tho an occasional peak still reaches ceil.)
    #
    #     peak-based scale (seen above) doesn't fix that, it only ever engages when
    #     smth has *already* been clipped
    #
    #     instead, bring the whole render to a consistant loudness, then use TANH to
    #     tame peaks that gain pushes past 1.0, so peaks compress smoothly
    #     instead of clipping

    target_rms = normalize_target
    max_boost = 6.0
    current_rms = float(np.sqrt(np.mean(out * out))) if out.size else 0.0
    if current_rms > 1e-6:
        gain = min(max(target_rms / current_rms, 1.0), max_boost)
        out = out * gain

    threshold = limiter_threshold
    mag = np.abs(out)
    over = mag > threshold
    if np.any(over):
        span = 1.0 - threshold
        compressed_mag = threshold + span * np.tanh((mag[over] - threshold) / span)
        out[over] = np.sign(out[over]) * compressed_mag

    final = np.clip(out * volume, -1, 1) * 32767.0
    if dither:
        rng = np.random.default_rng(seed)
        dither_noise = (rng.uniform(-1.0, 1.0, final.shape) + rng.uniform(-1.0, 1.0, final.shape)) * 0.5
        final = np.clip(final + dither_noise, -32768, 32767)
    return final.astype(np.int16)