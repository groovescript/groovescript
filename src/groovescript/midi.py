"""MIDI export: converts GrooveScript IR to MIDI file bytes.

Writes a Format 1 MIDI file with two tracks:
  - Track 0: tempo and time-signature meta events
  - Track 1: drum note events on MIDI channel 10 (0-indexed: 9)

General MIDI (GM) standard drum note numbers are used so the output plays
correctly in any GM-compatible device or DAW.
"""

import math
from fractions import Fraction

from .compiler import Event, IRGroove, IRSong

TICKS_PER_BEAT = 480  # ticks per quarter note (PPQ)
_DRUM_CHANNEL = 9     # MIDI channel 10, 0-indexed
_DEFAULT_TEMPO = 120  # BPM when no tempo is specified in metadata

# General MIDI standard drum note numbers (channel 10 / 0-indexed 9)
_NOTE: dict[str, int] = {
    "BD":  36,   # Bass Drum 1
    "SN":  38,   # Acoustic Snare
    "SCS": 37,   # Side Stick (snare cross-stick)
    "HH":  42,   # Closed Hi-Hat
    "OH":  46,   # Open Hi-Hat
    "HF":  44,   # Pedal Hi-Hat
    "RD":  51,   # Ride Cymbal 1
    "CR":  49,   # Crash Cymbal 1
    "FT":  41,   # Low Floor Tom
    "HT":  50,   # High Tom
    "MT":  45,   # Low-Mid Tom
}

_VEL_DEFAULT = 80
_VEL_ACCENT  = 110
_VEL_GHOST   = 30
_VEL_GRACE   = 60   # velocity for flam/drag grace strokes

_GRACE_TICKS  = 30  # ticks before main note that a grace stroke falls
_HIT_DURATION = 30  # note-on → note-off gap for a standard percussive hit

# Cymbals ring: their note-off is deferred until just before the next strike
# of the same pitch (or extended past the end of the song with a tail).
_SUSTAIN_PITCHES: frozenset[int] = frozenset({49, 51, 46})  # CR, RD, OH
_SUSTAIN_TAIL_TICKS = 4 * TICKS_PER_BEAT  # ring-out past the final strike


# ---------------------------------------------------------------------------
# MIDI binary primitives
# ---------------------------------------------------------------------------

def _vlq(value: int) -> bytes:
    """Encode a non-negative integer as a MIDI variable-length quantity."""
    if value == 0:
        return b"\x00"
    parts: list[int] = []
    while value:
        parts.append(value & 0x7F)
        value >>= 7
    parts.reverse()
    for i in range(len(parts) - 1):
        parts[i] |= 0x80
    return bytes(parts)


def _u32(v: int) -> bytes:
    return v.to_bytes(4, "big")


def _u16(v: int) -> bytes:
    return v.to_bytes(2, "big")


def _u24(v: int) -> bytes:
    return v.to_bytes(3, "big")


def _build_track(events: list[tuple[int, bytes]]) -> bytes:
    """Serialize (absolute_tick, data) pairs into an MTrk chunk.

    Events at the same tick sort note-offs before note-ons to avoid
    spurious retriggering in strict MIDI players.
    """
    def _sort_key(e: tuple[int, bytes]) -> tuple[int, int]:
        tick, data = e
        # 0x8x = note-off → priority 0; everything else → priority 1
        priority = 0 if (data[0] & 0xF0) == 0x80 else 1
        return (tick, priority)

    body = b""
    prev = 0
    for tick, data in sorted(events, key=_sort_key):
        body += _vlq(tick - prev) + data
        prev = tick
    body += b"\x00\xFF\x2F\x00"  # end-of-track meta event
    return b"MTrk" + _u32(len(body)) + body


def _tempo_event(bpm: int) -> bytes:
    """Build a Set Tempo meta event for the given BPM."""
    usec = round(60_000_000 / bpm)
    return b"\xFF\x51\x03" + _u24(usec)


def _timesig_event(ts: str) -> bytes:
    """Build a Time Signature meta event from a string like '4/4' or '6/8'."""
    n, d = ts.split("/")
    n, d = int(n), int(d)
    dd = round(math.log2(d))  # MIDI denominator is log2(d): 4→2, 8→3
    return bytes([0xFF, 0x58, 0x04, n, dd, 24, 8])


def _bar_ticks(ts: str) -> int:
    """Return the number of ticks in one full bar of the given time signature."""
    n, d = ts.split("/")
    # N beats of duration 4/D quarter notes each → N * 4/D * TICKS_PER_BEAT
    return int(Fraction(int(n) * 4, int(d)) * TICKS_PER_BEAT)


