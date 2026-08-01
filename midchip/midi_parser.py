"""
midchip.midi_parser - MIDI file -> closed NoteInterval list.

Handles note on/off pairing, sustain pedal (CC64) hold, program changes
(-> wave type), volume/expression/pan (CC7/CC10/CC11) tracking, pitch-bend
curve capture (per channel, for real vibrato/bend playback), and
(optionally) chip voice-pool remapping.
"""
from __future__ import annotations

import struct
import sys
from collections import defaultdict
from dataclasses import dataclass

import mido

from . import ui
from .chips import ChipProfile, assign_voice_slots
from .cli_common import ALL_CHANNELS
from .constants import PITCH_BEND_RANGE_SEMITONES
from .gm_mapping import instrument_to_wave, resolve_wave_type


@dataclass
class NoteInterval:
    start_time: float
    end_time:   float
    channel:    int
    note:       int
    velocity:   float
    wave_type:  str
    # True when this note's note-on arrived while the same (channel, note)
    # was still sounding (no note-off in between) -- see the "retrigger"
    # handling below. Defaults to False so every existing positional
    # NoteInterval(...) call site (assign_voice_slots included) keeps
    # working unchanged; synth.py uses this to shorten the attack ramp on
    # these, since the ear is already hearing that pitch and a full fresh
    # attack reads as an audible little dip/click rather than a clean
    # re-strike.
    retrigger:  bool = False


@dataclass
class LyricEvent:
    time:       float
    text:       str
    line_break: bool = False  # True if this word should start a new display line


def _read_varlen(data: bytes, i: int) -> tuple[int, int]:
    val = 0
    while True:
        b = data[i]
        i += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    return val, i


