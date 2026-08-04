"""
midchip.viz __main__ | realtime oscilloscope visualization for MidChip.
----------

Usage:
    python -m midchip.viz song.mid                              # normal, live window
    python -m midchip.viz song.mid --chip 2a03                  # NES-restricted, live
    python -m midchip.viz song.mid --chip dmg --export out.mp4  # render to video
"""
from __future__ import annotations

import argparse
import sys

from midchip import add_common_args, parse_disabled, parse_substitutions, get_chip, FPS
from midchip import ui
from midchip.__main__ import VERSION # why have i done this
from midchip.midi_parser import parse_intervals, parse_lyrics
from midchip.synth import render_audio

from .app import run_live, run_export, DEFAULT_WIDTH, DEFAULT_HEIGHT
from .render import LyricTrack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="midchip.viz",
        description="Real-time oscilloscope visualization of a MIDI file "
                     "being chiptune-synthesized.",
    )
    add_common_args(parser)
    parser.add_argument(
        "-e", "--export", metavar="OUT.mp4", default=None,
        help="Render to a video file instead of opening a live window "
             "(requires ffmpeg on PATH)",
    )
    parser.add_argument("-W", "--width", type=int, default=DEFAULT_WIDTH,
                         help=f"Window/video width in pixels (default {DEFAULT_WIDTH})")
    parser.add_argument("-H", "--height", type=int, default=DEFAULT_HEIGHT,
                         help=f"Window/video height in pixels (default {DEFAULT_HEIGHT})")
    parser.add_argument(
        "-f", "--fps", type=int, default=FPS,
        help=f"Frame rate for --export (default {FPS}). The live window "
             "free-runs at the display's refresh rate instead.",
    )
    return parser


def _progress(i: int, total: int) -> None:
    line = ui.progress_bar(i, total, label="Rendering audio")
    if line:
        print(line, end="", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> None:
    # I don't even..
    print(
        "\033[38;2;255;152;238m\033[1m" + r"            _     _"+"\033[38;2;48;244;140m"+r"      _     _       "+"\n"
        "\033[38;2;255;152;238m" + r"           (_)   | |"+"\033[38;2;48;244;140m"+r"    | |   (_)      "+"\n"
        "\033[38;2;255;137;235m" + r"  _ __ ___  _  __| |"+"\033[38;2;36;234;129m"+r" ___| |__  _ _ __  "+"\n"
        "\033[38;2;255;137;235m" + r" | '_ ` _ \| |/ _` |"+"\033[38;2;36;234;129m"+r"/ __| '_ \| | '_ \ "+"\n"
        "\033[38;2;255;107;229m" + r" | | | | | | | (_| |"+"\033[38;2;18;204;106m"+r" (__| | | | | |_) |"+"\n"
        "\033[38;2;255;107;229m" + r" |_| |_| |_|_|\__,_|"+"\033[38;2;18;204;106m"+r"\___|_| |_|_| .__/ "+"\n"
        "\033[0;31m\033[1m" + "   viz                          \033[38;2;26;221;118m| |    "+"\n"
        "\033[38;2;255;92;226m" + f"      \033[0m\033[0;37m\033[3m{VERSION}\033[0m\033[1m\033[0;34m\033[1m\033[38;2;26;221;118m" + r"                    |_|    " + "\033[0m"+"\n"
        # "\n\033[0m\033[3m\"Insert sick splash text here\""+"\n"
        "\033[1m\033[2m-----------------------------------------\n\033[0m"
    )
    args = build_parser().parse_args(argv)
    disabled = parse_disabled(args.disable)
    substitutions = parse_substitutions(args.substitute)
    chip = get_chip(args.chip, no_channel_limits=args.no_chip_channel_limits)

    ui.step(f"Parsing {args.midi_file}...")
    intervals, total_time, used, cc_by_channel, bend_by_channel = parse_intervals(
        args.midi_file, disabled, chip, substitutions
    )
    if not intervals:
        sys.exit(ui.error("No notes found in this MIDI file (after wave/channel filtering)."))

    lyric_events = parse_lyrics(args.midi_file)
    lyrics = LyricTrack(lyric_events)
    if lyrics:
        ui.info(f"Found lyrics ({len(lyric_events)} word/syllable event(s)).")

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
    ui.blank()  # newline after the progress bar

    if args.export:
        run_export(
            args.midi_file, intervals, total_time, used, chip, audio, args.export,
            width=args.width, height=args.height, fps=args.fps, lyrics=lyrics,
        )
    else:
        run_live(
            args.midi_file, intervals, total_time, used, chip, audio,
            width=args.width, height=args.height, lyrics=lyrics,
        )


if __name__ == "__main__":
    main()