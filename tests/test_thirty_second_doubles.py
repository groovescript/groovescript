"""Tests for 32nd-note double-stroke support."""
from fractions import Fraction
from pathlib import Path

import pytest

from groovescript.ast_nodes import BeatHit, FillBar, FillLine, Groove, InstrumentHit, PatternLine
from groovescript.compiler import compile_fill_bar, compile_groove
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


# ── Parser tests ──────────────────────────────────────────────────────────────

def test_parse_double_modifier_pattern_line():
    """'double' on a pattern-line beat is preserved on BeatHit.modifiers."""
    src = """\
groove "g":
    HH: 1, 1e double, 2, 2e
"""
    song = parse(src)
    hh = song.grooves[0].pattern[0]  # first PatternLine (HH)
    beats = hh.beats
    assert beats[0] == "1" and getattr(beats[0], "modifiers", []) == []
    assert beats[1] == "1e" and getattr(beats[1], "modifiers", []) == ["double"]
    assert beats[2] == "2" and getattr(beats[2], "modifiers", []) == []


def test_parse_32nd_alias_normalized_to_double():
    """'32nd' is normalized to 'double' at parse time."""
    src = """\
groove "g":
    HH: 1, 1e 32nd, 2
"""
    song = parse(src)
    hh = song.grooves[0].pattern[0]
    beat_1e = hh.beats[1]
    assert str(beat_1e) == "1e"
    assert beat_1e.modifiers == ["double"]


def test_parse_double_position_style():
    """'double' on a position-style groove line is preserved."""
    src = """\
groove "g":
    1e: HH double
"""
    song = parse(src)
    hh_line = song.grooves[0].pattern[0]
    beat = hh_line.beats[0]
    assert beat.modifiers == ["double"]


def test_parse_double_in_variation_add():
    """'double' in a variation add action is preserved."""
    src = """\
groove "g":
    HH: 1, 1&, 2, 2&, 3, 3&, 4, 4&

section "s":
  bars: 2
  groove: "g"
  variation at bar 1:
    add HH double at 1e
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.action == "add"
    assert action.instrument == "HH"
    assert action.modifiers == ["double"]


def test_parse_double_in_count_notes_fill():
    """'double' in a count+notes notes string is normalized and attached."""
    src = """\
fill "f":
  count "1 e & a":
    1: SN double
    1e: SN
    1&: SN double
    1a: SN
"""
    song = parse(src)
    fill = song.fills[0]
    bar = fill.bars[0]
    # Beat 1 has SN with double, beat 1e has plain SN
    hits_1 = bar.lines[0].instruments
    hits_1e = bar.lines[1].instruments
    assert hits_1[0].modifiers == ["double"]
    assert hits_1e[0].modifiers == []


def test_parse_ghost_and_double_together():
    """'ghost' and 'double' can coexist on the same hit."""
    src = """\
groove "g":
    SN: 1 ghost double
"""
    song = parse(src)
    sn = song.grooves[0].pattern[0]
    mods = sn.beats[0].modifiers
    assert "ghost" in mods
    assert "double" in mods


# ── Compiler tests ─────────────────────────────────────────────────────────────

def test_compile_double_preserves_modifier():
    """Events compiled from a 'double' hit carry 'double' in modifiers."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(instrument="HH", beats=[BeatHit("1e", ["double"])]),
        ]],
    )
    ir = compile_groove(g)
    event = next(e for e in ir.events if e.instrument == "HH")
    assert "double" in event.modifiers


def test_compile_double_at_wrong_subdivision_raises():
    """'double' at 8th-note subdivision (2 slots/beat) is rejected."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(instrument="HH", beats=[BeatHit("1&", ["double"])]),
        ]],
    )
    with pytest.raises(ValueError, match="double.*16th"):
        compile_groove(g)


def test_compile_double_with_flam_raises():
    """'double' combined with 'flam' is rejected at compile time."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(instrument="HH", beats=[BeatHit("1e", ["double", "flam"])]),
        ]],
    )
    with pytest.raises(ValueError, match="incompatible"):
        compile_groove(g)


