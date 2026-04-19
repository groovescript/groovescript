"""Tests for the MIDI export module (groovescript.midi)."""

import struct
from fractions import Fraction

import pytest

from groovescript.ast_nodes import Groove, Metadata, PatternLine, Section, Song, StarSpec
from groovescript.compiler import IRBar, IRGroove, IRSong, compile_groove, compile_song, Event
from groovescript.midi import (
    TICKS_PER_BEAT,
    _VEL_DEFAULT,
    _bar_ticks,
    _build_track,
    _timesig_event,
    _tempo_event,
    _vlq,
    emit_midi,
)
from groovescript.parser import parse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_midi_header(data: bytes) -> tuple[int, int, int]:
    """Parse the 14-byte MIDI header; return (format, ntrks, ticks_per_beat)."""
    assert data[:4] == b"MThd"
    chunk_len = struct.unpack(">I", data[4:8])[0]
    assert chunk_len == 6
    fmt, ntrks, tpb = struct.unpack(">HHH", data[8:14])
    return fmt, ntrks, tpb


def _parse_tracks(data: bytes) -> list[bytes]:
    """Return the raw body bytes (after the MTrk+length header) for each track."""
    tracks = []
    offset = 14  # skip MThd chunk
    while offset < len(data):
        assert data[offset:offset + 4] == b"MTrk", f"Expected MTrk at offset {offset}"
        length = struct.unpack(">I", data[offset + 4:offset + 8])[0]
        body = data[offset + 8:offset + 8 + length]
        tracks.append(body)
        offset += 8 + length
    return tracks


