from fractions import Fraction
from pathlib import Path

from groovescript.compiler import compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_fixture_library_fills():
    """End-to-end: library_fills.gs references several built-in library fills
    without defining them locally; they should all resolve from the built-in
    fill library at compile time."""
    song = parse_file(str(FIXTURES / "library_fills.gs"))
    assert song.metadata.title == "Library Fills"
    # No fills defined in the fixture — all references come from the library.
    assert len(song.fills) == 0
    referenced = {p.fill_name for s in song.sections for p in s.fills}
    assert referenced == {
        "crash",
        "snare-roll",
        "snare-roll-half",
        "tom-roll",
        "tom-roll-half",
    }
    ir = compile_song(song)
    assert len(ir.bars) == sum(s.bars for s in song.sections)
    ly = emit_lilypond(ir)
    assert "drummode" in ly


def test_library_fill_crash():
    source = """
    section "verse":
        bars: 2
        groove: "rock"
        fill "crash" at bar 2
    """
    song = parse(source)
    ir = compile_song(song)

    assert len(ir.bars) == 2
    # Bar 2 should contain BD + CR on beat 1 (overlaying the rock groove).
    bar2 = ir.bars[1]
    assert any(e.instrument == "BD" and e.beat_position == 0 for e in bar2.events)
    assert any(e.instrument == "CR" and e.beat_position == 0 for e in bar2.events)


def test_library_fill_snare_roll_half():
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "snare-roll-half" at bar 1 beat 3
    """
    song = parse(source)
    ir = compile_song(song)

    assert len(ir.bars) == 1
    bar = ir.bars[0]
    # Eight 16th-note snare hits across beats 3 and 4 (groove SN before
    # beat 3 is preserved; the fill replaces only beats 3 onward).
    snare_positions = sorted(
        e.beat_position for e in bar.events
        if e.instrument == "SN" and e.beat_position >= Fraction(1, 2)
    )
    expected = [Fraction(2, 4) + Fraction(i, 16) for i in range(8)]
    assert snare_positions == expected
    # Bar must use 16th-note resolution to fit the roll.
    assert bar.subdivision >= 16


def test_library_fill_override():
    """A user-defined fill with the same name as a library fill takes precedence."""
    source = """
    fill "crash":
      count "1":
        1: SN

    section "verse":
        bars: 1
        groove: "rock"
        fill "crash" at bar 1
    """
    song = parse(source)
    ir = compile_song(song)

    assert len(ir.bars) == 1
    # The override puts a single SN at beat 1; no BD or CR from the library
    # version should land on beat 1 from the fill.
    bar = ir.bars[0]
    on_beat_one = [e for e in bar.events if e.beat_position == 0]
    instruments = {e.instrument for e in on_beat_one}
    assert "SN" in instruments
    assert "CR" not in instruments


def test_library_fill_tom_roll_subdivisions():
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "tom-roll" at bar 1
    """
    song = parse(source)
    ir = compile_song(song)

    bar = ir.bars[0]
    assert bar.subdivision >= 16
    # FT, MT, HT all appear in the bar.
    instruments = {e.instrument for e in bar.events}
    assert {"HT", "MT", "FT"}.issubset(instruments)


def test_library_fill_unknown_still_errors():
    """A reference to a fill that is neither user-defined nor in the library
    must still raise a clear unknown-fill error."""
    import pytest

    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "definitely-not-a-real-fill" at bar 1
    """
    song = parse(source)
    with pytest.raises(ValueError, match="unknown fill"):
        compile_song(song)
