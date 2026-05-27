"""Tests for the ``break on bar N`` section directive.

The break directive silences (removes all events from) a specified range of
bars or beats within a section.  Covers all four DSL forms:

  break on bar 3
  break on bar 3 beat 3
  break on bar 3 beat 3 through bar 5
  break on bar 3 beat 3 through bar 5 beat 2
"""

from fractions import Fraction

import pytest

from groovescript.ast_nodes import BreakSpec, Section
from groovescript.compiler import compile_song
from groovescript.parser import parse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile(src: str):
    return compile_song(parse(src))


def _events(bar) -> list:
    return bar.events


def _positions(bar) -> set:
    return {e.beat_position for e in bar.events}


def _instruments_at(bar, pos: Fraction) -> set:
    return {e.instrument for e in bar.events if e.beat_position == pos}


_STANDARD_GROOVE = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4
"""

# ---------------------------------------------------------------------------
# BreakSpec dataclass unit tests
# ---------------------------------------------------------------------------

def test_break_spec_effective_end_bar_defaults_to_start():
    spec = BreakSpec(start_bar=3)
    assert spec.effective_end_bar == 3


def test_break_spec_effective_end_bar_explicit():
    spec = BreakSpec(start_bar=3, end_bar=5)
    assert spec.effective_end_bar == 5


# ---------------------------------------------------------------------------
# DSL parse → compile round-trip tests
# ---------------------------------------------------------------------------

def test_break_whole_bar_silences_entire_bar():
    """``break on bar 3`` removes all events from bar 3 only."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 3
"""
    ir = _compile(src)
    assert len(ir.bars[2].events) == 0   # bar 3 is silent
    assert len(ir.bars[0].events) > 0    # bar 1 untouched
    assert len(ir.bars[1].events) > 0    # bar 2 untouched
    assert len(ir.bars[3].events) > 0    # bar 4 untouched


def test_break_bar_beat_silences_from_beat_onward():
    """``break on bar 1 beat 3`` silences beats 3 and 4 but keeps 1 and 2."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 2
  groove: "g"
  break on bar 1 beat 3
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    # 4/4: beat 3 = Fraction(2,4), beat 4 = Fraction(3,4)
    remaining = _positions(bar1)
    assert Fraction(0) in remaining          # beat 1 BD + HH survive
    assert Fraction(1, 4) in remaining       # beat 2 SN + HH survives
    # beats 3, 3&, 4 all gone
    for pos in [Fraction(2, 4), Fraction(3, 4)]:
        assert pos not in remaining, f"position {pos} should be silenced"
    # bar 2 untouched
    assert len(ir.bars[1].events) > 0


def test_break_beat_range_silences_from_beat_through_end_bar():
    """``break on bar 1 beat 3 through bar 2`` silences bar1 from beat 3
    onwards and all of bar 2."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 1 beat 3 through bar 2
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    bar2 = ir.bars[1]
    bar3 = ir.bars[2]

    # bar 1: beats 1, 2 survive; beat 3 onwards gone
    assert Fraction(0) in _positions(bar1)
    assert Fraction(1, 4) in _positions(bar1)
    assert Fraction(2, 4) not in _positions(bar1)
    assert Fraction(3, 4) not in _positions(bar1)

    # bar 2: completely silent
    assert len(bar2.events) == 0

    # bar 3: untouched
    assert len(bar3.events) > 0


def test_break_full_range_with_end_beat():
    """``break on bar 1 beat 3 through bar 2 beat 2`` silences bar 1 from
    beat 3 onwards and bar 2 up to and including beat 2."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 1 beat 3 through bar 2 beat 2
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    bar2 = ir.bars[1]

    # bar 1: beats before beat 3 survive
    assert Fraction(0) in _positions(bar1)
    assert Fraction(1, 4) in _positions(bar1)
    # beat 3 and beyond gone
    assert Fraction(2, 4) not in _positions(bar1)

    # bar 2: beat 1 and beat 2 gone (positions 0 and 1/4 <= 1/4)
    assert Fraction(0) not in _positions(bar2)
    assert Fraction(1, 4) not in _positions(bar2)
    # beat 3 survives (position 2/4 > end beat 2 = 1/4)
    assert Fraction(2, 4) in _positions(bar2)
    assert Fraction(3, 4) in _positions(bar2)