def _note_on(note: int, vel: int) -> bytes:
    return bytes([0x90 | _DRUM_CHANNEL, note & 0x7F, vel & 0x7F])


def _note_off(note: int) -> bytes:
    return bytes([0x80 | _DRUM_CHANNEL, note & 0x7F, 0])


def _velocity(modifiers: list[str]) -> int:
    if "accent" in modifiers:
        return _VEL_ACCENT
    if "ghost" in modifiers:
        return _VEL_GHOST
    return _VEL_DEFAULT


def _extend_sustained(
    events: list[tuple[int, bytes]], end_tick: int
) -> list[tuple[int, bytes]]:
    """Let cymbals ring: replace the short note-off on every sustained pitch
    with one that lands just before the next strike of the same pitch (or a
    full bar past the song's end if no further strike follows).
    """
    on_ticks: dict[int, list[int]] = {}
    for tick, data in events:
        if (
            (data[0] & 0xF0) == 0x90
            and data[2] > 0
            and data[1] in _SUSTAIN_PITCHES
        ):
            on_ticks.setdefault(data[1], []).append(tick)
    for ticks in on_ticks.values():
        ticks.sort()

    out: list[tuple[int, bytes]] = []
    for tick, data in events:
        is_off = (
            (data[0] & 0xF0) == 0x80
            or ((data[0] & 0xF0) == 0x90 and data[2] == 0)
        )
        if is_off and data[1] in _SUSTAIN_PITCHES:
            continue
        out.append((tick, data))

    for pitch, ticks in on_ticks.items():
        for i, t in enumerate(ticks):
            if i + 1 < len(ticks):
                off_tick = max(t + 1, ticks[i + 1] - 1)
            else:
                off_tick = max(t + 1, end_tick + _SUSTAIN_TAIL_TICKS)
            out.append((off_tick, _note_off(pitch)))

    return out


# ---------------------------------------------------------------------------
# Per-hit event builder
# ---------------------------------------------------------------------------

