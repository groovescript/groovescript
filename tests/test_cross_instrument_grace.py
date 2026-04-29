"""Cross-instrument flam/drag (``flam:<inst>`` / ``drag:<inst>``).

Covers the parameterised modifier form that lets the grace stroke(s) play
on a different instrument than the main hit, plus the tightening that
brings ``drag``'s instrument restriction in line with ``flam``.
"""

from fractions import Fraction

import pytest

from groovescript.compiler import compile_song
from groovescript.errors import GrooveScriptError
from groovescript.lilypond import emit_lilypond
from groovescript.midi import emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.parser import parse


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def test_parse_pattern_line_flam_with_grace_inst():
    """``HT: 1 flam:SN`` parses as a hi-tom hit with a snare grace target."""
    song = parse("""\
groove "g":
    HT: 1 flam:SN
""")
    beat = song.grooves[0].bars[0][0].beats[0]
    assert beat.label == "1"
    assert beat.modifiers == ["flam"]
    assert beat.grace_instrument == "SN"


def test_parse_pattern_line_drag_with_grace_inst():
    """``RD: 2 drag:SN`` parses as a ride hit with a snare drag target."""
    song = parse("""\
groove "g":
    RD: 2 drag:SN
""")
    beat = song.grooves[0].bars[0][0].beats[0]
    assert beat.modifiers == ["drag"]
    assert beat.grace_instrument == "SN"


def test_parse_pos_line_flam_with_grace_inst():
    """Position→instruments line accepts ``HT flam:SN`` as a single hit spec."""
    song = parse("""\
groove "g":
    1: HT flam:SN
""")
    line = song.grooves[0].bars[0][0]
    assert line.instrument == "HT"
    assert line.beats[0].modifiers == ["flam"]
    assert line.beats[0].grace_instrument == "SN"


def test_parse_count_notes_flam_with_grace_inst():
    """Count+notes form accepts ``HT flam:SN`` inside the notes string."""
    song = parse("""\
fill "f":
  count: "1 e & a"
  notes: "HT flam:SN, SN, BD, CR"

groove "g":
    BD: 1

section "v":
  bars: 1
  groove: "g"
  fill "f" at bar 1
""")
    fill = song.fills[0]
    first = fill.bars[0].lines[0]
    assert first.beat == "1"
    assert first.instruments[0].instrument == "HT"
    assert first.instruments[0].modifiers == ["flam"]
    assert first.instruments[0].grace_instrument == "SN"


def test_parse_long_form_grace_instrument_normalises():
    """``flam:snare`` (long-form alias) normalises the grace target to ``SN``."""
    song = parse("""\
groove "g":
    HT: 1 flam:snare
""")
    beat = song.grooves[0].bars[0][0].beats[0]
    assert beat.grace_instrument == "SN"


# ---------------------------------------------------------------------------
# Compiler — happy path
# ---------------------------------------------------------------------------

def test_compile_cross_instrument_flam_event_carries_grace():
    src = """\
groove "g":
    HT: 1 flam:SN

section "a":
  bars: 1
  groove: "g"
"""
    song = compile_song(parse(src))
    events = [e for e in song.bars[0].events if e.instrument == "HT"]
    assert len(events) == 1
    assert events[0].modifiers == ["flam"]
    assert events[0].grace_instrument == "SN"


def test_compile_same_instrument_flam_with_explicit_arg_normalises():
    """``snare flam:snare`` is accepted and treated like bare ``snare flam``."""
    src = """\
groove "g":
    SN: 1 flam:snare

section "a":
  bars: 1
  groove: "g"
"""
    song = compile_song(parse(src))
    ev = song.bars[0].events[0]
    assert ev.instrument == "SN"
    assert ev.modifiers == ["flam"]
    assert ev.grace_instrument == "SN"


# ---------------------------------------------------------------------------
# Compiler — validation errors
# ---------------------------------------------------------------------------

