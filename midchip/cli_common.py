"""
midchip.cli_common | shared argparse pieces for CLI frontends.
----------
both midchip and midchip.viz need the same knobs/params, so they're
convinently defined here
"""
from __future__ import annotations

import argparse
import dataclasses

from . import ui
from .chips import ChipProfile, CHIP_PROFILES
from .constants import (
    ALL_WAVES, MASTER_VOLUME, ATTACK, RELEASE, REVERB_MIX, REVERB_DECAY,
    VIBRATO_RATE_HZ, VIBRATO_DEPTH_SEMITONES,
)

ALL_CHANNELS = -1

def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "midi_file",
        help="Path to the input .mid file",
    )
    parser.add_argument(
        "-c", "--chip", choices=sorted(CHIP_PROFILES), default=None, metavar="CHIP",
        help="Restrict synthesis to a retro sound chip's voices/waves. "
             f"Choices: {', '.join(sorted(CHIP_PROFILES))}",
    )
    parser.add_argument(
        "-L", "--no-chip-channel-limits", action="store_true",
        help="Ignore a --chip profile's channel/voice-pool caps (its "
             "max_channels and per-wave polyphony limits), while still "
             "using its wave set, remaps, and hardware quirks (register-"
             "quantized pitch, envelopes, etc). Every note gets its own "
             "voice instead of the oldest/quietest getting stolen when the "
             "chip's real hardware would've run out. No effect without "
             "--chip.",
    )
    parser.add_argument(
        "-d", "--disable", default="", metavar="WAVE,WAVE,...",
        help="Comma-separated wave types to disable; each falls back to the "
             f"nearest similar wave. Choices: {', '.join(sorted(ALL_WAVES))}",
    )
    parser.add_argument(
        "-s", "--substitute", default="", metavar="CH-WAVE-WAVE,...",
        help="Force one wave type to become another on specific channels, "
             "e.g. '1-triangle-saw' replaces every triangle-wave note on "
             "channel 1 with a saw wave. Channels are 1-16 (1-indexed, "
             "matching how DAWs/trackers number them, NOT MIDI's internal "
             "0-15). Either of the first two positions can be '*' as a "
             "wildcard: '*-triangle-saw' replaces every triangle note on "
             "every channel; '3-*-noise' replaces every wave on channel 3 "
             "with noise; '*-*-saw' replaces everything, everywhere. A "
             "specific channel/wave rule always wins over a wildcard one "
             "where both could apply. Comma-separate multiple rules, e.g. "
             "'1-triangle-saw,3-square-noise'. Applied after GM/chip wave "
             "assignment and before --disable's fallback chain, so a "
             "substituted wave that's also disabled still falls back "
             f"normally. Choices: {', '.join(sorted(ALL_WAVES))}",
    )
    parser.add_argument(
        "-V", "--volume", type=float, default=MASTER_VOLUME, metavar="0-1",
        help=f"Master output volume, 0.0-1.0 (default {MASTER_VOLUME})",
    )
    parser.add_argument(
        "-v", "--vibrato", action="store_true",
        help="Add synthesized vibrato to every sustained note (rate/depth/"
             "delay set in constants.py, depth nudged by register). Layers "
             "on top of any real pitch-bend automation already in the MIDI "
             "file, which is always applied regardless of this flag.",
    )
    parser.add_argument(
        "-g", "--vibrato-depth", type=float, default=VIBRATO_DEPTH_SEMITONES,
        metavar="SEMITONES",
        help=f"Peak pitch swing of --vibrato once fully ramped in, in "
             f"semitones (default {VIBRATO_DEPTH_SEMITONES}), measured at "
             "A4 - still scaled up/down by register the same as before. "
             "No effect without --vibrato.",
    )
    parser.add_argument(
        "-G", "--vibrato-rate", type=float, default=VIBRATO_RATE_HZ, metavar="HZ",
        help=f"Wobble speed of --vibrato in Hz (default {VIBRATO_RATE_HZ}). "
             "No effect without --vibrato.",
    )
    parser.add_argument(
        "-m", "--mono", action="store_true",
        help="Render in mono instead of stereo. Stereo (the default) pans "
             "each channel using the MIDI file's own CC10 pan messages "
             "(center if a channel never sends one); --mono disables that "
             "and sums everything to a single channel like older versions did.",
    )
    parser.add_argument(
        "-r", "--reverb", action="store_true",
        help="Add a Schroeder-style algorithmic reverb tail to the mix "
             "(needs scipy). Every oscillator renders bone dry otherwise; "
             "this gives dense arrangements some shared sense of space "
             "instead of every voice sitting right on top of the others.",
    )
    parser.add_argument(
        "-u", "--unison", type=int, default=1, metavar="N",
        help="Stack N slightly-detuned copies of each pitched voice for a "
             "thicker lead/pad sound (default 1 = off, single oscillator "
             "per note, unchanged from before this option existed). Use "
             "with --detune to set how far apart they're tuned.",
    )
    parser.add_argument(
        "-t", "--detune", type=float, default=8.0, metavar="CENTS",
        help="Total spread across the --unison voices, in cents (default "
             "8.0). Has no effect unless --unison is set above 1.",
    )
    parser.add_argument(
        "-w", "--workers", type=int, default=None, metavar="N",
        help="Number of worker processes for audio synthesis (default: "
             "up to 8, based on CPU count). Notes render independently of "
             "each other so this parallelizes cleanly; pass 1 to force "
             "single-process rendering.",
    )
    parser.add_argument(
        "-D", "--no-dither", action="store_true",
        help="Skip dithering the final int16 output. Dithering (on by "
             "default) adds an imperceptibly small amount of noise before "
             "quantization to avoid audible distortion in quiet passages "
             "and reverb tails; turn it off only if you need bit-exact "
             "reproducible output across renders.",
    )
    parser.add_argument(
        "-R", "--no-rms-fix", action="store_true",
        help="Skip per-note RMS normalization (on by default), which "
             "evens out each individual note's loudness across wave types/"
             "envelopes before it's mixed in. Turn it off to hear each "
             "wave's raw, unnormalized level. This is separate from the "
             "final mix-wide loudness pass, which --normalize-target and "
             "--limiter-threshold control.",
    )
    parser.add_argument(
        "-a", "--attack", type=float, default=None, metavar="SECONDS",
        help="Override every note's attack (fade-in) time in seconds. "
             "Default follows the --chip profile if one's set, otherwise "
             f"{ATTACK}. Set this to override either.",
    )
    parser.add_argument(
        "-A", "--release", type=float, default=None, metavar="SECONDS",
        help="Override every note's release (fade-out) time in seconds. "
             "Default follows the --chip profile if one's set, otherwise "
             f"{RELEASE}. Set this to override either.",
    )
    parser.add_argument(
        "-n", "--normalize-target", type=float, default=0.35, metavar="RMS",
        help="Target RMS loudness (default 0.35) the final mix is boosted "
             "toward before peak-limiting, so dense multi-voice passages "
             "don't come out quieter than simple ones just because "
             "independent oscillators partially cancel by phase when summed.",
    )
    parser.add_argument(
        "-T", "--limiter-threshold", type=float, default=0.7, metavar="0-1",
        help="Level (default 0.7) above which the final mix gets smoothly "
             "tanh-compressed instead of hard-clipped. Lower it for a more "
             "noticeably 'squashed' loud mix; raise it (max 1.0) for a "
             "sharper, more clip-prone ceiling.",
    )
    parser.add_argument(
        "-M", "--reverb-mix", type=float, default=REVERB_MIX, metavar="0-1",
        help=f"Wet/dry blend for --reverb (default {REVERB_MIX}; 0 = fully "
             "dry, 1 = fully wet). No effect without --reverb.",
    )
    parser.add_argument(
        "-K", "--reverb-decay", type=float, default=REVERB_DECAY, metavar="0-1",
        help=f"Comb-filter feedback gain for --reverb's tail (default "
             f"{REVERB_DECAY}; higher = longer tail). Keep it under ~0.95 "
             "or the tail can run away. No effect without --reverb.",
    )
    parser.add_argument(
        "-S", "--seed", type=int, default=None, metavar="N",
        help="Seed the random number generator used for dither noise (and "
             "anything else randomized during rendering). Default is an "
             "unseeded, different-every-run RNG; set this alongside "
             "--no-dither, or on its own, to get bit-exact reproducible "
             "output across renders of the same input.",
    )


