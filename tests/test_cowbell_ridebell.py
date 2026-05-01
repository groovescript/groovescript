"""Tests for cowbell (CB) and ride bell (RB) instrument support.

Covers parsing aliases, compiler validation (mutex with RD/HH/OH), and the
end-to-end LilyPond / MIDI / MusicXML emission paths.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from groovescript.compiler import compile_groove, compile_song
from groovescript.errors import GrooveScriptError
from groovescript.lilypond import emit_lilypond
from groovescript.midi import emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.parser import parse


# ── Parser: alias normalisation ──────────────────────────────────────────


@pytest.mark.parametrize(
    "alias,canonical",
    [
        ("CB", "CB"),
        ("cb", "CB"),
        ("cowbell", "CB"),
        ("RB", "RB"),
        ("rb", "RB"),
        ("ridebell", "RB"),
        ("bell", "RB"),
    ],
)
def test_alias_normalises_to_canonical(alias: str, canonical: str) -> None:
    """Each documented alias for cowbell and ride bell normalises to the
    canonical abbreviation.
    """
    src = f"""\
groove "g":
    {alias}: 1, 3
"""
    song = parse(src)
    line = song.grooves[0].pattern[0]
    assert line.instrument == canonical


def test_bell_alias_is_ride_bell_not_cowbell() -> None:
    """Regression: ``bell`` is reserved for ride bell so the bare token does
    not silently bind to cowbell.
    """
    src = """\
groove "g":
    bell: 1, 3
"""
    song = parse(src)
    assert song.grooves[0].pattern[0].instrument == "RB"


# ── Compiler: mutex rule between same-physical-instrument pairs ──────────


def test_rd_and_rb_at_same_position_is_rejected() -> None:
    """RD (ride bow) and RB (ride bell) cannot sound on the same beat — they
    are the same cymbal struck in different places.
    """
    src = """\
groove "bad":
    BD: 1, 3
    SN: 2, 4
    RD: 1, 2, 3, 4
    RB: 3
"""
    with pytest.raises(GrooveScriptError, match="RB and RD cannot sound at the same beat"):
        compile_groove(parse(src).grooves[0])


def test_hh_and_oh_at_same_position_is_rejected() -> None:
    """Regression: HH (closed hi-hat) and OH (open hi-hat) describe the same
    hi-hat with mutually exclusive articulations and cannot stack on one beat.
    """
    src = """\
groove "bad":
    BD: 1, 3
    SN: 2, 4
    HH: 1
    OH: 1
"""
    with pytest.raises(GrooveScriptError, match="HH and OH cannot sound at the same beat"):
        compile_groove(parse(src).grooves[0])


def test_hh_and_oh_via_position_to_instruments_line_is_rejected() -> None:
    """Regression: the position→instruments style (``1: HH OH``) hits the
    same mutex check as the instrument→positions style.
    """
    src = """\
groove "bad":
    BD: 1, 3
    SN: 2, 4
    1: HH OH
"""
    with pytest.raises(GrooveScriptError, match="HH and OH cannot sound"):
        compile_groove(parse(src).grooves[0])


def test_hh_and_oh_on_different_beats_is_allowed() -> None:
    """HH and OH are fine when they occupy distinct beat positions; the
    mutex rule fires only when they share a position.
    """
    src = """\
groove "ok":
    BD: 1, 3
    SN: 2, 4
    HH: *16 except 2a, 4a
    OH: 2a, 4a
"""
    ir = compile_groove(parse(src).grooves[0])
    instruments_at = {(e.beat_position, e.instrument) for e in ir.events}
    assert (Fraction(7, 16), "OH") in instruments_at
    assert (Fraction(7, 16), "HH") not in instruments_at


def test_cowbell_and_ridebell_can_coexist() -> None:
    """CB and RB are different physical instruments and may share a beat."""
    src = """\
groove "latin":
    BD: 1, 3
    CB: *4
    RB: 1, 3
"""
    ir = compile_groove(parse(src).grooves[0])
    cb_hits = [e for e in ir.events if e.instrument == "CB"]
    rb_hits = [e for e in ir.events if e.instrument == "RB"]
    assert len(cb_hits) == 4
    assert len(rb_hits) == 2


def test_rb_replacing_rd_on_a_beat_is_allowed_via_variation() -> None:
    """A variation that removes RD before adding RB lets the bell sound on
    a beat the bow used to occupy without tripping the mutex check.
    """
    src = """\
groove "ride":
    BD: 1, 3
    SN: 2, 4
    RD: *4

section "verse":
    bars: 1
    groove: "ride"
    variation at bar 1:
      remove RD at 3
      add RB at 3
"""
    song = parse(src)
    ir = compile_song(song)
    bar1_events = ir.bars[0].events
    at_three = [e for e in bar1_events if e.beat_position == Fraction(1, 2)]
    instruments = {e.instrument for e in at_three}
    assert "RB" in instruments
    assert "RD" not in instruments


# ── LilyPond emission ────────────────────────────────────────────────────


def test_lilypond_emits_cb_and_rb_drum_names() -> None:
    """CB compiles to LilyPond ``cb`` and RB to ``rb`` (both built-in
    drum-name aliases for cowbell and ridebell respectively).
    """
    src = """\
title: "demo"
tempo: 120

groove "g":
    BD: 1, 3
    SN: 2, 4
    CB: *4
    RB: 1, 3

section "verse":
    bars: 1
    groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    # The drum-style table must define cowbell (triangle, position 6)
    # and ridebell (harmonic/diamond, position 4).
    assert "(cowbell triangle #f 6)" in ly
    assert "(ridebell harmonic #f 4)" in ly
    # The body must reference cb and rb drum names.
    assert "cb" in ly
    assert "rb" in ly


# ── MIDI emission ────────────────────────────────────────────────────────


def test_midi_uses_general_midi_cowbell_and_ridebell_notes() -> None:
    """CB → GM 56 (Cowbell), RB → GM 53 (Ride Bell). We assert by scanning
    the emitted track bytes for the corresponding note-on velocities.
    """
    src = """\
title: "demo"
tempo: 120

groove "g":
    CB: 1
    RB: 1

section "verse":
    bars: 1
    groove: "g"
"""
    midi_bytes = emit_midi(compile_song(parse(src)))
    # Note-on bytes (channel 10 = 0x99) followed by pitch followed by velocity.
    # Locate at least one 0x99 <pitch> <velocity> triple per pitch.
    assert b"\x99\x38" in midi_bytes  # 0x38 = 56 = cowbell
    assert b"\x99\x35" in midi_bytes  # 0x35 = 53 = ride bell


# ── MusicXML emission ────────────────────────────────────────────────────


def test_musicxml_uses_triangle_for_cb_and_diamond_for_rb() -> None:
    """The MusicXML export sets <notehead> to ``triangle`` for cowbell and
    ``diamond`` for ride bell so XML readers render them with the
    standard percussion shapes.
    """
    src = """\
title: "demo"
tempo: 120

groove "g":
    CB: 1
    RB: 1

section "verse":
    bars: 1
    groove: "g"
"""
    xml = emit_musicxml(compile_song(parse(src))).decode()
    assert "<notehead>triangle</notehead>" in xml
    assert "<notehead>diamond</notehead>" in xml
