"""
midchip.viz.render | draws an oscilloscope grid via pygame
----------
write a desc. here later
"""
from __future__ import annotations

import heapq
import itertools
import math

import numpy as np
import pygame

from midchip import DISP_SAMPLES, generate_wave, midi_to_freq

from . import theme

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(n: int) -> str:
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


class LyricLine:
    __slots__ = ("start", "words")

    def __init__(self, words: list[tuple[str, float]]):
        self.words = words             # [(text, time), ...]
        self.start = words[0][1]


class LyricTrack:
    AUTO_GAP_SECONDS = 3.0
    AUTO_MAX_WORDS = 10

    def __init__(self, events: list):
        self.lines: list[LyricLine] = []
        if not events:
            return

        has_explicit_breaks = any(e.line_break for e in events[1:])

        grouped: list[list[tuple[str, float]]] = []
        current: list[tuple[str, float]] = []
        prev_time = None
        for i, e in enumerate(events):
            if i == 0:
                start_new = True
            elif has_explicit_breaks:
                start_new = e.line_break
            else:
                start_new = (
                    (prev_time is not None and e.time - prev_time > self.AUTO_GAP_SECONDS)
                    or len(current) >= self.AUTO_MAX_WORDS
                )
            if start_new and current:
                grouped.append(current)
                current = []
            current.append((e.text, e.time))
            prev_time = e.time
        if current:
            grouped.append(current)

        self.lines = [LyricLine(words) for words in grouped]

    def __bool__(self) -> bool:
        return bool(self.lines)

    def current_line(self, elapsed: float):
        if not self.lines:
            return None
        chosen = self.lines[0]
        for line in self.lines:
            if line.start <= elapsed:
                chosen = line
            else:
                break
        sung = sum(1 for _, wt in chosen.words if wt <= elapsed)
        return chosen.words, sung


def grid_shape(n: int) -> tuple[int, int]:
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return rows, cols


class Panel:
    __slots__ = ("rect", "channel", "scope_rect")

    def __init__(self, rect: pygame.Rect, channel: int):
        self.rect = rect
        self.channel = channel
        pad_top, pad_bottom = 22, 16
        self.scope_rect = pygame.Rect(
            rect.x + 4, rect.y + pad_top,
            rect.width - 8, rect.height - pad_top - pad_bottom,
        )


class ActiveNoteTracker:
    def __init__(self, intervals):
        self._sorted = sorted(intervals, key=lambda iv: iv.start_time)
        self._start_idx = 0
        self._heaps: dict[int, list] = {}
        self._counter = itertools.count()
        self._last_elapsed = float("-inf")

    def active(self, elapsed: float) -> dict[int, object]:
        if elapsed < self._last_elapsed:
            # shouldn't happen from either call site (both only move
            # forward); but if it ever does, a stale/incorrect result is
            # safer than corrupting the sweep state irrecoverably..
            elapsed = self._last_elapsed
        self._last_elapsed = elapsed

        n = len(self._sorted)
        while self._start_idx < n and self._sorted[self._start_idx].start_time <= elapsed:
            iv = self._sorted[self._start_idx]
            heap = self._heaps.setdefault(iv.channel, [])
            heapq.heappush(heap, (-iv.start_time, next(self._counter), iv))
            self._start_idx += 1

        result: dict[int, object] = {}
        for ch, heap in self._heaps.items():
            # heap top is always the latest-started note pushed so
            # far for this channel. if it's already ended, it can never
            # become valid again (elapsed only grows), so it's safe to
            # discard permanently and check the next-latest-started one.
            while heap and heap[0][2].end_time <= elapsed:
                heapq.heappop(heap)
            if heap:
                result[ch] = heap[0][2]
        return result