def parse_disabled(raw: str) -> set[str]:
    disabled = {w.strip() for w in raw.split(",") if w.strip()}
    unknown = disabled - ALL_WAVES
    if unknown:
        raise SystemExit(ui.error(
            f"Unknown wave type(s) in --disable: {', '.join(sorted(unknown))}\n"
            f"Valid waves: {', '.join(sorted(ALL_WAVES))}"
        ))
    return disabled


def parse_substitutions(raw: str) -> dict[int, dict[str, str]]:
    subs: dict[int, dict[str, str]] = {}
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    for entry in entries:
        parts = entry.split("-")
        if len(parts) != 3:
            raise SystemExit(ui.error(
                f"Malformed --substitute entry '{entry}': expected "
                "CHANNEL-OLDWAVE-NEWWAVE, e.g. '1-triangle-saw' ('*' is "
                "allowed for CHANNEL and OLDWAVE, e.g. '*-triangle-saw')."
            ))
        ch_str, old_wave, new_wave = parts

        if ch_str == "*":
            ch = ALL_CHANNELS
        else:
            if not ch_str.isdigit():
                raise SystemExit(ui.error(
                    f"Malformed --substitute entry '{entry}': CHANNEL must "
                    "be a number 1-16 or '*'."
                ))
            ch = int(ch_str)
            if not (1 <= ch <= 16):
                raise SystemExit(ui.error(
                    f"Invalid channel {ch} in --substitute entry '{entry}': "
                    "channels are numbered 1-16 (or '*' for every channel)."
                ))
            ch -= 1  # 1-indexed flag -> MIDI's internal 0-15

        # new_wave is never allowed to be '*'; only the "from" side can be
        # a wildcard, since a rule has to land on one wave.
        unknown = ({new_wave} if old_wave == "*" else {old_wave, new_wave}) - ALL_WAVES
        if unknown:
            raise SystemExit(ui.error(
                f"Unknown wave type(s) in --substitute entry '{entry}': "
                f"{', '.join(sorted(unknown))}\n"
                f"Valid waves: {', '.join(sorted(ALL_WAVES))}"
            ))
        subs.setdefault(ch, {})[old_wave] = new_wave
    return subs


def get_chip(name: str | None, no_channel_limits: bool = False) -> "ChipProfile | None":
    if name is None:
        return None
    chip = CHIP_PROFILES[name]
    if no_channel_limits:
        # Keep every other hardware quirk (wave set/remap, hw_family
        # quantization, envelopes, ...) but drop the two knobs that ever
        # cause a note to be dropped or an earlier note to be truncated:
        # the flat max_channels cap and the per-wave voice pool caps that
        # assign_voice_slots steals from. dataclasses.replace() copies the
        # profile rather than mutating the shared CHIP_PROFILES entry, so
        # this is safe to call on every invocation.
        chip = dataclasses.replace(chip, max_channels=None, wave_voice_limit=None)
    return chip