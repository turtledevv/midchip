"""
midchip.viz.app | midchip visualizer
----------
desc here later
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import wave
from pathlib import Path

import pygame

from midchip import SAMPLE_RATE, FPS
from midchip import ui

from .render import OscilloscopeGrid

DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720


def _title_for(midi_path: str, chip) -> str:
    name = Path(midi_path).stem
    return f"{name} \u2014 {chip.label}" if chip else name


def run_live(
    midi_path: str, intervals, total_time: float, used_channels, chip, audio,
    width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
    lyrics=None,
) -> None:
    # render_audio returns (n_samples,) for mono or (n_samples, 2) for
    # stereo depending on the --mono flag; match the mixer to whichever it
    # actually gave us instead of assuming mono like this used to.
    channels = audio.shape[1] if audio.ndim == 2 else 1
    pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=channels)
    pygame.init()

    screen = pygame.display.set_mode((width, height))
    title = _title_for(midi_path, chip)
    pygame.display.set_caption(title)
    clock = pygame.time.Clock()

    grid = OscilloscopeGrid(
        width, height, sorted(used_channels), title,
        chip_triangle_steps=chip.triangle_steps if chip else None,
        lyrics=lyrics,
    )

    sound = pygame.sndarray.make_sound(audio)
    channel = sound.play()
    start = time.time()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        elapsed = time.time() - start
        if elapsed >= total_time or (channel is not None and not channel.get_busy() and elapsed > 0.5):
            running = False
            elapsed = total_time

        active = grid.active_notes(intervals, elapsed)
        grid.draw(screen, active, min(elapsed, total_time), total_time)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.mixer.stop()
    pygame.quit()


def run_export(
    midi_path: str, intervals, total_time: float, used_channels, chip, audio,
    out_path: str, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
    fps: int = FPS, lyrics=None,
) -> None:
    """Render the oscilloscope to `out_path` (a video file) via ffmpeg,
    with no window or live audio device required."""
    if not _ffmpeg_available():
        raise SystemExit(ui.error(
            "ffmpeg not found on PATH. Install it (e.g. `apt install ffmpeg` / "
            "`brew install ffmpeg`) to use --export."
        ))

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()

    title = _title_for(midi_path, chip)
    screen = pygame.Surface((width, height))
    grid = OscilloscopeGrid(
        width, height, sorted(used_channels), title,
        chip_triangle_steps=chip.triangle_steps if chip else None,
        lyrics=lyrics,
    )

    tmp_wav = Path(out_path).with_suffix(".tmp.wav")
    channels = audio.shape[1] if audio.ndim == 2 else 1
    with wave.open(str(tmp_wav), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

    ffmpeg = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pixel_format", "rgb24",
            "-video_size", f"{width}x{height}", "-framerate", str(fps),
            "-i", "pipe:0",
            "-i", str(tmp_wav),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            out_path,
        ],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    n_frames = max(1, int(total_time * fps) + 1)
    try:
        for frame_idx in range(n_frames):
            elapsed = frame_idx / fps
            active = grid.active_notes(intervals, elapsed)
            grid.draw(screen, active, elapsed, total_time)
            ffmpeg.stdin.write(pygame.image.tostring(screen, "RGB"))
            if frame_idx % max(1, fps // 2) == 0:
                line = ui.progress_bar(frame_idx, n_frames, label="Exporting frames",
                                        show_count=True)
                if line:
                    print(line, end="", file=sys.stderr, flush=True)
    finally:
        ffmpeg.stdin.close()
        ffmpeg.wait()
        tmp_wav.unlink(missing_ok=True)
        ui.blank()

    pygame.quit()
    if ffmpeg.returncode != 0:
        raise SystemExit(ui.error(f"ffmpeg exited with code {ffmpeg.returncode}"))
    ui.success(f"Wrote {out_path}")


def _ffmpeg_available() -> bool:
    from shutil import which
    return which("ffmpeg") is not None