"""Tests for the ``break on bar N`` section directive.

The break directive silences (removes all events from) a specified range of
bars or beats within a section.  When no ``through`` clause is given the
break runs to the end of the section.  The four user-facing forms are:

  break on bar 3                           → bar 3 through end of section
  break on bar 3 beat 3                    → bar 3 beat 3 through end of section
  break on bar 3 beat 3 through bar 5      → bar 3 beat 3 through bar 5 (end)
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


def _positions(bar) -> set:
    return {e.beat_position for e in bar.events}


_STANDARD_GROOVE = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4
"""

# ---------------------------------------------------------------------------
# BreakSpec dataclass unit tests
# ---------------------------------------------------------------------------

def test_break_spec_effective_end_bar_none_returns_total_bars():
    """When end_bar is None, effective_end_bar returns total_bars (end of section)."""
    spec = BreakSpec(start_bar=3)
    assert spec.effective_end_bar(8) == 8


def test_break_spec_effective_end_bar_explicit():
    spec = BreakSpec(start_bar=3, end_bar=5)
    assert spec.effective_end_bar(8) == 5


# ---------------------------------------------------------------------------
# No-through forms: break runs to end of section
# ---------------------------------------------------------------------------

def test_break_whole_bar_silences_to_end_of_section():
    """``break on bar 3`` (4-bar section) silences bars 3 and 4."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 3
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) > 0    # bar 1 intact
    assert len(ir.bars[1].events) > 0    # bar 2 intact
    assert len(ir.bars[2].events) == 0   # bar 3 silent
    assert len(ir.bars[3].events) == 0   # bar 4 silent (break runs to end)


def test_break_bar_beat_silences_to_end_of_section():
    """``break on bar 2 beat 3`` silences beat 3 onwards in bar 2, then all
    of bar 3 and bar 4 — the break runs to the end of the section."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 2 beat 3
"""
    ir = _compile(src)
    bar2 = ir.bars[1]
    # bar 2: beats 1 and 2 survive; beat 3 onwards gone
    assert Fraction(0) in _positions(bar2)
    assert Fraction(1, 4) in _positions(bar2)
    assert Fraction(2, 4) not in _positions(bar2)
    assert Fraction(3, 4) not in _positions(bar2)
    # bars 3 and 4: fully silent
    assert len(ir.bars[2].events) == 0
    assert len(ir.bars[3].events) == 0
    # bar 1 untouched
    assert len(ir.bars[0].events) > 0


def test_break_from_bar_1_silences_whole_section():
    """``break on bar 1`` silences the entire section."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 3
  groove: "g"
  break on bar 1
"""
    ir = _compile(src)
    for bar in ir.bars:
        assert len(bar.events) == 0


# ---------------------------------------------------------------------------
# Through forms: break has an explicit end
# ---------------------------------------------------------------------------

def test_break_through_explicit_end_bar():
    """``break on bar 1 beat 3 through bar 2`` silences bar 1 from beat 3
    and all of bar 2; bar 3 resumes."""
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

    assert Fraction(0) in _positions(bar1)
    assert Fraction(1, 4) in _positions(bar1)
    assert Fraction(2, 4) not in _positions(bar1)
    assert len(bar2.events) == 0
    assert len(bar3.events) > 0


def test_break_through_with_end_beat():
    """``break on bar 1 beat 3 through bar 2 beat 2`` silences bar 1 from
    beat 3 and bar 2 up to and including beat 2; beat 3 of bar 2 resumes."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 1 beat 3 through bar 2 beat 2
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    bar2 = ir.bars[1]

    # bar 1: beats 1-2 survive; beat 3+ gone
    assert Fraction(0) in _positions(bar1)
    assert Fraction(1, 4) in _positions(bar1)
    assert Fraction(2, 4) not in _positions(bar1)

    # bar 2: beats 1-2 (positions <= 1/4) gone; beat 3+ survives
    assert Fraction(0) not in _positions(bar2)
    assert Fraction(1, 4) not in _positions(bar2)
    assert Fraction(2, 4) in _positions(bar2)
    assert Fraction(3, 4) in _positions(bar2)

    # bar 3 and 4 untouched
    assert len(ir.bars[2].events) > 0
    assert len(ir.bars[3].events) > 0


def test_break_range_without_beats():
    """``break on bar 2 through bar 3`` silences bars 2 and 3; bars 1 and 4
    are untouched."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 2 through bar 3
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) > 0    # bar 1 intact
    assert len(ir.bars[1].events) == 0   # bar 2 silent
    assert len(ir.bars[2].events) == 0   # bar 3 silent
    assert len(ir.bars[3].events) > 0    # bar 4 intact


def test_break_range_with_end_beat_only():
    """``break on bar 1 through bar 2 beat 3`` silences all of bar 1 and bar 2
    through beat 3; beat 4 of bar 2 survives."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 3
  groove: "g"
  break on bar 1 through bar 2 beat 3
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    bar2 = ir.bars[1]

    assert len(bar1.events) == 0
    assert Fraction(0) not in _positions(bar2)
    assert Fraction(2, 4) not in _positions(bar2)
    assert Fraction(3, 4) in _positions(bar2)


def test_break_through_same_bar_is_single_bar():
    """``break on bar 3 through bar 3`` silences only bar 3."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 3 through bar 3
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) > 0
    assert len(ir.bars[1].events) > 0
    assert len(ir.bars[2].events) == 0   # bar 3 only
    assert len(ir.bars[3].events) > 0


# ---------------------------------------------------------------------------
# Multiple breaks
# ---------------------------------------------------------------------------

def test_multiple_breaks_with_explicit_range():
    """Two ``through``-bounded breaks each silence their own single bar."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 1 through bar 1
  break on bar 3 through bar 3
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) == 0   # bar 1 broken
    assert len(ir.bars[1].events) > 0    # bar 2 intact
    assert len(ir.bars[2].events) == 0   # bar 3 broken
    assert len(ir.bars[3].events) > 0    # bar 4 intact