def _add_hit(
    out: list[tuple[int, bytes]],
    ev: Event,
    note: int,
    tick: int,
) -> None:
    """Append MIDI note events for one regular (non-buzz) drum hit.

    Handles flam (one grace note), drag (two grace notes), and double
    (a second stroke one 32nd note after the main hit).
    """
    vel = _velocity(ev.modifiers)
    mods = ev.modifiers

    # Grace notes (flam / drag) land slightly before the main note
    if "flam" in mods:
        gt = max(0, tick - _GRACE_TICKS)
        out.append((gt, _note_on(note, _VEL_GRACE)))
        out.append((gt + _HIT_DURATION, _note_off(note)))
    elif "drag" in mods:
        for offset in (2, 1):
            gt = max(0, tick - offset * _GRACE_TICKS)
            out.append((gt, _note_on(note, _VEL_GRACE)))
            out.append((gt + _HIT_DURATION, _note_off(note)))

    # Main note
    out.append((tick, _note_on(note, vel)))
    out.append((tick + _HIT_DURATION, _note_off(note)))

    # Double: second stroke one 32nd note after the main hit
    if "double" in mods:
        d_tick = tick + TICKS_PER_BEAT // 8  # 1/32 note = TICKS_PER_BEAT / 8
        out.append((d_tick, _note_on(note, vel)))
        out.append((d_tick + _HIT_DURATION, _note_off(note)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def emit_midi(ir: IRSong | IRGroove) -> bytes:
    """Convert an IRSong or standalone IRGroove to MIDI file bytes (Format 1).

    For a standalone IRGroove (no arrangement), the groove is played once at
    120 BPM in 4/4.  For an IRSong, the full arrangement is emitted with all
    tempo and time-signature changes honoured.
    """
    if isinstance(ir, IRGroove):
        return _midi_from_groove(ir)
    return _midi_from_song(ir)


# ---------------------------------------------------------------------------
# IRSong path
# ---------------------------------------------------------------------------

def _midi_from_song(song: IRSong) -> bytes:
    default_ts = song.metadata.time_signature
    default_bpm = song.metadata.tempo if song.metadata.tempo is not None else _DEFAULT_TEMPO

    # Pre-compute absolute tick start for each bar
    bar_starts: list[int] = []
    cur_tick = 0
    cur_ts = default_ts
    for bar in song.bars:
        bar_starts.append(cur_tick)
        ts = bar.time_signature if bar.time_signature is not None else cur_ts
        cur_ts = ts
        cur_tick += _bar_ticks(ts)

    # Tempo track: time-signature and tempo meta events
    tempo_track: list[tuple[int, bytes]] = [
        (0, _timesig_event(default_ts)),
        (0, _tempo_event(default_bpm)),
    ]
    cur_ts = default_ts
    cur_bpm = default_bpm
    for bar_idx, bar in enumerate(song.bars):
        tick = bar_starts[bar_idx]
        if bar.time_signature is not None and bar.time_signature != cur_ts:
            cur_ts = bar.time_signature
            tempo_track.append((tick, _timesig_event(cur_ts)))
        if bar.tempo is not None and bar.tempo != cur_bpm:
            cur_bpm = bar.tempo
            tempo_track.append((tick, _tempo_event(cur_bpm)))

    drum_track = _bars_to_drum_events(song.bars, bar_starts, default_ts)
    drum_track = _extend_sustained(drum_track, cur_tick)

    header = b"MThd" + _u32(6) + _u16(1) + _u16(2) + _u16(TICKS_PER_BEAT)
    return header + _build_track(tempo_track) + _build_track(drum_track)


def _bars_to_drum_events(
    bars: list,
    bar_starts: list[int],
    default_ts: str,
) -> list[tuple[int, bytes]]:
    """Convert a list of IRBars to MIDI drum note events."""
    out: list[tuple[int, bytes]] = []
    cur_ts = default_ts

    for bar_idx, bar in enumerate(bars):
        bstart = bar_starts[bar_idx]
        ts = bar.time_signature if bar.time_signature is not None else cur_ts
        cur_ts = ts
        bticks = _bar_ticks(ts)

        if bar.is_rest:
            continue

        for ev in bar.events:
            note = _NOTE.get(ev.instrument)
            if note is None:
                continue

            tick = bstart + int(ev.beat_position * bticks)

            if ev.tied_from_prev:
                # Continuation of a cross-bar buzz: emit note-off at the end
                # of this segment only when the chain terminates here.
                if (
                    "buzz" in ev.modifiers
                    and ev.duration is not None
                    and not ev.tied_to_next
                ):
                    off_tick = bstart + int(ev.duration * bticks)
                    out.append((off_tick, _note_off(note)))
                # Middle of a chain (tied_to_next=True) or non-buzz: skip
                continue

            if "buzz" in ev.modifiers and ev.duration is not None:
                # Buzz roll: open the note here; close it when the chain ends
                out.append((tick, _note_on(note, _velocity(ev.modifiers))))
                if not ev.tied_to_next:
                    off_tick = tick + int(ev.duration * bticks)
                    out.append((off_tick, _note_off(note)))
                continue

            _add_hit(out, ev, note, tick)

    return out


# ---------------------------------------------------------------------------
# Standalone IRGroove path
# ---------------------------------------------------------------------------

def _midi_from_groove(groove: IRGroove) -> bytes:
    default_ts = "4/4"
    default_bpm = _DEFAULT_TEMPO
    bticks = _bar_ticks(default_ts)

    bar_starts = [i * bticks for i in range(groove.bars)]

    tempo_track: list[tuple[int, bytes]] = [
        (0, _timesig_event(default_ts)),
        (0, _tempo_event(default_bpm)),
    ]

    drum_track: list[tuple[int, bytes]] = []
    for ev in groove.events:
        bar_idx = ev.bar - 1  # 1-indexed to 0-indexed
        if bar_idx < 0 or bar_idx >= groove.bars:
            continue
        note = _NOTE.get(ev.instrument)
        if note is None:
            continue

        bstart = bar_starts[bar_idx]
        tick = bstart + int(ev.beat_position * bticks)

        if ev.tied_from_prev:
            if (
                "buzz" in ev.modifiers
                and ev.duration is not None
                and not ev.tied_to_next
            ):
                off_tick = bstart + int(ev.duration * bticks)
                drum_track.append((off_tick, _note_off(note)))
            continue

        if "buzz" in ev.modifiers and ev.duration is not None:
            drum_track.append((tick, _note_on(note, _velocity(ev.modifiers))))
            if not ev.tied_to_next:
                off_tick = tick + int(ev.duration * bticks)
                drum_track.append((off_tick, _note_off(note)))
            continue

        _add_hit(drum_track, ev, note, tick)

    drum_track = _extend_sustained(drum_track, groove.bars * bticks)

    header = b"MThd" + _u32(6) + _u16(1) + _u16(2) + _u16(TICKS_PER_BEAT)
    return header + _build_track(tempo_track) + _build_track(drum_track)