def test_compile_drag_on_cymbal_rejected():
    """Bare ``drag`` requires the main hit to be a snare/tom (matches flam)."""
    src = """\
groove "g":
    CR: 1 drag

section "a":
  bars: 1
  groove: "g"
"""
    with pytest.raises(GrooveScriptError, match="drag.*snare and toms"):
        compile_song(parse(src))


def test_compile_drag_on_bass_rejected():
    """Drag on bass drum is now rejected (was silently accepted before)."""
    src = """\
groove "g":
    BD: 1 drag

section "a":
  bars: 1
  groove: "g"
"""
    with pytest.raises(GrooveScriptError, match="drag.*snare and toms"):
        compile_song(parse(src))


def test_compile_flam_grace_instrument_must_be_grace_capable():
    """``flam:CR`` is rejected — cymbals can't carry a grace stroke."""
    src = """\
groove "g":
    HT: 1 flam:CR

section "a":
  bars: 1
  groove: "g"
"""
    with pytest.raises(
        GrooveScriptError, match="grace instrument must be a snare or tom"
    ):
        compile_song(parse(src))


def test_compile_drag_grace_instrument_must_be_grace_capable():
    """``drag:CR`` is rejected for the same reason as ``flam:CR``."""
    src = """\
groove "g":
    HT: 1 drag:CR

section "a":
  bars: 1
  groove: "g"
"""
    with pytest.raises(
        GrooveScriptError, match="grace instrument must be a snare or tom"
    ):
        compile_song(parse(src))


def test_compile_two_flams_at_same_position_rejected():
    """A flam uses both hands; two simultaneous flams would need three hands."""
    src = """\
groove "g":
    HT: 1 flam:SN
    SN: 1 flam

section "a":
  bars: 1
  groove: "g"
"""
    with pytest.raises(
        GrooveScriptError, match="more than one flam/drag"
    ):
        compile_song(parse(src))


def test_compile_flam_distributed_over_chord_rejected():
    """``(snare crash) flam:SN`` distributes flam to two main hits — invalid."""
    src = """\
fill "f":
  count: "1"
  notes: "(snare crash) flam:SN"

groove "g":
    BD: 1

section "a":
  bars: 1
  groove: "g"
  fill "f" at bar 1
"""
    with pytest.raises(GrooveScriptError, match="more than one flam/drag"):
        compile_song(parse(src))


def test_compile_chord_with_one_inner_flam_allowed():
    """Inside a paren chord, attaching the flam to a single member is fine."""
    src = """\
fill "f":
  count: "1"
  notes: "(snare flam:SN bass)"

groove "g":
    BD: 2

section "a":
  bars: 1
  groove: "g"
  fill "f" at bar 1
"""
    song = compile_song(parse(src))
    flam_events = [
        e for e in song.bars[0].events if "flam" in e.modifiers
    ]
    assert len(flam_events) == 1
    assert flam_events[0].instrument == "SN"
    assert flam_events[0].grace_instrument == "SN"


# ---------------------------------------------------------------------------
# Variation actions
# ---------------------------------------------------------------------------

def test_variation_add_with_cross_instrument_flam():
    src = """\
groove "g":
    BD: 1, 3

section "a":
  bars: 1
  groove: "g"
  variation at bar 1:
    add HT flam:SN at 2
"""
    song = compile_song(parse(src))
    ht_events = [e for e in song.bars[0].events if e.instrument == "HT"]
    assert len(ht_events) == 1
    assert ht_events[0].modifiers == ["flam"]
    assert ht_events[0].grace_instrument == "SN"


def test_variation_modify_add_cross_instrument_flam():
    src = """\
groove "g":
    HT: 2

section "a":
  bars: 1
  groove: "g"
  variation at bar 1:
    modify add flam:SN to HT at 2
"""
    song = compile_song(parse(src))
    ev = next(e for e in song.bars[0].events if e.instrument == "HT")
    assert ev.modifiers == ["flam"]
    assert ev.grace_instrument == "SN"


