"""
midchip.waveforms | canonical oscillator implementations
----------
this is the big file where all wave shapes are defined- both the
audio renderer and oscilloscope delay call the same function here
to get the waves.

all osc_* functions take a time array `t` (seconds) and a frequency
`f` (Hz), and returns a same-shaped np.ndarray in roughly [-1, 1].

i know it LOOKS like I know what I'm doing here; but like most things
in this codebase, I'm just winging it and praying (i'm stoopid)
"""
from __future__ import annotations

import numpy as np

from .constants import (
    SAMPLE_RATE, NYQUIST, HF_THRESH,
    KICK_TONE_START_HZ, KICK_TONE_END_HZ, KICK_TONE_MIX, KICK_PITCH_DECAY,
)


# band-limit helper
def _polyblep(phase: np.ndarray, dt: float) -> np.ndarray:
    out = np.zeros_like(phase)
    m1 = phase < dt # samples near rising edge
    t1 = phase[m1] / dt # norm. to 0-1
    out[m1] = t1 + t1 - t1 * t1 - 1.0 # smooth rising edge
    m2 = phase > (1.0 - dt) # norm. to -1-0
    t2 = (phase[m2] - 1.0) / dt # smooth falling edge
    out[m2] = t2 * t2 + t2 + t2 + 1.0 # edge correction
    return out


def _phase(t: np.ndarray, f: float) -> np.ndarray:
    return (f * t) % 1.0


# oscillators
def osc_square(t: np.ndarray, f: float, duty: float = 0.5, bandlimit: bool = True) -> np.ndarray:
    ph = _phase(t, f)
    w = np.where(ph < duty, 1.0, -1.0).astype(float)
    if bandlimit and len(t) > 1:
        dt = f / SAMPLE_RATE # phase step/sample
        w = w + _polyblep(ph, dt) - _polyblep((ph - duty) % 1.0, dt) # smooth edges
    return w


def osc_saw(t: np.ndarray, f: float, bandlimit: bool = True) -> np.ndarray:
    ph = _phase(t, f)
    w = 2.0 * ph - 1.0
    if bandlimit and len(t) > 1:
        w = w - _polyblep(ph, f / SAMPLE_RATE)
    return w


def osc_triangle(t: np.ndarray, f: float, steps: int | None = None, bandlimit: bool = True) -> np.ndarray:
    if bandlimit and len(t) > 1:
        sq = osc_square(t, f, bandlimit=True) # square base
        tri = np.cumsum(sq) * (2.0 * f / SAMPLE_RATE) # integrate into tri
        tri -= tri.mean()
        pk = np.max(np.abs(tri))
        raw = tri / pk if pk > 0 else tri
    else:
        raw = 2 * np.abs(2 * (f * t - np.floor(f * t + 0.5))) - 1 # native tri
    if steps is not None:
        half = steps / 2 # quant. scale
        raw = np.floor(raw * half + 0.5) / half # stairstepped
    return raw


def osc_noise(n_samples: int) -> np.ndarray:
    return np.random.uniform(-1, 1, n_samples)


def osc_pulse25(t: np.ndarray, f: float, bandlimit: bool = True) -> np.ndarray:
    w = osc_square(t, f, duty=0.25, bandlimit=bandlimit) # 25% duty square
    return w - w.mean()


def osc_pulse12(t: np.ndarray, f: float, bandlimit: bool = True) -> np.ndarray:
    w = osc_square(t, f, duty=0.125, bandlimit=bandlimit) # 12.5% duty square
    return w - w.mean()


def osc_pwm(t, f, lfo_hz=5.0, depth=0.2, bandlimit=True):
    duty = 0.5 + depth * 0.5 * np.sin(2*np.pi*lfo_hz*t) # duty sweep
    return osc_square(t, f, duty=duty, bandlimit=bandlimit) # var-width. square


def osc_additive(t: np.ndarray, f: float) -> np.ndarray:
    w = np.sin(2 * np.pi * f * t) # fundamental
    denom = 1.0
    if 2 * f < NYQUIST: # 2nd harmonic
        w = w + 0.5 * np.sin(4 * np.pi * f * t)
        denom += 0.5
    if 4 * f < NYQUIST: # 4th harmonic
        w = w + 0.25 * np.sin(8 * np.pi * f * t)
        denom += 0.25
    return w / denom # normalize vol.


def osc_half_saw(t: np.ndarray, f: float, bandlimit: bool = True) -> np.ndarray:
    w = np.maximum(0.0, osc_saw(t, f, bandlimit=bandlimit)) # chop neg. half
    return w - w.mean() # remove dc offset


def osc_ring_mod(t: np.ndarray, f: float, ratio: float = 1.5) -> np.ndarray:
    return np.sin(2 * np.pi * f * t) * np.sin(2 * np.pi * f * ratio * t) # ¯\_(ツ)_/¯


def osc_sine(t: np.ndarray, f: float) -> np.ndarray:
    return np.sin(2 * np.pi * f * t)