# ---------------------------------------------------------------------------
# Interaction with other directives
# ---------------------------------------------------------------------------

def test_break_overrides_fill():
    """A fill placed on the same bar as a bounded break: break wins."""
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
  break on bar 1 through bar 1
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) == 0   # break wins over fill
    assert len(ir.bars[1].events) > 0    # bar 2 unaffected


def test_break_overrides_crash_in():
    """crash in fires on bar 1, then a bounded break silences it."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 2
  groove: "g"
  crash in
  break on bar 1 through bar 1
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) == 0
    assert len(ir.bars[1].events) > 0


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_break_start_bar_out_of_range_raises():
    """A break whose start_bar exceeds section length is an error."""
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

def test_break_in_play_section_silences_to_end():
    """Break without ``through`` silences from the given bar to end of play block."""
    src = _STANDARD_GROOVE + """
section "s":
  play:
    groove "g" x4
  break on bar 2
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) > 0    # bar 1 intact
    assert len(ir.bars[1].events) == 0   # bar 2 silent
    assert len(ir.bars[2].events) == 0   # bar 3 silent (break runs to end)
    assert len(ir.bars[3].events) == 0   # bar 4 silent


# ---------------------------------------------------------------------------
# ``until`` forms: exclusive end boundary
# ---------------------------------------------------------------------------

def test_until_beat_excludes_end_beat():
    """``until bar N beat 3`` silences everything before beat 3, exclusive.

    Regression guard: beat 3 itself (and 3e, 3&, 3a) must NOT be silenced,
    whereas they would be silenced with ``through bar N beat 3``.
    """
    src = _STANDARD_GROOVE + """
section "s":
  bars: 2
  groove: "g"
  break on bar 1 beat 1 until bar 1 beat 3
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    # beats 1 and 2 are silenced (positions < 2/4)
    assert Fraction(0) not in _positions(bar1)       # beat 1
    assert Fraction(1, 8) not in _positions(bar1)    # beat 1&
    assert Fraction(1, 4) not in _positions(bar1)    # beat 2
    assert Fraction(3, 8) not in _positions(bar1)    # beat 2&
    # beat 3 and beyond survive (position >= 2/4)
    assert Fraction(2, 4) in _positions(bar1)        # beat 3
    assert Fraction(3, 8) not in _positions(bar1)    # beat 2& (already confirmed)
    assert Fraction(3, 4) in _positions(bar1)        # beat 4


def test_until_vs_through_difference():
    """``until beat 3`` silences 2& and 2a; ``through beat 2`` does not."""
    src = _STANDARD_GROOVE + """
section "through":
  bars: 1
  groove: "g"
  break on bar 1 beat 1 through bar 1 beat 2

section "until":
  bars: 1
  groove: "g"
  break on bar 1 beat 1 until bar 1 beat 3
"""
    ir = _compile(src)
    through_bar = ir.bars[0]
    until_bar = ir.bars[1]

    # ``through beat 2``: beat 2 (1/4) is silenced, but 2& (3/8) survives
    assert Fraction(1, 4) not in _positions(through_bar)
    assert Fraction(3, 8) in _positions(through_bar)   # 2& survives

    # ``until beat 3``: 2& (3/8) is silenced, beat 3 (2/4) survives
    assert Fraction(3, 8) not in _positions(until_bar)  # 2& silenced
    assert Fraction(2, 4) in _positions(until_bar)      # beat 3 survives


def test_until_bar_excludes_that_bar():
    """``until bar 3`` (no beat) silences bars 1-2; bar 3 is the first bar
    that plays."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 1 until bar 3
"""
    ir = _compile(src)
    assert len(ir.bars[0].events) == 0   # bar 1 silent
    assert len(ir.bars[1].events) == 0   # bar 2 silent
    assert len(ir.bars[2].events) > 0    # bar 3 plays
    assert len(ir.bars[3].events) > 0    # bar 4 plays


def test_until_beat_range_cross_bar():
    """``break on bar 2 beat 1 until bar 3 beat 3`` silences bar 2 fully and
    bar 3 beats 1-2 (exclusive of beat 3)."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 2 beat 1 until bar 3 beat 3
"""
    ir = _compile(src)
    bar2 = ir.bars[1]
    bar3 = ir.bars[2]

    assert len(bar2.events) == 0                      # fully silenced
    assert Fraction(0) not in _positions(bar3)        # beat 1 silenced
    assert Fraction(1, 4) not in _positions(bar3)     # beat 2 silenced
    assert Fraction(3, 8) not in _positions(bar3)     # beat 2& silenced
    assert Fraction(2, 4) in _positions(bar3)         # beat 3 survives
    assert Fraction(3, 4) in _positions(bar3)         # beat 4 survives
    assert len(ir.bars[0].events) > 0                 # bar 1 untouched
    assert len(ir.bars[3].events) > 0                 # bar 4 untouched


def test_until_same_bar_is_empty_range():
    """``until bar N`` when start_bar == N produces no silence (empty range)."""
    src = _STANDARD_GROOVE + """
section "s":
  bars: 4
  groove: "g"
  break on bar 3 until bar 3
"""
    ir = _compile(src)
    for bar in ir.bars:
        assert len(bar.events) > 0   # nothing silenced
