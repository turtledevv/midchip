"""
midchip.playback | simple audio-out module for CLI
----------
needs sounddevice; this is only used for playing the audio
directly back from the CLI instead of using viz or exporting
"""
from __future__ import annotations

import numpy as np

from . import ui
from .constants import SAMPLE_RATE


def play(audio: np.ndarray, rate: int = SAMPLE_RATE, blocking: bool = True) -> None:
    """Play a rendered int16 PCM buffer out the default audio device."""
    try:
        import sounddevice as sd
    except (ImportError, OSError) as e:
        raise SystemExit(ui.error(
            "Playback needs the 'sounddevice' package and a working PortAudio "
            "install.\n  pip install sounddevice\n"
            "(On Linux you may also need: apt install libportaudio2)\n"
            "Or just use --output to render a .wav file instead."
        )) from e

    # sounddevice wants float32 in [-1, 1]; midchip renders int16 PCM.
    floats = (audio.astype(np.float32) / 32767.0).copy()
    sd.play(floats, samplerate=rate, blocking=blocking)