def test_variation_replace_with_cross_instrument_drag():
    src = """\
groove "g":
    HH: 1, 2, 3, 4

section "a":
  bars: 1
  groove: "g"
  variation at bar 1:
    replace HH with RD drag:SN at 4
"""
    song = compile_song(parse(src))
    rd_events = [e for e in song.bars[0].events if e.instrument == "RD"]
    assert len(rd_events) == 1
    assert rd_events[0].modifiers == ["drag"]
    assert rd_events[0].grace_instrument == "SN"


def test_variation_modify_remove_clears_grace_instrument():
    """Removing the ornament should also clear the grace target."""
    src = """\
groove "g":
    HT: 1 flam:SN

section "a":
  bars: 1
  groove: "g"
  variation at bar 1:
    modify remove flam from HT at 1
"""
    song = compile_song(parse(src))
    ev = next(e for e in song.bars[0].events if e.instrument == "HT")
    assert "flam" not in ev.modifiers
    assert ev.grace_instrument is None


# ---------------------------------------------------------------------------
# Emitters — LilyPond
# ---------------------------------------------------------------------------

def test_lilypond_cross_instrument_flam_uses_grace_inst_pitch():
    """The ``\\slashedGrace`` token uses the grace inst's LilyPond name."""
    src = """\
groove "g":
    HT: 1 flam:SN

section "a":
  bars: 1
  groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\slashedGrace sn16" in ly  # grace plays on snare
    assert "tomh" in ly                  # main hit on hi-tom


def test_lilypond_cross_instrument_drag_uses_grace_inst_pitch():
    src = """\
groove "g":
    RD: 2 drag:SN

section "a":
  bars: 1
  groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\grace { sn16 sn16 }" in ly  # two snare graces
    assert "cymr" in ly                    # main hit on ride


def test_lilypond_same_instrument_flam_unchanged():
    """``snare flam`` (no arg) keeps the legacy ``\\slashedGrace sn16`` form."""
    src = """\
groove "g":
    SN: 2 flam

section "a":
  bars: 1
  groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\slashedGrace sn16" in ly


# ---------------------------------------------------------------------------
# Emitters — MIDI
# ---------------------------------------------------------------------------

def test_midi_cross_instrument_flam_grace_uses_grace_inst_pitch():
    """The grace note before the main hit fires on the grace instrument's GM pitch."""
    src = """\
groove "g":
    HT: 1 flam:SN

section "a":
  bars: 1
  groove: "g"
"""
    midi = emit_midi(compile_song(parse(src)))
    # GM drum note 38 = SN (acoustic snare); 50 = HT (high tom).
    # Both pitches must appear in the MIDI byte stream — the SN grace
    # before the HT main.
    assert bytes([0x99, 38]) in midi  # NoteOn channel 10, SN
    assert bytes([0x99, 50]) in midi  # NoteOn channel 10, HT


def test_midi_cross_instrument_drag_emits_two_grace_notes_on_grace_inst():
    src = """\
groove "g":
    RD: 1 drag:SN

section "a":
  bars: 1
  groove: "g"
"""
    midi = emit_midi(compile_song(parse(src)))
    # Two SN NoteOn (38) before one RD NoteOn (51).
    assert midi.count(bytes([0x99, 38])) == 2
    assert bytes([0x99, 51]) in midi


# ---------------------------------------------------------------------------
# Emitters — MusicXML
# ---------------------------------------------------------------------------

def test_musicxml_cross_instrument_flam_grace_uses_grace_inst_display():
    """The grace note's display-step/octave matches the grace instrument's voicing."""
    src = """\
groove "g":
    HT: 1 flam:SN

section "a":
  bars: 1
  groove: "g"
"""
    xml = emit_musicxml(compile_song(parse(src))).decode("utf-8")
    # MusicXML emits the grace note before the chord; check that it carries
    # the snare's display step (C, octave 5 in the project's _DISPLAY map),
    # which differs from the hi-tom's display step.
    grace_block = xml.split("<grace")[1].split("</note>")[0]
    assert "<display-step>C</display-step>" in grace_block
    assert "<display-octave>5</display-octave>" in grace_block