class OscilloscopeGrid:
    def __init__(self, width: int, height: int, channels: list[int], title: str,
                 chip_triangle_steps: int | None = None, lyrics: "LyricTrack | None" = None):
        self.width, self.height = width, height
        self.channels = channels
        self.title = title
        self.tri_steps = chip_triangle_steps
        self.lyrics = lyrics if lyrics else None

        pygame.font.init()
        self.font_title  = pygame.font.SysFont("monospace", 15, bold=True)
        self.font_sub    = pygame.font.SysFont("monospace", 12)
        self.font_label  = pygame.font.SysFont("monospace", 13, bold=True)
        self.font_info   = pygame.font.SysFont("monospace", 11)
        self.font_lyric  = pygame.font.SysFont("monospace", 14, bold=True)

        header_h  = 46
        if self.lyrics:
            header_h += 20  # extra row along the top for lyrics
        footer_h  = 22
        n_ch      = max(len(channels), 1)
        rows, cols = grid_shape(n_ch)
        grid_area = pygame.Rect(8, header_h, width - 16, height - header_h - footer_h)

        self.panels: dict[int, Panel] = {}
        cell_w = grid_area.width / cols
        cell_h = grid_area.height / rows
        for idx, ch in enumerate(channels):
            r, c = divmod(idx, cols)
            rect = pygame.Rect(
                int(grid_area.x + c * cell_w) + 3,
                int(grid_area.y + r * cell_h) + 3,
                int(cell_w) - 6, int(cell_h) - 6,
            )
            self.panels[ch] = Panel(rect, ch)

        self.progress_rect = pygame.Rect(16, height - footer_h + 4, width - 32, 8)

    def draw(self, surface: pygame.Surface, active: dict[int, "object"], elapsed: float, total_time: float):
        surface.fill(theme.BASE)

        title_surf = self.font_title.render(self.title, True, theme.TEXT)
        surface.blit(title_surf, title_surf.get_rect(center=(self.width // 2, 14)))
        time_surf = self.font_sub.render(f"{elapsed:5.1f}s / {total_time:5.1f}s", True, theme.SUBTEXT)
        surface.blit(time_surf, time_surf.get_rect(center=(self.width // 2, 32)))

        if self.lyrics:
            self._draw_lyrics(surface, elapsed)

        for ch, panel in self.panels.items():
            iv = active.get(ch)
            self._draw_panel(surface, panel, iv)

        pygame.draw.rect(surface, theme.SURFACE, self.progress_rect, border_radius=3)
        if total_time > 0:
            w = int(self.progress_rect.width * min(elapsed / total_time, 1.0))
            if w > 0:
                fill = pygame.Rect(self.progress_rect.x, self.progress_rect.y, w, self.progress_rect.height)
                pygame.draw.rect(surface, theme.BLUE, fill, border_radius=3)

    def _draw_lyrics(self, surface: pygame.Surface, elapsed: float) -> None:
        result = self.lyrics.current_line(elapsed)
        if result is None:
            return
        words, sung = result

        x0, y = 16, 48
        max_width = self.width - x0 - 16

        start = 0
        while start < sung:
            text = "".join(w for w, _ in words[start:])
            if self.font_lyric.size(text)[0] <= max_width:
                break
            start += 1
        visible = words[start:]
        visible_sung = sung - start

        x = x0
        for i, (word, _wt) in enumerate(visible):
            color = theme.TEXT if i < visible_sung else theme.OVERLAY
            surf = self.font_lyric.render(word, True, color)
            if x + surf.get_width() > x0 + max_width:
                break
            surface.blit(surf, (x, y))
            x += surf.get_width()

    def _draw_panel(self, surface: pygame.Surface, panel: Panel, iv):
        rect = panel.rect
        active = iv is not None
        bg = theme.MANTLE if active else theme.BASE
        pygame.draw.rect(surface, bg, rect)
        pygame.draw.rect(surface, theme.SURFACE, rect, width=1)

        # label = f"Ch {panel.channel + 1}"
        label = ""
        lbl_surf = self.font_label.render(label, True, theme.TEXT)
        surface.blit(lbl_surf, lbl_surf.get_rect(midtop=(rect.centerx, rect.y - 18)))

        sr = panel.scope_rect
        mid_y = sr.centery
        pygame.draw.line(surface, theme.SURFACE, (sr.x, mid_y), (sr.right, mid_y), 1)

        if active:
            freq = midi_to_freq(iv.note)
            color = theme.wave_color(iv.wave_type)
            is_stepped = (iv.wave_type == "triangle" and self.tri_steps is not None)
            f = max(freq, 8.0)
            WINDOW = 0.015  # 15 ms
            t = np.linspace(0, WINDOW, DISP_SAMPLES, endpoint=False)
            wave = generate_wave(iv.wave_type, t, f, triangle_steps=self.tri_steps if is_stepped else None, bandlimit=False)
            scale = 0.95 if is_stepped else 0.72
            pts = []
            for i in range(DISP_SAMPLES):
                x = sr.x + int(i / (DISP_SAMPLES - 1) * sr.width)
                y = int(mid_y - wave[i] * scale * (sr.height / 2))
                pts.append((x, y))
            if len(pts) > 1:
                pygame.draw.lines(surface, color, False, pts, 2)

            info = f"{iv.wave_type}  {note_name(iv.note)}  {freq:.0f}Hz"
            info_surf = self.font_info.render(info, True, color)
            surface.blit(info_surf, info_surf.get_rect(midtop=(rect.centerx, rect.bottom - 15)))
        else:
            info_surf = self.font_info.render("\u2014", True, theme.OVERLAY)
            surface.blit(info_surf, info_surf.get_rect(midtop=(rect.centerx, rect.bottom - 15)))

    def active_notes(self, intervals, elapsed: float) -> dict[int, object]:
        tracker = getattr(self, "_tracker", None)
        if tracker is None or getattr(self, "_tracker_key", None) != id(intervals):
            tracker = ActiveNoteTracker(intervals)
            self._tracker = tracker
            self._tracker_key = id(intervals)
        return tracker.active(elapsed)