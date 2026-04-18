"""Tests for crescendo and decrescendo (dynamic hairpin) support."""

from fractions import Fraction
from pathlib import Path

from groovescript.ast_nodes import DynamicSpan
from groovescript.parser import parse, parse_file
from groovescript.compiler import compile_song
from groovescript.lilypond import emit_lilypond

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_fixture_dynamics():
    """End-to-end: dynamics.gs parses, compiles, and emits full + partial-bar
    crescendo/decrescendo hairpins across the whole song."""
    song = parse_file(str(FIXTURES / "dynamics.gs"))
    assert song.metadata.title == "Dynamics Test"
    # Verse has a 2-bar crescendo.
    verse = next(s for s in song.sections if s.name == "verse")
    cresc = verse.dynamic_spans[0]
    assert cresc.kind == "cresc"
    # Chorus has both a partial-bar cresc and a full-bar decresc.
    chorus = next(s for s in song.sections if s.name == "chorus")
    kinds = {span.kind for span in chorus.dynamic_spans}
    assert {"cresc", "decresc"}.issubset(kinds)
    # Whole song compiles and emits both hairpin tokens + the terminator.
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\<" in ly
    assert "\\>" in ly
    assert "\\!" in ly


# ── Parser tests ────────────────────────────────────────────────────────────

CRESC_BASIC = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 4
    groove: "beat"
    cresc from bar 2 to bar 3
"""


def test_parse_cresc_no_beats():
    song = parse(CRESC_BASIC)
    section = song.sections[0]
    assert len(section.dynamic_spans) == 1
    span = section.dynamic_spans[0]
    assert span.kind == "cresc"
    assert span.from_bar == 2
    assert span.to_bar == 3
    assert span.from_beat is None
    assert span.to_beat is None


CRESC_WITH_BEATS = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 8
    groove: "beat"
    cresc from bar 3 beat 3 to bar 4 beat 1
    decresc from bar 6 to bar 7 beat 2&
"""


def test_parse_cresc_with_from_beat():
    song = parse(CRESC_WITH_BEATS)
    span = song.sections[0].dynamic_spans[0]
    assert span.kind == "cresc"
    assert span.from_bar == 3
    assert span.from_beat == "3"
    assert span.to_bar == 4
    assert span.to_beat == "1"


def test_parse_decresc_with_to_beat():
    song = parse(CRESC_WITH_BEATS)
    span = song.sections[0].dynamic_spans[1]
    assert span.kind == "decresc"
    assert span.from_bar == 6
    assert span.from_beat is None
    assert span.to_bar == 7
    assert span.to_beat == "2&"


CRESC_BOTH_BEATS = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 4
    groove: "beat"
    cresc from bar 1 beat 3 to bar 2 beat 3
"""


def test_parse_cresc_both_beats():
    song = parse(CRESC_BOTH_BEATS)
    span = song.sections[0].dynamic_spans[0]
    assert span.from_beat == "3"
    assert span.to_beat == "3"


# ── Compiler tests ──────────────────────────────────────────────────────────

def test_compile_cresc_sets_ir_bar_dynamic_starts():
    song = parse(CRESC_BASIC)
    ir = compile_song(song)
    # Bar 2 (0-indexed: 1) should have a cresc start at position 0
    bar2 = ir.bars[1]
    assert len(bar2.dynamic_starts) == 1
    assert bar2.dynamic_starts[0] == (Fraction(0), "cresc")


def test_compile_cresc_sets_ir_bar_dynamic_stops():
    song = parse(CRESC_BASIC)
    ir = compile_song(song)
    # Bar 3 (0-indexed: 2) should have a stop sentinel
    bar3 = ir.bars[2]
    assert len(bar3.dynamic_stops) == 1
    # Fraction(-1) is the "end of bar" sentinel
    assert bar3.dynamic_stops[0] == Fraction(-1)


def test_compile_cresc_with_beat_positions():
    song = parse(CRESC_WITH_BEATS)
    ir = compile_song(song)
    # Bar 3 has cresc start at beat 3 (position = Fraction(2, 4) in 8ths grid)
    bar3 = ir.bars[2]
    assert len(bar3.dynamic_starts) == 1
    pos, kind = bar3.dynamic_starts[0]
    assert kind == "cresc"
    assert pos == Fraction(2, 4)  # beat 3 in 4/4 = position 1/2


def test_compile_bars_without_dynamics_have_empty_lists():
    song = parse(CRESC_BASIC)
    ir = compile_song(song)
    # Bars 1 and 4 should have no dynamics
    assert ir.bars[0].dynamic_starts == []
    assert ir.bars[0].dynamic_stops == []
    assert ir.bars[3].dynamic_starts == []
    assert ir.bars[3].dynamic_stops == []


# ── LilyPond emission tests ────────────────────────────────────────────────

def test_lilypond_cresc_hairpin():
    song = parse(CRESC_BASIC)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    # Should contain \< for crescendo start
    assert "\\<" in ly
    # Should contain \! for hairpin terminator
    assert "\\!" in ly


def test_lilypond_decresc_hairpin():
    src = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 4
    groove: "beat"
    decresc from bar 2 to bar 3
"""
    song = parse(src)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\>" in ly
    assert "\\!" in ly


def test_lilypond_partial_bar_cresc():
    """A cresc that starts mid-bar should attach \\< to the right beat."""
    src = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 4
    groove: "beat"
    cresc from bar 2 beat 3 to bar 3 beat 1