def test_break_range_without_beats():
    """``break on bar 2 through bar 3`` silences bars 2 and 3 completely."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 2 through bar 3
"""
    ir = _compile(src)
    assert len(ir.bars[1].events) == 0   # bar 2
    assert len(ir.bars[2].events) == 0   # bar 3
    assert len(ir.bars[0].events) > 0    # bar 1 untouched
    assert len(ir.bars[3].events) > 0    # bar 4 untouched


def test_break_range_with_end_beat_only():
    """``break on bar 1 through bar 2 beat 3`` silences all of bar 1 and bar 2
    up to and including beat 3."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 3
  groove: "g"
  break on bar 1 through bar 2 beat 3
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    bar2 = ir.bars[1]

    assert len(bar1.events) == 0   # fully silenced
    # bar 2: beats <= Fraction(2, 4) silenced; beat 4 survives
    assert Fraction(0) not in _positions(bar2)
    assert Fraction(2, 4) not in _positions(bar2)
    assert Fraction(3, 4) in _positions(bar2)


def test_multiple_breaks_accumulate():
    """Two separate break directives each silence their own range."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 1
  break on bar 3
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) == 0   # bar 1 broken
    assert len(ir.bars[1].events) > 0    # bar 2 intact
    assert len(ir.bars[2].events) == 0   # bar 3 broken
    assert len(ir.bars[3].events) > 0    # bar 4 intact


def test_break_coexists_with_fill():
    """A fill placed on the same bar as a break: break wins (fill events are
    removed by the subsequent break application)."""
    src = """
groove "g":
  BD: 1, 3
  SN: 2, 4
  HH: *8

fill "f":
  count "1 e & a 2 e & a 3 e & a 4 e & a":
    1: SN
    1e: SN
    1&: SN
    1a: SN
    2: SN
    2e: SN
    2&: SN
    2a: SN
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: SN
    4e: SN
    4&: SN
    4a: SN

section "s":
  bars: 2
  groove: "g"
  fill "f" at bar 1
  break on bar 1
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) == 0   # break wins over fill
    assert len(ir.bars[1].events) > 0    # bar 2 unaffected


def test_break_coexists_with_crash_in():
    """crash in fires on bar 1, then break silences it — result is empty bar 1."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 2
  groove: "g"
  crash in
  break on bar 1
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) == 0
    assert len(ir.bars[1].events) > 0


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_break_bar_out_of_range_raises():
    """A break targeting a bar beyond the section length is an error."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 5
"""
    with pytest.raises(Exception, match="out of range|bar 5"):
        _compile(src)


def test_break_end_bar_before_start_bar_raises():
    """A break where end_bar < start_bar is invalid."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 3 beat 1 through bar 2
"""
    with pytest.raises(Exception, match="out of range|bar 2"):
        _compile(src)


def test_break_end_bar_out_of_range_raises():
    """A break where end_bar exceeds section length is an error."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 3 through bar 6
"""
    with pytest.raises(Exception, match="out of range|bar 6"):
        _compile(src)


# ---------------------------------------------------------------------------
# play: section support
# ---------------------------------------------------------------------------

def test_break_in_play_section():
    """Break directive works inside a ``play:`` section."""
    src = _STANDARD_GROOVE + """
section "s":
  play:
    groove "g" x4
  break on bar 2
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) > 0    # bar 1 intact
    assert len(ir.bars[1].events) == 0   # bar 2 silenced
    assert len(ir.bars[2].events) > 0    # bar 3 intact