def _count_out_of_range_bytes(path: str) -> int:
    """Raw pass over the file's own bytes, independent of mido, purely to
    report how many MIDI data bytes fall outside the valid 0-127 range -
    the actual on-disk defect that makes a strict parser reject a file.
    Real-world exports (OnlineSequencer and similar tools among them) hit
    this most often via velocity values pushed past 127 by a humanize or
    gain pass that forgot to clamp. Diagnostic only: recovery is mido's
    own clip=True, which this function doesn't replace or need to match
    exactly, so a best-effort return of 0 on any parse trouble is fine."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return 0

    if data[0:4] != b"MThd" or len(data) < 14:
        return 0

    hdr_len = struct.unpack(">I", data[4:8])[0]
    _, ntracks, _ = struct.unpack(">HHH", data[8:8 + 6])
    i = 8 + hdr_len
    bad = 0
    track_idx = 0
    try:
        while i < len(data) and track_idx < ntracks:
            if data[i:i + 4] != b"MTrk":
                break
            tlen = struct.unpack(">I", data[i + 4:i + 8])[0]
            j, track_end = i + 8, i + 8 + tlen
            running_status = None
            while j < track_end:
                _, j = _read_varlen(data, j)
                status = data[j]
                if status < 0x80:
                    b = running_status
                else:
                    b = status
                    j += 1
                    if b < 0xF0:
                        running_status = b
                hi = b & 0xF0
                if hi in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    d1, d2 = data[j], data[j + 1]
                    j += 2
                    if d1 > 127 or d2 > 127:
                        bad += 1
                elif hi in (0xC0, 0xD0):
                    if data[j] > 127:
                        bad += 1
                    j += 1
                elif b == 0xFF:
                    j += 1
                    length, j = _read_varlen(data, j)
                    j += length
                elif b in (0xF0, 0xF7):
                    length, j = _read_varlen(data, j)
                    j += length
                else:
                    return bad  # unrecognized status byte; we're so fucked, give up
            i = track_end
            track_idx += 1
    except (IndexError, struct.error):
        pass
    return bad


def _load_midi(path: str) -> "mido.MidiFile":
    """Load a MIDI file, tolerating the kinds of real-world damage that
    strict parsers reject outright, and telling the user what was found
    rather than either crashing or silently reinterpreting the file.

    - Out-of-range data bytes (e.g. velocity > 127 from an export that
      forgot to clamp after scaling/humanizing) are the most common defect
      in the wild. mido's clip=True already recovers from these by
      clamping to the valid range; this just makes that repair visible.
    - Genuinely unrecoverable problems (truncated files, corrupted track/
      chunk structure) get a clear, specific message instead of a raw
      traceback.
    """
    try:
        mido.MidiFile(path, clip=False)
    except OSError as e:
        if "data byte" in str(e):
            bad = _count_out_of_range_bytes(path)
            count_desc = f"{bad} out-of-range data byte(s)" if bad else "out-of-range data byte(s)"
            ui.warn(
                f"'{path}' contains {count_desc} (values above the "
                "valid 0-127 MIDI limit; usually due to velocity/CC export errors.) "
                "They've been clamped to 127 so the file can still render; a "
                "few notes may be slightly louder/softer than the original intended."
            )
        else:
            ui.warn(
                f"'{path}' failed strict MIDI parsing ({e}); "
                "falling back to a lenient parse."
            )
    except EOFError:
        sys.exit(ui.error(
            f"'{path}' looks truncated (it ends in the "
            "middle of a track). Try re-exporting or re-downloading it."
        ))
    except (struct.error, IndexError, ValueError):
        pass  # let the lenient parse below try it out; report if it also dies a horrible fatal death
    except Exception:
        pass

    try:
        return mido.MidiFile(path, clip=True)
    except EOFError:
        sys.exit(ui.error(
            f"'{path}' looks truncated (it ends in the "
            "middle of a track). Try re-exporting or re-downloading it."
        ))
    except Exception as e:
        sys.exit(ui.error(f"Error loading MIDI: {e}"))


def _resolve_substitution(
    substitutions: dict[int, dict[str, str]], channel: int, wave: str
) -> str | None:
    """Look up `wave` on `channel` in `substitutions`, preferring the most
    specific rule available: exact channel + exact wave, then exact channel
    + '*' wave, then '*' channel + exact wave, then '*' channel + '*' wave.
    Returns None if no rule matches."""
    for ch_key in (channel, ALL_CHANNELS):
        ch_subs = substitutions.get(ch_key)
        if not ch_subs:
            continue
        if wave in ch_subs:
            return ch_subs[wave]
        if "*" in ch_subs:
            return ch_subs["*"]
    return None


def parse_intervals(
    path: str,
    disabled: set[str],
    chip: "ChipProfile | None" = None,
    substitutions: dict[int, dict[str, str]] | None = None,
) -> tuple[list[NoteInterval], float, set[int], dict, dict]:
    """Returns (intervals, total_time, used_channels, cc_by_channel,
    bend_by_channel). bend_by_channel maps MIDI channel -> sorted list of
    (time, semitone_shift) breakpoints, built from that channel's
    pitchwheel messages scaled by that channel's pitch-bend range (as set
    by an RPN 0/0 + Data Entry MSB/LSB sequence earlier in the file, or the
    GM default of PITCH_BEND_RANGE_SEMITONES if the file never sets one).

    substitutions maps MIDI channel (0-indexed, or cli_common.ALL_CHANNELS
    for a '*' channel rule) -> {old_wave (or '*' for any wave): new_wave},
    e.g. from cli_common.parse_substitutions. Applied per note-on, after
    GM-instrument/chip wave assignment and before the --disable fallback
    chain, so a channel's notes can be steered to a specific wave without
    touching any other channel using that same GM instrument. When more
    than one rule could match a note, the most specific one wins: an exact
    channel + exact wave beats exact channel + wildcard wave, which beats
    wildcard channel + exact wave, which beats wildcard channel + wildcard
    wave (see _resolve_substitution)."""
    midi = _load_midi(path)

    msgs = list(midi)
    total_time = sum(m.time for m in msgs)

    ch_program = {i: 0 for i in range(16)}
    ch_sustain = {i: False for i in range(16)}

    # Per-channel pitch-bend range in semitones, as set by RPN 0/0 (Registered
    # Parameter 0 = "pitch bend sensitivity") + Data Entry MSB/LSB. Starts at
    # the GM default and is only overwritten if the file actually sends that
    # RPN sequence; MSB = whole semitones, LSB = cents (1/100 semitone).
    ch_bend_range = {i: PITCH_BEND_RANGE_SEMITONES for i in range(16)}
    ch_bend_range_msb = {i: None for i in range(16)}
    # Currently-selected RPN (MSB, LSB) per channel. (127, 127) is the
    # spec's "null"/deselected value, so CC6/CC38 are ignored until a real
    # RPN has been selected via CC101/CC100.
    ch_rpn_selected = {i: (127, 127) for i in range(16)}

    open_notes: dict[tuple[int, int], tuple[float, float, str]] = {}
    held_notes: dict[tuple[int, int], tuple[float, float, str]] = {}
    intervals: list[NoteInterval] = []
    used: set[int] = set()
    cc_events: list[tuple[float, int, int, float]] = []
    bend_events: list[tuple[float, int, float]] = []
    t = 0.0
    retrigger_count = 0
    orphan_note_off_count = 0

    for msg in msgs:
        t += msg.time

        if msg.type == "program_change":
            ch_program[msg.channel] = msg.program

        elif msg.type == "control_change" and msg.control == 64:
            pedal_on = msg.value >= 64
            if ch_sustain[msg.channel] and not pedal_on:
                # held_notes is shared across all 16 channels (keyed by
                # (channel, note)), so only flush the entries that belong
                # to *this* channel - otherwise another channel's pedal
                # lifting here would prematurely cut off notes this
                # channel is still legitimately holding under its own
                # (still-down) sustain.
                for k in [k for k in held_notes if k[0] == msg.channel]:
                    s, v, w, rt = held_notes.pop(k)
                    intervals.append(NoteInterval(s, t, k[0], k[1], v, w, retrigger=rt))
                    used.add(k[0])
            ch_sustain[msg.channel] = pedal_on

        elif msg.type == "note_on" and msg.velocity > 0:
            key = (msg.channel, msg.note)

            # A note_on for a pitch that's still open is a retrigger: the
            # file never sent a note_off before playing it again (common
            # in unquantized/overlapping exports, e.g. hand-drawn piano
            # rolls). Close the ringing note out at the current time
            # first, instead of overwriting open_notes[key] and losing it
            # outright - that used to silently drop every retriggered
            # note from the render entirely.
            is_retrigger = key in open_notes
            if is_retrigger:
                s, v, w, _rt = open_notes.pop(key)
                if t > s:
                    intervals.append(NoteInterval(s, t, key[0], key[1], v, w, retrigger=_rt))
                    used.add(key[0])
                retrigger_count += 1

            wt = instrument_to_wave(ch_program[msg.channel], msg.channel)

            if chip is not None:
                if msg.channel in chip.channel_wave_force:
                    wt = chip.channel_wave_force[msg.channel]
                elif wt not in chip.supported_waves:
                    wt = chip.wave_remap.get(wt, "square")

            if substitutions:
                new_wt = _resolve_substitution(substitutions, msg.channel, wt)
                if new_wt is not None:
                    wt = new_wt

            wt = resolve_wave_type(wt, disabled)
            open_notes[key] = (t, msg.velocity / 127.0, wt, is_retrigger)
            used.add(msg.channel)

        elif msg.type in ("note_off", "note_on"):  # note_on vel=0 == note_off
            key = (msg.channel, msg.note)
            if key in open_notes:
                s, v, w, rt = open_notes.pop(key)
                if ch_sustain[msg.channel]:
                    held_notes[key] = (s, v, w, rt)
                else:
                    intervals.append(NoteInterval(s, t, key[0], key[1], v, w, retrigger=rt))
                    used.add(key[0])
            else:
                orphan_note_off_count += 1

        elif msg.type == "control_change":
            if msg.control in (7, 10, 11):
                cc_events.append((t, msg.channel, msg.control, msg.value / 127.0))
            elif msg.control == 101:      # RPN MSB
                ch_rpn_selected[msg.channel] = (msg.value, ch_rpn_selected[msg.channel][1])
            elif msg.control == 100:      # RPN LSB
                ch_rpn_selected[msg.channel] = (ch_rpn_selected[msg.channel][0], msg.value)
            elif msg.control == 6:        # Data Entry MSB
                if ch_rpn_selected[msg.channel] == (0, 0):
                    ch_bend_range_msb[msg.channel] = msg.value
                    ch_bend_range[msg.channel] = float(msg.value)
            elif msg.control == 38:       # Data Entry LSB (cents)
                if ch_rpn_selected[msg.channel] == (0, 0) and ch_bend_range_msb[msg.channel] is not None:
                    ch_bend_range[msg.channel] = ch_bend_range_msb[msg.channel] + msg.value / 100.0

        elif msg.type == "pitchwheel":
            # msg.pitch is -8192..8191, center 0 == no bend. scale by the
            # channel's actual bend range (from RPN 0/0 if the file set one,
            # otherwise GM default), not a fixed constant (a song that
            # widens/narrows its range and gets scaled by the wrong constant
            # ends up audibly detuned on every bent note. oops.)
            semitone_shift = (msg.pitch / 8192.0) * ch_bend_range[msg.channel]
            bend_events.append((t, msg.channel, semitone_shift))

    for key, (s, v, w, rt) in {**open_notes, **held_notes}.items():
        intervals.append(NoteInterval(s, total_time, key[0], key[1], v, w, retrigger=rt))

    if retrigger_count or orphan_note_off_count:
        parts = []
        if retrigger_count:
            parts.append(f"{retrigger_count} retriggered note(s) recovered")
        if orphan_note_off_count:
            parts.append(f"{orphan_note_off_count} note-off(s) with no matching note-on ignored")
        ui.note(f"'{path}' had messy note pairing: " + ", ".join(parts) + ".")

    cc_by_channel = defaultdict(list)
    for evt_t, ch, ctrl, val in cc_events:
        cc_by_channel[ch].append((evt_t, ctrl, val))
    for ch in cc_by_channel:
        cc_by_channel[ch].sort()

    bend_by_channel = defaultdict(list)
    for evt_t, ch, semitone_shift in bend_events:
        bend_by_channel[ch].append((evt_t, semitone_shift))
    for ch in bend_by_channel:
        bend_by_channel[ch].sort()

    if chip is None:
        return intervals, total_time, used, cc_by_channel, bend_by_channel

    remapped, used_voices = assign_voice_slots(intervals, chip)
    return remapped, total_time, used_voices, cc_by_channel, bend_by_channel


def parse_lyrics(path: str) -> list[LyricEvent]:
    """Extract lyric words/syllables with timestamps, supporting the two
    conventions found in the wild:

    - The dedicated MIDI "lyrics" meta event (0xFF 0x05), spec'd for exactly
      this purpose: one syllable or word per event.
    - The Soft Karaoke (.kar) convention, which predates and is far more
      common than the above: plain "text" meta events (0xFF 0x01) carry the
      lyrics instead, with a few leading-character conventions layered on
      top -- lines starting with '@' are file metadata (title/author/
      language/etc.), not lyrics, and are dropped; '/' marks the start of a
      new display line; '\\' marks the start of a new paragraph (treated
      the same as '/' here, just implying a bigger visual break).

    If a file has genuine 'lyrics' events those are used and any 'text'
    events are ignored; text-event fallback only kicks in when there are no
    'lyrics' events at all. Returns [] if the file has no lyrics by either
    convention.
    """
    midi = _load_midi(path)

    lyric_raw: list[tuple[float, str]] = []
    text_raw: list[tuple[float, str]] = []
    t = 0.0
    for msg in midi:
        t += msg.time
        if msg.type == "lyrics":
            lyric_raw.append((t, msg.text))
        elif msg.type == "text":
            text_raw.append((t, msg.text))

    source = lyric_raw if lyric_raw else text_raw

    events: list[LyricEvent] = []
    for evt_t, raw in source:
        text = raw
        line_break = False
        # These leading-character conventions are Soft Karaoke's, but it's
        # harmless to honor them on genuine 'lyrics' events too -- some
        # encoders reuse the same markers there for double compatibility.
        while text[:1] in ("\\", "/"):
            line_break = True
            text = text[1:]
        if text.startswith("@"):
            continue  # file metadata (title/author/language/...), not a lyric

        # A handful of exports embed literal newlines inside one event
        # instead of (or alongside) the \ and / markers above.
        first = True
        for part in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            part_break = line_break if first else True
            first = False
            if part:
                events.append(LyricEvent(evt_t, part, part_break))

    events.sort(key=lambda e: e.time)
    return events