"""
    song = parse(src)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    # The cresc starts at beat 3, which is the 5th 8th note in the bar.
    # Check that \< appears in the output
    assert "\\<" in ly
    # Check that \! appears for the terminator
    assert "\\!" in ly


# ── Inline fill dynamic span tests ─────────────────────────────────────────

_INLINE_FILL_WITH_CRESC = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 4
    groove: "beat"
    fill at bar 4:
        count "1 2 3 4":
            1: BD
            2: SN
            3: SN
            4: SN
        cresc from bar 1 to bar 1
"""


def test_parse_inline_fill_dynamic_span():
    """Regression: inline fills should parse and store dynamic spans."""
    song = parse(_INLINE_FILL_WITH_CRESC)
    section = song.sections[0]
    assert len(section.inline_fills) == 1
    fill = section.inline_fills[0]
    assert len(fill.dynamic_spans) == 1
    span = fill.dynamic_spans[0]
    assert span.kind == "cresc"
    assert span.from_bar == 1
    assert span.to_bar == 1


def test_compile_inline_fill_dynamic_span():
    """Regression: inline fill dynamic spans should appear in the compiled IR bar."""
    song = parse(_INLINE_FILL_WITH_CRESC)
    ir = compile_song(song)
    # Fill is at bar 4 (0-indexed: 3); cresc from/to bar 1 of the fill = section bar 4
    bar4 = ir.bars[3]
    assert len(bar4.dynamic_starts) >= 1
    kinds = {kind for _, kind in bar4.dynamic_starts}
    assert "cresc" in kinds


def test_lilypond_inline_fill_dynamic_span():
    """Regression: inline fill crescendo should produce hairpin tokens in LilyPond output."""
    song = parse(_INLINE_FILL_WITH_CRESC)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\<" in ly
    assert "\\!" in ly


_INLINE_FILL_WITH_DECRESC = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 4
    groove: "beat"
    fill at bar 4:
        count "1 2 3 4":
            1: BD
            2: SN
            3: SN
            4: SN
        decresc from bar 1 to bar 1
"""


def test_compile_inline_fill_decresc_span():
    """Regression: inline fill decrescendo should appear in the compiled IR."""
    song = parse(_INLINE_FILL_WITH_DECRESC)
    ir = compile_song(song)
    bar4 = ir.bars[3]
    assert len(bar4.dynamic_starts) >= 1
    kinds = {kind for _, kind in bar4.dynamic_starts}
    assert "decresc" in kinds


# ── Full-word synonym and shorthand syntax tests ─────────────────────────────

_SYNONYMS_AND_SHORTHAND = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 4
    groove: "beat"
    crescendo from bar 1 to bar 2
    decrescendo from bar 3 to bar 4
    cresc bar 2
    decresc bar 3
"""


def test_parse_crescendo_synonym():
    """Regression: 'crescendo' is accepted as a synonym for 'cresc' and normalized."""
    song = parse(_SYNONYMS_AND_SHORTHAND)
    span = song.sections[0].dynamic_spans[0]
    assert span.kind == "cresc"
    assert span.from_bar == 1
    assert span.to_bar == 2


def test_parse_decrescendo_synonym():
    """Regression: 'decrescendo' is accepted as a synonym for 'decresc' and normalized."""
    song = parse(_SYNONYMS_AND_SHORTHAND)
    span = song.sections[0].dynamic_spans[1]
    assert span.kind == "decresc"


def test_parse_cresc_bar_shorthand():
    """Regression: 'cresc bar N' is accepted as a single-bar hairpin shorthand."""
    song = parse(_SYNONYMS_AND_SHORTHAND)
    span = song.sections[0].dynamic_spans[2]
    assert span.kind == "cresc"
    assert span.from_bar == 2
    assert span.to_bar == 2
    assert span.from_beat is None
    assert span.to_beat is None


def test_parse_decresc_bar_shorthand():
    """Regression: 'decresc bar N' is accepted as a single-bar hairpin shorthand."""
    song = parse(_SYNONYMS_AND_SHORTHAND)
    span = song.sections[0].dynamic_spans[3]
    assert span.kind == "decresc"
    assert span.from_bar == 3
    assert span.to_bar == 3


def test_compile_cresc_bar_shorthand_sets_ir():
    """Regression: shorthand single-bar cresc produces correct IR start/stop."""
    song = parse(_SYNONYMS_AND_SHORTHAND)
    ir = compile_song(song)
    # 'cresc bar 2' → bar index 1 should have a start and bar index 1 a stop
    bar2 = ir.bars[1]
    starts = {kind for _, kind in bar2.dynamic_starts}
    assert "cresc" in starts
    assert Fraction(-1) in bar2.dynamic_stops


def test_like_inherits_dynamic_spans():
    """Section-level dynamic spans are inherited through bare ``like`` sections."""
    src = """\
groove "beat":
        BD: 1, 3
        SN: 2, 4
        HH: *8

section "verse":
    bars: 4
    groove: "beat"
    cresc from bar 3 to bar 4

section "verse 2":
    like "verse"
"""
    song = parse(src)
    ir = compile_song(song)
    # verse 2 bars (absolute 5-8) should also have dynamics from inheritance
    bar7 = ir.bars[6]  # 0-indexed: bar 7 = verse 2's bar 3
    assert len(bar7.dynamic_starts) == 1
    assert bar7.dynamic_starts[0][1] == "cresc"
