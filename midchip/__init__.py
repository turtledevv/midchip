"""
midchip | MIDI-to-chiptune core library.
----------
parses a MIDI file into note intervals, maps GM instruments to waves,
with retro chip support, etc.. read README for more info!
"""
from .constants import (
    SAMPLE_RATE, NYQUIST, MASTER_VOLUME, ATTACK, RELEASE, DISP_SAMPLES, FPS,
    WAVE_LOUDNESS, ALL_WAVES, WAVE_REPLACEMENTS, HF_HARSH,
)
from .waveforms import generate as generate_wave
from .gm_mapping import instrument_to_wave, resolve_wave_type
from .chips import ChipProfile, CHIP_PROFILES
from .midi_parser import NoteInterval, parse_intervals, LyricEvent, parse_lyrics
from .synth import render_audio, render_note, midi_to_freq, hf_gain, presence_gain
from .cli_common import add_common_args, parse_disabled, parse_substitutions, get_chip, ALL_CHANNELS
from . import ui

__all__ = [
    "SAMPLE_RATE", "NYQUIST", "MASTER_VOLUME", "ATTACK", "RELEASE", "DISP_SAMPLES", "FPS",
    "WAVE_LOUDNESS", "ALL_WAVES", "WAVE_REPLACEMENTS", "HF_HARSH",
    "generate_wave", "instrument_to_wave", "resolve_wave_type",
    "ChipProfile", "CHIP_PROFILES",
    "NoteInterval", "parse_intervals", "LyricEvent", "parse_lyrics",
    "render_audio", "render_note", "midi_to_freq", "hf_gain", "presence_gain",
    "add_common_args", "parse_disabled", "parse_substitutions", "get_chip", "ALL_CHANNELS",
    "ui",
]