def _collect_note_on(track_body: bytes) -> list[tuple[int, int, int]]:
    """Return all Note On events as (absolute_tick, pitch, velocity).

    Parses variable-length delta times and handles the note-on message
    format (0x9n pp vv). Zero-velocity note-ons are excluded (they are
    treated as note-offs by MIDI convention).
    """
    notes = []
    pos = 0
    abs_tick = 0
    while pos < len(track_body):
        # Read variable-length delta
        delta = 0
        while True:
            b = track_body[pos]
            pos += 1
            delta = (delta << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
        abs_tick += delta

        if pos >= len(track_body):
            break
        status = track_body[pos]
        if status == 0xFF:
            # Meta event — skip
            pos += 1
            meta_type = track_body[pos]; pos += 1
            # Read meta length (VLQ)
            meta_len = 0
            while True:
                b = track_body[pos]; pos += 1
                meta_len = (meta_len << 7) | (b & 0x7F)
                if not (b & 0x80):
                    break
            pos += meta_len
        elif (status & 0xF0) == 0x90:
            # Note On
            pos += 1
            pitch = track_body[pos]; pos += 1
            vel = track_body[pos]; pos += 1
            if vel > 0:
                notes.append((abs_tick, pitch, vel))
        elif (status & 0xF0) == 0x80:
            # Note Off
            pos += 3
        else:
            # Other channel message (skip 2 data bytes for most)
            pos += 3
    return notes


def _collect_note_off(track_body: bytes) -> list[tuple[int, int]]:
    """Return (absolute_tick, pitch) for every Note Off event.

    Zero-velocity Note Ons are also treated as Note Offs per MIDI convention.
    """
    offs = []
    pos = 0
    abs_tick = 0
    while pos < len(track_body):
        delta = 0
        while True:
            b = track_body[pos]
            pos += 1
            delta = (delta << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
        abs_tick += delta
        if pos >= len(track_body):
            break
        status = track_body[pos]
        if status == 0xFF:
            pos += 1
            pos += 1  # meta type
            meta_len = 0
            while True:
                b = track_body[pos]; pos += 1
                meta_len = (meta_len << 7) | (b & 0x7F)
                if not (b & 0x80):
                    break
            pos += meta_len
        elif (status & 0xF0) == 0x80:
            pos += 1
            pitch = track_body[pos]; pos += 1
            pos += 1  # velocity
            offs.append((abs_tick, pitch))
        elif (status & 0xF0) == 0x90:
            pos += 1
            pitch = track_body[pos]; pos += 1
            vel = track_body[pos]; pos += 1
            if vel == 0:
                offs.append((abs_tick, pitch))
        else:
            pos += 3
    return offs


# ---------------------------------------------------------------------------
# Unit tests: binary primitives
# ---------------------------------------------------------------------------

def test_vlq_zero():
    assert _vlq(0) == b"\x00"


def test_vlq_single_byte():
    assert _vlq(127) == b"\x7F"


def test_vlq_two_bytes():
    # 128 encodes to 0x81 0x00
    assert _vlq(128) == b"\x81\x00"


def test_vlq_multibyte():
    # 0x3FFF = 16383 → 0xFF 0x7F
    assert _vlq(16383) == b"\xFF\x7F"


def test_bar_ticks_4_4():
    assert _bar_ticks("4/4") == 4 * TICKS_PER_BEAT


def test_bar_ticks_3_4():
    assert _bar_ticks("3/4") == 3 * TICKS_PER_BEAT


def test_bar_ticks_6_8():
    assert _bar_ticks("6/8") == 3 * TICKS_PER_BEAT  # 6 eighth notes = 3 quarter notes


def test_timesig_event_structure():
    evt = _timesig_event("4/4")
    assert evt[0:2] == bytes([0xFF, 0x58])
    assert evt[2] == 4   # data length
    assert evt[3] == 4   # numerator
    assert evt[4] == 2   # denominator as log2(4)


def test_tempo_event_structure():
    evt = _tempo_event(120)
    assert evt[0:3] == bytes([0xFF, 0x51, 0x03])
    usec = int.from_bytes(evt[3:6], "big")
    assert usec == 500_000  # 120 BPM = 500 000 µs/beat


# ---------------------------------------------------------------------------
# MIDI file structure tests
# ---------------------------------------------------------------------------

def _make_money_beat_groove() -> IRGroove:
    g = Groove(
        name="money beat",
        bars=[[
            PatternLine(instrument="BD", beats=["1", "3"]),
            PatternLine(instrument="SN", beats=["2", "4"]),
            PatternLine(instrument="HH", beats=StarSpec(note_value=8)),
        ]],
    )
    return compile_groove(g)


def test_emit_midi_groove_header():
    """Output starts with a valid MIDI header (Format 1, 2 tracks, correct PPQ)."""
    data = emit_midi(_make_money_beat_groove())
    fmt, ntrks, tpb = _parse_midi_header(data)
    assert fmt == 1
    assert ntrks == 2
    assert tpb == TICKS_PER_BEAT


def test_emit_midi_groove_two_tracks():
    data = emit_midi(_make_money_beat_groove())
    tracks = _parse_tracks(data)
    assert len(tracks) == 2


def test_emit_midi_groove_has_bd_sn_hh():
    """Drum track contains Note On events for BD (36), SN (38), and HH (42)."""
    data = emit_midi(_make_money_beat_groove())
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    pitches = {n[1] for n in notes}
    assert 36 in pitches, "BD (pitch 36) missing"
    assert 38 in pitches, "SN (pitch 38) missing"
    assert 42 in pitches, "HH (pitch 42) missing"


def test_emit_midi_groove_bd_on_beats_1_3():
    """BD hits fall on beat 1 (tick 0) and beat 3 (tick 2*TICKS_PER_BEAT) in 4/4."""
    data = emit_midi(_make_money_beat_groove())
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    bd_ticks = sorted(t for t, p, v in notes if p == 36)
    assert bd_ticks == [0, 2 * TICKS_PER_BEAT]


def test_emit_midi_groove_sn_on_beats_2_4():
    """SN hits fall on beat 2 (tick TICKS_PER_BEAT) and beat 4 (tick 3*TICKS_PER_BEAT)."""
    data = emit_midi(_make_money_beat_groove())
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    sn_ticks = sorted(t for t, p, v in notes if p == 38)
    assert sn_ticks == [TICKS_PER_BEAT, 3 * TICKS_PER_BEAT]


def test_emit_midi_groove_hh_eight_hits():
    """HH at *8 produces 8 evenly-spaced hits across the bar in 4/4."""
    data = emit_midi(_make_money_beat_groove())
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    hh_ticks = sorted(t for t, p, v in notes if p == 42)
    assert len(hh_ticks) == 8
    step = TICKS_PER_BEAT // 2  # eighth note
    assert hh_ticks == [i * step for i in range(8)]


# ---------------------------------------------------------------------------
# IRSong path
# ---------------------------------------------------------------------------

ARRANGEMENT_SRC = """\
metadata:
  title: "Test"
  tempo: 100
  time_signature: 4/4

groove "beat":
  BD: 1, 3
  SN: 2, 4
  HH: *8

section "verse":
  bars: 2
  groove: "beat"
"""


def test_emit_midi_song_header():
    ir = compile_song(parse(ARRANGEMENT_SRC))
    data = emit_midi(ir)
    fmt, ntrks, tpb = _parse_midi_header(data)
    assert fmt == 1
    assert ntrks == 2
    assert tpb == TICKS_PER_BEAT


def test_emit_midi_song_tempo_in_track_0():
    """Track 0 of an IRSong contains a tempo meta event matching the metadata BPM."""
    ir = compile_song(parse(ARRANGEMENT_SRC))
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    # Check the raw tempo event is present in track 0 bytes
    # 100 BPM = 600 000 µs/beat → 0x09 0x27 0xC0
    usec = round(60_000_000 / 100)
    usec_bytes = usec.to_bytes(3, "big")
    assert b"\xFF\x51\x03" + usec_bytes in tracks[0]


def test_emit_midi_song_two_bars_of_notes():
    """A 2-bar arrangement produces BD hits across both bars."""
    ir = compile_song(parse(ARRANGEMENT_SRC))
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    bd_ticks = sorted(t for t, p, v in notes if p == 36)
    bar_len = _bar_ticks("4/4")
    # Beat 1 of bar 1 and bar 2; beat 3 of bar 1 and bar 2
    expected = sorted([0, 2 * TICKS_PER_BEAT, bar_len, bar_len + 2 * TICKS_PER_BEAT])
    assert bd_ticks == expected


# ---------------------------------------------------------------------------
# Modifier: accent / ghost velocity
# ---------------------------------------------------------------------------

def test_accent_velocity():
    """Accent modifier produces a higher MIDI velocity."""
    src = """\
groove "g":
  SN: 2 accent
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    sn_notes = [v for t, p, v in notes if p == 38]
    assert sn_notes, "No SN notes found"
    assert max(sn_notes) >= 100


def test_ghost_velocity():
    """Ghost modifier produces a lower MIDI velocity."""
    src = """\
groove "g":
  SN: 2 ghost
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    sn_notes = [v for t, p, v in notes if p == 38]
    assert sn_notes, "No SN notes found"
    assert min(sn_notes) <= 40


# ---------------------------------------------------------------------------
# Modifier: flam (grace note before main hit)
# ---------------------------------------------------------------------------

def test_flam_produces_two_sn_events():
    """Flam on SN produces 2 note-on events (grace + main) at different ticks."""
    src = """\
groove "g":
  SN: 2 flam
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    sn_notes = [(t, v) for t, p, v in notes if p == 38]
    assert len(sn_notes) == 2
    ticks = sorted(t for t, v in sn_notes)
    # Grace note must come strictly before main note
    assert ticks[0] < ticks[1]


def test_flam_on_toms_produces_grace_and_main():
    """Regression: flam modifier is supported on all toms (FT, HT, MT), not only SN.

    Each flammed tom hit should produce 2 note-on events: a grace stroke and the
    main hit, with the grace arriving strictly before the main.
    """
    # GM MIDI pitches: FT=41, HT=50, MT=45
    for instrument, pitch in (("FT", 41), ("HT", 50), ("MT", 45)):
        src = f"""\
groove "g":
  {instrument}: 2 flam
"""
        ir = compile_groove(parse(src).grooves[0])
        data = emit_midi(ir)
        tracks = _parse_tracks(data)
        notes = _collect_note_on(tracks[1])
        tom_notes = [(t, v) for t, p, v in notes if p == pitch]
        assert len(tom_notes) == 2, f"{instrument} flam should produce 2 events"
        ticks = sorted(t for t, v in tom_notes)
        assert ticks[0] < ticks[1], f"{instrument} grace note must precede main note"


# ---------------------------------------------------------------------------
# Modifier: double (second stroke one 32nd note after main)
# ---------------------------------------------------------------------------

def test_double_produces_two_sn_events():
    """Double on SN produces 2 note-on events separated by a 32nd note."""
    src = """\
groove "g":
  SN: 2, 4
  HH: *16
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    # All SN note-ons before applying double (no double modifier here)
    notes_before = _collect_note_on(tracks[1])

    src_double = """\
groove "g":
  SN: 2 double, 4
  HH: *16
"""
    ir2 = compile_groove(parse(src_double).grooves[0])
    data2 = emit_midi(ir2)
    tracks2 = _parse_tracks(data2)
    notes_after = _collect_note_on(tracks2[1])

    # The double adds one extra note-on for SN
    sn_before = [t for t, p, v in notes_before if p == 38]
    sn_after = [t for t, p, v in notes_after if p == 38]
    assert len(sn_after) == len(sn_before) + 1

    # The two SN hits from beat 2 should be separated by exactly 1/32 note
    beat2_tick = TICKS_PER_BEAT  # beat 2 of 4/4
    beat2_sn = sorted(t for t in sn_after if abs(t - beat2_tick) <= TICKS_PER_BEAT // 8 + 1)
    assert len(beat2_sn) == 2
    assert beat2_sn[1] - beat2_sn[0] == TICKS_PER_BEAT // 8  # 1/32 note


# ---------------------------------------------------------------------------
# Instrument mapping: all known instruments produce note events
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("instrument,expected_pitch", [
    ("BD",  36),
    ("SN",  38),
    ("SCS", 37),
    ("HH",  42),
    ("OH",  46),
    ("HF",  44),
    ("RD",  51),
    ("CR",  49),
    ("FT",  41),
    ("HT",  50),
    ("MT",  45),
])
def test_instrument_pitch_mapping(instrument, expected_pitch):
    """Each instrument maps to its expected GM drum pitch."""
    src = f"""\
groove "g":
  {instrument}: 1
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    pitches = {p for t, p, v in notes}
    assert expected_pitch in pitches, f"{instrument} should map to pitch {expected_pitch}"


# ---------------------------------------------------------------------------
# Tempo changes per section
# ---------------------------------------------------------------------------

def test_tempo_change_between_sections():
    """A per-section tempo change emits a new tempo meta event at the right tick."""
    src = """\
metadata:
  tempo: 120
  time_signature: 4/4

groove "beat":
  BD: 1, 3
  SN: 2, 4

section "A":
  bars: 1
  groove: "beat"

section "B":
  bars: 1
  groove: "beat"
  tempo: 160
"""
    ir = compile_song(parse(src))
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    # 160 BPM = 375 000 µs/beat
    usec_160 = round(60_000_000 / 160)
    usec_bytes = usec_160.to_bytes(3, "big")
    assert b"\xFF\x51\x03" + usec_bytes in tracks[0]


# ---------------------------------------------------------------------------
# Time signature changes
# ---------------------------------------------------------------------------

def test_time_signature_change_emits_event():
    """A section with a different time signature emits a new time-sig event."""
    src = """\
metadata:
  tempo: 120
  time_signature: 4/4

groove "beat4":
  BD: 1, 3
  SN: 2, 4

groove "beat3":
  BD: 1
  SN: 2, 3

section "A":
  bars: 1
  groove: "beat4"

section "B":
  bars: 1
  groove: "beat3"
  time_signature: 3/4
"""
    ir = compile_song(parse(src))
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    # 3/4 time sig → numerator=3, denominator log2(4)=2
    ts_3_4 = bytes([0xFF, 0x58, 0x04, 3, 2, 24, 8])
    assert ts_3_4 in tracks[0]


# ---------------------------------------------------------------------------
# Rest bars produce no note events
# ---------------------------------------------------------------------------

def test_rest_bar_emits_no_notes():
    """A play: rest bar produces no drum note events."""
    src = """\
metadata:
  tempo: 120
  time_signature: 4/4

groove "beat":
  BD: 1, 3
  SN: 2, 4

section "intro":
  play:
    groove "beat" x1
    rest x1
"""
    ir = compile_song(parse(src))
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    bar_len = _bar_ticks("4/4")
    # No note-on events should fall in bar 2 (ticks bar_len .. 2*bar_len)
    bar2_notes = [t for t, p, v in notes if bar_len <= t < 2 * bar_len]
    assert bar2_notes == []


# ---------------------------------------------------------------------------
# Modifier: drag (two grace notes before main hit)
# ---------------------------------------------------------------------------

def test_drag_produces_three_sn_events():
    """Drag on SN produces 3 note-on events: two grace strokes + the main hit.

    Regression: prior to coverage being added, drag was implemented in the
    exporter but never exercised by tests, so a regression in the grace-note
    spacing or velocity could have slipped through.
    """
    src = """\
groove "g":
  SN: 2 drag
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    sn = sorted((t, v) for t, p, v in notes if p == 38)
    assert len(sn) == 3
    ticks = [t for t, v in sn]
    # Two grace strokes precede the main hit, evenly spaced
    assert ticks[0] < ticks[1] < ticks[2]
    # Grace strokes use the lower grace velocity, main uses default
    assert sn[0][1] < _VEL_DEFAULT
    assert sn[1][1] < _VEL_DEFAULT
    assert sn[2][1] == _VEL_DEFAULT


# ---------------------------------------------------------------------------
# Modifier: buzz roll (sustained note over a span)
# ---------------------------------------------------------------------------

def test_buzz_roll_emits_one_note_on_and_one_note_off():
    """A half-note buzz on SN at beat 1 produces a single note-on at tick 0
    and a single note-off two beats later — not a stream of restrikes.
    """
    src = """\
groove "g":
  SN: 1 buzz:2
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    sn_ons = [(t, v) for t, p, v in _collect_note_on(tracks[1]) if p == 38]
    sn_offs = [t for t, p in _collect_note_off(tracks[1]) if p == 38]
    assert len(sn_ons) == 1
    assert sn_ons[0][0] == 0
    assert len(sn_offs) == 1
    # Half-note span = 2 beats = 2 * TICKS_PER_BEAT
    assert sn_offs[0] == 2 * TICKS_PER_BEAT


def test_buzz_roll_ties_across_bars():
    """A buzz roll that starts in bar 1 and ties into bar 2 should produce one
    note-on in bar 1 and one note-off in bar 2 — never an extra restrike at
    the bar line.
    """
    src = """\
metadata:
  tempo: 120
  time_signature: 4/4

groove "buzz across":
  bar 1:
    SN: 4 buzz:2
  bar 2:
    SN: 2, 4

section "A":
  bars: 2
  groove: "buzz across"
"""
    ir = compile_song(parse(src))
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    bar_len = _bar_ticks("4/4")
    sn_ons = sorted(t for t, p, v in _collect_note_on(tracks[1]) if p == 38)
    sn_offs = sorted(t for t, p in _collect_note_off(tracks[1]) if p == 38)
    # Note-ons: buzz start (beat 4 of bar 1), then beat 2 and beat 4 of bar 2.
    # The cross-bar buzz must NOT add a second buzz note-on at bar 2 beat 1.
    assert sn_ons[0] == 3 * TICKS_PER_BEAT
    assert bar_len + TICKS_PER_BEAT in sn_ons
    assert bar_len + 3 * TICKS_PER_BEAT in sn_ons
    # The buzz note-off lands one beat into bar 2 (start tick + 2 beats)
    assert (3 * TICKS_PER_BEAT + 2 * TICKS_PER_BEAT) in sn_offs


# ---------------------------------------------------------------------------
# Cymbal sustain: rides, crashes, open hi-hats ring until next strike
# ---------------------------------------------------------------------------

def test_crash_rings_to_next_strike():
    """Two crashes in a 2-bar arrangement: the first crash's note-off lands
    just before the second crash, not 30 ticks after the first.
    """
    src = """\
metadata:
  tempo: 120
  time_signature: 4/4

groove "g":
  CR: 1
  BD: 1, 3
  SN: 2, 4

section "A":
  bars: 2
  groove: "g"
"""
    ir = compile_song(parse(src))
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    bar_len = _bar_ticks("4/4")
    cr_ons = sorted(t for t, p, v in _collect_note_on(tracks[1]) if p == 49)
    cr_offs = sorted(t for t, p in _collect_note_off(tracks[1]) if p == 49)
    assert cr_ons == [0, bar_len]
    # Two strikes → two note-offs. First off is just before second strike,
    # second off rings out past the song's end.
    assert len(cr_offs) == 2
    assert bar_len - 32 < cr_offs[0] < bar_len, (
        f"first crash should ring nearly until tick {bar_len}, got {cr_offs[0]}"
    )
    # Tail must extend past song end (2 bars = 2 * bar_len)
    assert cr_offs[1] >= 2 * bar_len


def test_single_crash_rings_past_song_end():
    """A lone crash with no follow-up gets a tail extension past song end."""
    src = """\
groove "g":
  CR: 1
  BD: 1
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    bar_len = _bar_ticks("4/4")
    cr_offs = [t for t, p in _collect_note_off(tracks[1]) if p == 49]
    assert len(cr_offs) == 1
    assert cr_offs[0] > bar_len, "crash should ring past the bar's end"


def test_ride_and_open_hat_also_sustain():
    """Ride (51) and open hi-hat (46) follow the same sustain rule as crash."""
    for instrument, pitch in (("RD", 51), ("OH", 46)):
        src = f"""\
groove "g":
  {instrument}: 1, 3
  BD: 1
"""
        ir = compile_groove(parse(src).grooves[0])
        data = emit_midi(ir)
        tracks = _parse_tracks(data)
        offs = sorted(t for t, p in _collect_note_off(tracks[1]) if p == pitch)
        ons = sorted(t for t, p, v in _collect_note_on(tracks[1]) if p == pitch)
        assert len(ons) == 2
        assert len(offs) == 2
        # First off is right before second strike, not 30 ticks after first
        assert offs[0] > ons[0] + 30, (
            f"{instrument}: expected sustain past 30 ticks, got off at {offs[0]}"
        )


def test_closed_hat_does_not_sustain():
    """Closed hi-hat (42) is percussive and keeps its short note-off."""
    src = """\
groove "g":
  HH: *4
"""
    ir = compile_groove(parse(src).grooves[0])
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    ons = sorted(t for t, p, v in _collect_note_on(tracks[1]) if p == 42)
    offs = sorted(t for t, p in _collect_note_off(tracks[1]) if p == 42)
    assert len(ons) == 4
    assert len(offs) == 4
    # Each off lands exactly _HIT_DURATION after its on
    for on, off in zip(ons, offs):
        assert off - on == 30


# ---------------------------------------------------------------------------
# Regression: unknown instrument does not crash the exporter
# ---------------------------------------------------------------------------

def test_unknown_instrument_is_silently_skipped():
    """An Event with an unknown instrument name is skipped without raising."""
    from groovescript.ast_nodes import Metadata
    bar = IRBar(
        number=1,
        subdivision=8,
        events=[
            Event(bar=1, beat_position=Fraction(0), instrument="UNKNOWN"),
            Event(bar=1, beat_position=Fraction(1, 4), instrument="BD"),
        ],
        time_signature="4/4",
    )
    ir = IRSong(
        metadata=Metadata(tempo=120, time_signature="4/4"),
        bars=[bar],
        sections=[],
    )
    data = emit_midi(ir)
    tracks = _parse_tracks(data)
    notes = _collect_note_on(tracks[1])
    pitches = {p for t, p, v in notes}
    assert 36 in pitches          # BD note present
    assert len(pitches) == 1      # only BD, no mystery pitch