def test_compile_double_with_drag_raises():
    """'double' combined with 'drag' is rejected at compile time."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(instrument="SN", beats=[BeatHit("3a", ["double", "drag"])]),
        ]],
    )
    with pytest.raises(ValueError, match="incompatible"):
        compile_groove(g)


def test_compile_fill_double_at_correct_subdivision():
    """'double' in a fill at 16th subdivision compiles without error."""
    fb = FillBar(
        label="1 e & a",
        lines=[
            FillLine(beat="1e", instruments=[InstrumentHit("SN", ["double"])]),
        ],
    )
    ir = compile_fill_bar(fb)
    event = ir.events[0]
    assert "double" in event.modifiers


def test_compile_fill_double_at_wrong_subdivision_raises():
    """'double' in a fill that resolves to 8th subdivision is rejected."""
    fb = FillBar(
        label="1 & 2 &",
        lines=[
            FillLine(beat="1&", instruments=[InstrumentHit("SN", ["double"])]),
        ],
    )
    with pytest.raises(ValueError, match="double.*16th"):
        compile_fill_bar(fb)


# ── LilyPond emitter tests ────────────────────────────────────────────────────

def _groove_ly(beats_with_mods: list[tuple[str, list[str]]], instrument: str = "HH") -> str:
    """Compile a single-instrument 16th-note groove and return its LilyPond."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(
                instrument=instrument,
                beats=[BeatHit(label, mods) for label, mods in beats_with_mods],
            ),
        ]],
    )
    ir = compile_groove(g)
    return emit_lilypond(ir)


@pytest.mark.parametrize("beats,contains,not_contains", [
    # Plain doubled slot emits two 32nds.
    ([("1e", ["double"])],
     ["hh32 hh32"],
     []),
    # A doubled slot blocks beat-1 consolidation to a quarter note.
    ([("1", []), ("1e", ["double"])],
     ["hh32 hh32"],
     ["hh4"]),
    # ghost+double parenthesises both strokes.
    ([("1e", ["ghost", "double"])],
     ["\\parenthesize hh32 \\parenthesize hh32"],
     []),
    # accent+double accents only the first stroke.
    ([("1e", ["accent", "double"])],
     ["hh32->"],
     ["hh32-> hh32->"]),
])
def test_emit_doubled_slot_variants(beats, contains, not_contains):
    """Doubled 16th slots emit two 32nds, with modifier-specific decoration."""
    ly = _groove_ly(beats)
    for s in contains:
        assert s in ly
    for s in not_contains:
        assert s not in ly


def test_emit_32nd_alias_same_output_as_double():
    """'32nd' alias produces identical LilyPond to 'double'."""
    src_double = """\
groove "g":
    HH: 1, 1e double, 2
"""
    src_32nd = """\
groove "g":
    HH: 1, 1e 32nd, 2
"""
    from groovescript.compiler import compile_groove as cg
    from groovescript.lilypond import emit_lilypond as el

    def _compile(src: str) -> str:
        song = parse(src)
        return el(cg(song.grooves[0]))

    assert _compile(src_double) == _compile(src_32nd)


def test_emit_simultaneous_double_and_plain():
    """When BD+HH share a slot but only HH is doubled, BD plays once."""
    # Beat 1: BD+HH together (position-style), only HH doubled
    src = """\
groove "g":
    BD: 1
    HH: 1, 1e double
"""
    song = parse(src)
    from groovescript.compiler import compile_groove as cg
    from groovescript.lilypond import emit_lilypond as el
    ly = el(cg(song.grooves[0]))
    # Beat 1 slot: BD+HH chord at 16th (BD not doubled)
    assert "<bd hh>16" in ly
    # Beat 1e: doubled HH
    assert "hh32 hh32" in ly


def test_fixture_compiles():
    """The thirty_second_doubles fixture file compiles without error."""
    from groovescript.parser import parse_file
    from groovescript.compiler import compile_song
    from groovescript.lilypond import emit_lilypond
    song = parse_file(str(FIXTURES / "thirty_second_doubles.gs"))
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "hh32 hh32" in ly
    assert "\\parenthesize sn32 \\parenthesize sn32" in ly
