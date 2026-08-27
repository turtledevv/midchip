"""
midchip __main__ | render a MIDI file to chiptune audio.
----------

Usage:
    python -m midchip song.mid                        # preview only (plays, no file)
    python -m midchip song.mid -o song.wav             # render to WAV only (stereo, panned)
    python -m midchip song.mid -o song.wav --play      # render to WAV AND play it
    python -m midchip song.mid --chip 2a03 --disable pwm,ring_mod -o nes.wav
    python -m midchip song.mid --reverb -o song.wav    # add reverb tail
    python -m midchip song.mid --mono -o song.wav      # old-style mono, no panning
"""
from __future__ import annotations

import argparse
import sys
import wave
import os

from . import ui
from .cli_common import add_common_args, parse_disabled, parse_substitutions, get_chip
from .constants import SAMPLE_RATE
from .midi_parser import parse_intervals
from .synth import render_audio

VERSION = "v2.4.1"

def _progress(i: int, total: int) -> None:
    line = ui.progress_bar(i, total, label="Rendering")
    if line:
        print(line, end="", file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="midchip",
        description="Turn a MIDI file into chiptune audio.",
    )
    add_common_args(parser)
    parser.add_argument(
        "-o", "--output", default=None, metavar="OUT.wav",
        help="Write rendered audio to this .wav path",
    )
    parser.add_argument(
        "-p", "--play", action="store_true",
        help="Play the rendered audio back. This is the default behavior "
             "when --output isn't given; pass it explicitly to also play "
             "back audio that's being saved to a file.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    # I'm not religious; but please forgive me for I have sinned.
    # Don't even try to read this.
    # Leave it alone; and never touch it again.
    # This goes for me and all future maintainers.
    #                    - Thanks for understanding, from the dipshit who coded this
    print(
        "\033[38;2;255;152;238m\033[1m" + r"            _     _"+"\033[38;2;48;244;140m"+r"      _     _       "+"\n"
        "\033[38;2;255;152;238m" + r"           (_)   | |"+"\033[38;2;48;244;140m"+r"    | |   (_)      "+"\n"
        "\033[38;2;255;137;235m" + r"  _ __ ___  _  __| |"+"\033[38;2;36;234;129m"+r" ___| |__  _ _ __  "+"\n"
        "\033[38;2;255;137;235m" + r" | '_ ` _ \| |/ _` |"+"\033[38;2;36;234;129m"+r"/ __| '_ \| | '_ \ "+"\n"
        "\033[38;2;255;107;229m" + r" | | | | | | | (_| |"+"\033[38;2;18;204;106m"+r" (__| | | | | |_) |"+"\n"
        "\033[38;2;255;107;229m" + r" |_| |_| |_|_|\__,_|"+"\033[38;2;18;204;106m"+r"\___|_| |_|_| .__/ "+"\n"
        "\033[38;2;26;221;118m" + r"                                | |    "+"\n"
        "\033[38;2;255;92;226m" + f"      \033[0m\033[0;37m\033[3m{VERSION}\033[0m\033[1m\033[0;34m\033[1m\033[38;2;26;221;118m" + r"                    |_|    " + "\033[0m"+"\n"
        # "\n\033[0m\033[3m\"Insert sick splash text here\""+"\n"
        "\033[1m\033[2m-----------------------------------------\n\033[0m"
    )

    args = build_parser().parse_args(argv)
    disabled = parse_disabled(args.disable)
    substitutions = parse_substitutions(args.substitute)
    chip = get_chip(args.chip, no_channel_limits=args.no_chip_channel_limits)

    # No --output means there's nothing else to do with the audio but play it.
    should_play = args.play or args.output is None

    ui.step(f"Parsing {args.midi_file}...")
    intervals, total_time, used, cc_by_channel, bend_by_channel = parse_intervals(
        args.midi_file, disabled, chip, substitutions
    )
    if not intervals:
        sys.exit(ui.error("No notes found in this MIDI file (after wave/channel filtering)."))

    ui.step(f"Rendering {len(intervals)} notes across {len(used)} channel(s)"
            + (f" on {chip.label}" if chip else "") + "...")
    audio = render_audio(
        intervals, total_time, volume=args.volume,
        cc_by_channel=cc_by_channel, bend_by_channel=bend_by_channel,
        vibrato=args.vibrato, chip=chip, progress_cb=_progress,
        stereo=not args.mono, reverb=args.reverb,
        unison_voices=args.unison, unison_detune_cents=args.detune,
        dither=not args.no_dither, workers=args.workers,
        rms_fix=not args.no_rms_fix, seed=args.seed,
        attack=args.attack, release=args.release,
        reverb_mix=args.reverb_mix, reverb_decay=args.reverb_decay,
        normalize_target=args.normalize_target,
        limiter_threshold=args.limiter_threshold,
        vibrato_rate=args.vibrato_rate, vibrato_depth=args.vibrato_depth,
    )
    ui.blank()  # newline after progress bar

    if args.output:
        with wave.open(args.output, "wb") as wf:
            wf.setnchannels(1 if args.mono else 2)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        ui.success(f"Wrote {args.output}")

    if should_play:
        from .playback import play as play_audio

        if os.environ.get("MIDCHIP_GUI") is not None:
            ui.info("Playing... (Click Exit to stop)")
        else:
            ui.info("Playing... (Ctrl+C to stop)")

        try:
            play_audio(audio, rate=SAMPLE_RATE, blocking=True)
        except KeyboardInterrupt:
            ui.blank()


if __name__ == "__main__":
    main()
