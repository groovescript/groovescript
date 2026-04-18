"""Tests for the hi-hat foot chick (HF) instrument."""
from pathlib import Path

import pytest

from groovescript.compiler import compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_fixture_hihat_foot():
    """End-to-end: hihat_foot.gs parses, compiles, and renders HF as `hhp`."""
    song = parse_file(str(FIXTURES / "hihat_foot.gs"))
    assert song.metadata.title == "Hi-Hat Foot Chick Demo"
    # Both grooves should carry HF on 2 and 4.
    for groove in song.grooves:
        hf_line = next((p for p in groove.bars[0] if p.instrument == "HF"), None)
        assert hf_line is not None
        assert list(hf_line.beats) == ["2", "4"]
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "hhp" in ly


def test_parse_hf_canonical():
    """``HF`` is recognised as an instrument on a pattern line."""
    src = """\
groove "g":
    HF: 2, 4
"""
    song = parse(src)
    hf = song.grooves[0].pattern[0]
    assert hf.instrument == "HF"
    assert list(hf.beats) == ["2", "4"]


def test_parse_hf_lowercase_alias():
    """Lowercase ``hf`` resolves to the canonical ``HF``."""
    src = """\
groove "g":
    hf: 2, 4
"""
    song = parse(src)
    assert song.grooves[0].pattern[0].instrument == "HF"


@pytest.mark.parametrize(
    "alias", ["hihatfoot", "footchick"]
)
def test_parse_hf_long_form_aliases(alias):
    """Long-form aliases resolve to the canonical ``HF``."""
    src = f"""\
groove "g":
    {alias}: 2, 4
"""
    song = parse(src)
    assert song.grooves[0].pattern[0].instrument == "HF"


def test_parse_hf_in_count_notes():
    """HF aliases are accepted inside a count+notes body."""
    src = """\
fill "f":
  count: "1 2 3 4"
  notes: "SN HF SN HF"
"""
    song = parse(src)
    bar = song.fills[0].bars[0]
    assert bar.lines[1].instruments[0].instrument == "HF"
    assert bar.lines[3].instruments[0].instrument == "HF"


def test_compile_hf_emits_events():
    """HF compiles to events at the expected beat positions."""
    src = """\
groove "g":
    HF: 2, 4

section "s":
  bars: 1
  groove: "g"
"""
    song = parse(src)
    ir = compile_song(song)
    hf_events = [e for e in ir.bars[0].events if e.instrument == "HF"]
    assert len(hf_events) == 2


def test_emit_hf_uses_hhp_lilypond_name():
    """HF events render as the LilyPond ``hhp`` (hi-hat pedal) token."""
    src = """\
groove "g":
    HF: 2, 4

section "s":
  bars: 1
  groove: "g"
"""
    song = parse(src)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "hhp" in ly


def test_hf_with_other_instruments_chords():
    """HF layers correctly with BD/SN on the same beat slot."""
    src = """\
groove "g":
    BD: 1, 3
    SN: 2, 4
    HF: 2, 4

section "s":
  bars: 1
  groove: "g"
"""
    song = parse(src)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    # A chord at beat 2 should contain both sn and hhp.
    assert "<sn hhp>" in ly or "<hhp sn>" in ly