def osc_supersaw(t: np.ndarray, f: float) -> np.ndarray:
    detunes = [-0.02, -0.01, 0.0, 0.01, 0.02]

    w = np.zeros_like(t)

    for d in detunes:
        w += osc_saw(t, f * (1.0 + d), bandlimit=False)

    w /= len(detunes)

    peak = np.max(np.abs(w))
    return w / peak if peak > 0 else w


def osc_fm_bell(t: np.ndarray, f: float, mod_ratio: float = 3.5, # note to self, fm_bell sucks anyways, mayb remove this shitty expirement
                decay_rate: float = 4.5) -> np.ndarray:
    span = t[-1] if len(t) and t[-1] > 0 else 1.0  # sound time/length
    aliasing_ok = f * mod_ratio < NYQUIST  # will mod stay below nyq. freq.?
    base_idx = 4.0 if aliasing_ok else 1.2  # strong FM str. if safe, weaker FM str. otherwise
    if f > HF_THRESH:
        base_idx *= max(0.3, (HF_THRESH / f) ** 0.5)  # high notes = less fm (cause of harshness)
    idx = base_idx * np.exp(-decay_rate * t / span)  # fm amnt. fade out
    return np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * mod_ratio * t))  # carrier sine wave, being phase-bent
                                                                                    # by another fucking sine wave


def _red_noise(n_samples: int) -> np.ndarray:
    r = np.cumsum(osc_noise(n_samples)) # HAHA CUMsum (i'm so fucking stupid)
    r = r - r.mean()
    pk = np.max(np.abs(r))
    return r / pk if pk > 0 else r


def _bright_noise(n_samples: int) -> np.ndarray:
    raw = osc_noise(n_samples + 1)
    hp = np.diff(raw)
    pk = np.max(np.abs(hp)) # use loudest sample
    return hp / pk if pk > 0 else hp


def osc_kick(t: np.ndarray) -> np.ndarray:
    n = len(t)
    if n == 0:
        return np.zeros(0) # nothing to make..
    freq_env = KICK_TONE_END_HZ + (KICK_TONE_START_HZ - KICK_TONE_END_HZ) * np.exp(
        -t / max(KICK_PITCH_DECAY, 1e-4)
    ) # pitch falls
    phase = np.cumsum(freq_env) / SAMPLE_RATE # freq -> phase
    tone = np.sin(2 * np.pi * phase)
    body = _red_noise(n)
    return KICK_TONE_MIX * tone + (1.0 - KICK_TONE_MIX) * body # mix tone/noise


def osc_snare(n_samples: int) -> np.ndarray:
    # body (red noise) + crack (bright noise)
    return 0.55 * _red_noise(n_samples) + 0.45 * _bright_noise(n_samples)


def osc_tom(n_samples: int) -> np.ndarray:
    # mostly low noise
    return 0.75 * _red_noise(n_samples) + 0.25 * osc_noise(n_samples)


def osc_hihat(n_samples: int) -> np.ndarray:
    return _bright_noise(n_samples)


def osc_cymbal(n_samples: int) -> np.ndarray:
    return _bright_noise(n_samples)


_DRUM_VOICES = {
    "kick":         lambda t: osc_kick(t),
    "snare":        lambda t: osc_snare(len(t)),
    "tom":          lambda t: osc_tom(len(t)),
    "hihat_closed": lambda t: osc_hihat(len(t)),
    "hihat_open":   lambda t: osc_hihat(len(t)),
    "cymbal":       lambda t: osc_cymbal(len(t)),
}


def generate_drum(category: str, t: np.ndarray) -> np.ndarray:
    fn = _DRUM_VOICES.get(category) # find drum gen.
    if fn is None:
        return osc_noise(len(t)) # fallback to noise
    return fn(t)


# dispatch table
_OSCILLATORS = {
    "square":   osc_square,
    "saw":      osc_saw,
    "triangle": osc_triangle,
    "pulse25":  osc_pulse25,
    "pulse12":  osc_pulse12,
    "pwm":      osc_pwm,
    "additive": osc_additive,
    "half_saw": osc_half_saw,
    "ring_mod": osc_ring_mod,
    "sine":     osc_sine,
    "fm_bell":  osc_fm_bell,
    "supersaw": osc_supersaw,
}


def generate(wave_type: str, t: np.ndarray, freq: float, *,
             triangle_steps: int | None = None, bandlimit: bool = True) -> np.ndarray:
    """generation entry point for waves"""
    if wave_type == "noise":
        return osc_noise(len(t))
    if wave_type == "triangle":
        return osc_triangle(t, freq, steps=triangle_steps, bandlimit=bandlimit)
    fn = _OSCILLATORS.get(wave_type)
    if fn is None: # square wave fallback
        return osc_square(t, freq, bandlimit=bandlimit)
    if wave_type in ("square", "saw", "pulse25", "pulse12", "half_saw"):
        return fn(t, freq, bandlimit=bandlimit)
    return fn(t, freq)