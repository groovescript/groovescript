from pathlib import Path

import pytest
from groovescript.parser import parse, parse_file
from groovescript.compiler import compile_song
from groovescript.lilypond import emit_lilypond

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_fixture_library_grooves():
    """End-to-end: library_grooves.gs references five built-in library grooves
    (rock, 16th-rock, funk, shuffle, jazz-ride) without defining them locally;
    they should all resolve from the built-in library at compile time."""
    song = parse_file(str(FIXTURES / "library_grooves.gs"))
    assert song.metadata.title == "Library Grooves"
    # No grooves defined in the fixture — all references come from the library.
    assert len(song.grooves) == 0
    section_grooves = {s.groove for s in song.sections}
    assert section_grooves == {"rock", "16th-rock", "funk", "shuffle", "jazz-ride"}
    # Every referenced library groove should resolve and compile.
    ir = compile_song(song)
    assert len(ir.bars) == sum(s.bars for s in song.sections)
    ly = emit_lilypond(ir)
    assert "drummode" in ly

def test_library_groove_rock():
    source = """
    metadata:
        title: "Library Test"
    
    section "Verse":
        bars: 2
        groove: "rock"
    """
    song = parse(source)
    ir = compile_song(song)
    
    assert len(ir.bars) == 2
    # "rock" has BD on 1, 3; SN on 2, 4; HH on * (8ths)
    # Total events per bar: 8 (HH) + 2 (BD) + 2 (SN) = 12
    assert len(ir.bars[0].events) == 12
    
    # Check some events in first bar
    events = ir.bars[0].events
    # BD at 0.0 and 0.5
    assert any(e.instrument == "BD" and e.beat_position == 0 for e in events)
    assert any(e.instrument == "BD" and e.beat_position == 0.5 for e in events)
    # SN at 0.25 and 0.75
    assert any(e.instrument == "SN" and e.beat_position == 0.25 for e in events)
    assert any(e.instrument == "SN" and e.beat_position == 0.75 for e in events)

def test_library_groove_override():
    # User-defined groove should override library one
    source = """
    groove "rock":
            BD: 1, 2, 3, 4

    section "Verse":
        bars: 1
        groove: "rock"
    """
    song = parse(source)
    ir = compile_song(song)
    
    assert len(ir.bars) == 1
    # Only BD on 1, 2, 3, 4 => 4 events
    assert len(ir.bars[0].events) == 4
    for e in ir.bars[0].events:
        assert e.instrument == "BD"

def test_library_groove_shuffle():
    source = """
    section "Verse":
        bars: 1
        groove: "shuffle"
    """
    song = parse(source)
    ir = compile_song(song)
    
    # shuffle infers a 12-slot (triplet) grid
    # HH: 1, 1let, 2, 2let, 3, 3let, 4, 4let (8 events)
    # BD: 1, 3 (2 events)
    # SN: 2, 4 (2 events)
    # Total 12 events
    assert ir.bars[0].subdivision == 12
    assert len(ir.bars[0].events) == 12
    
    # "1let" in subdivision 12 is offset (1-1)*3 + 2 = 2. 2/12 = 1/6
    assert any(e.instrument == "HH" and e.beat_position == 0 for e in ir.bars[0].events)
    from fractions import Fraction
    assert any(e.instrument == "HH" and e.beat_position == Fraction(2, 12) for e in ir.bars[0].events)
