"""Tests for the ``crash in`` section flag.

Covers riding-instrument detection across different instruments and
subdivisions, modifier handling, and interactions with ``play:`` blocks,
``like`` inheritance, variations, and fills at bar 1.
"""

from fractions import Fraction

import pytest

from groovescript.compiler import compile_song
from groovescript.parser import parse


def _compile(src: str):
    return compile_song(parse(src))


def _events_at(bar, position: Fraction):
    return [e for e in bar.events if e.beat_position == position]


def _instruments_at(bar, position: Fraction) -> set[str]:
    return {e.instrument for e in _events_at(bar, position)}


# ── Riding detection across instruments ───────────────────────────────

def test_crash_in_replaces_hihat_rider():
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 2
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    # First HH hit is gone; a CR sits on beat 1 alongside the BD.
    assert _instruments_at(bar1, Fraction(0)) == {"CR", "BD"}
    # The rest of the HH pattern is intact.
    hh_positions = sorted(e.beat_position for e in bar1.events if e.instrument == "HH")
    assert hh_positions == [Fraction(i, 8) for i in range(1, 8)]
    # Bar 2 is untouched.
    assert "HH" in _instruments_at(ir.bars[1], Fraction(0))
    assert "CR" not in _instruments_at(ir.bars[1], Fraction(0))


def test_crash_in_replaces_ride_rider_quarters():
    src = """
groove "g":
  RD: *4
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    assert _instruments_at(bar1, Fraction(0)) == {"CR", "BD"}
    # RD keeps its other three quarter-note hits.
    rd_positions = sorted(e.beat_position for e in bar1.events if e.instrument == "RD")
    assert rd_positions == [Fraction(1, 4), Fraction(2, 4), Fraction(3, 4)]


def test_crash_in_replaces_open_hihat_rider_sixteenths():
    src = """
groove "g":
  OH: *16
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    assert _instruments_at(bar1, Fraction(0)) == {"CR", "BD"}
    oh_positions = sorted(e.beat_position for e in bar1.events if e.instrument == "OH")
    assert oh_positions == [Fraction(i, 16) for i in range(1, 16)]


def test_crash_in_replaces_floor_tom_rider():
    """Rosanna-style floor-tom groove: crash in rides into the tom groove."""
    src = """
groove "g":
  FT: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    assert _instruments_at(bar1, Fraction(0)) == {"CR", "BD"}
    ft_positions = sorted(e.beat_position for e in bar1.events if e.instrument == "FT")
    assert ft_positions == [Fraction(i, 8) for i in range(1, 8)]


# ── Fallbacks when the rider has no beat-1 hit ────────────────────────

def test_crash_in_falls_back_to_beat_one_when_rider_misses_one():
    """HH: *8 except 1 — no HH on beat 1. Crash is added, HH stays excluded."""
    src = """
groove "g":
  HH: *8 except 1
  BD: 1

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    assert _instruments_at(bar1, Fraction(0)) == {"CR", "BD"}
    # HH beat-1 hit was not resurrected — the user excluded it.
    hh_positions = {e.beat_position for e in bar1.events if e.instrument == "HH"}
    assert Fraction(0) not in hh_positions


def test_crash_in_falls_back_when_no_star_pattern():
    """Explicit beats only — unclear rider; fallback: add CR on beat 1."""
    src = """
groove "g":
  BD: 1, 3
  SN: 2, 4
  HH: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    # No rider has a hit on beat 1, so a CR is simply added.
    assert "CR" in _instruments_at(bar1, Fraction(0))
    assert "BD" in _instruments_at(bar1, Fraction(0))
    # HH hits on 2 and 4 survive.
    hh_positions = sorted(e.beat_position for e in bar1.events if e.instrument == "HH")
    assert hh_positions == [Fraction(1, 4), Fraction(3, 4)]


# ── Modifier preservation rules ───────────────────────────────────────

def test_crash_in_preserves_accent_on_replaced_hit():
    src = """
groove "g":
  HH: 1 accent, 2, 3, 4
  BD: 1

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    cr_events = [e for e in _events_at(bar1, Fraction(0)) if e.instrument == "CR"]
    assert len(cr_events) == 1
    assert "accent" in cr_events[0].modifiers


def test_crash_in_strips_ghost_on_replaced_hit():
    """A ghosted crash is unconventional; ghost is dropped."""
    src = """
groove "g":
  HH: 1 ghost, 2, 3, 4
  BD: 1

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    cr_events = [e for e in _events_at(bar1, Fraction(0)) if e.instrument == "CR"]
    assert len(cr_events) == 1
    assert "ghost" not in cr_events[0].modifiers


# ── No-op / idempotent cases ──────────────────────────────────────────

def test_crash_in_no_op_when_crash_already_on_beat_one():
    src = """
groove "g":
  CR: 1
  HH: *8 except 1
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    cr_positions = [e.beat_position for e in bar1.events if e.instrument == "CR"]
    # Exactly one CR on beat 1 — we didn't add a duplicate.
    assert cr_positions == [Fraction(0)]


def test_crash_in_only_affects_first_bar():
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 4
  groove: "g"
  crash in
"""
    ir = _compile(src)
    for bar in ir.bars[1:]:
        assert "CR" not in _instruments_at(bar, Fraction(0))
        assert "HH" in _instruments_at(bar, Fraction(0))


# ── Interactions with other section features ─────────────────────────

def test_crash_in_applies_to_first_bar_of_play_block():
    """With ``play:``, crash-in targets the first bar of the first item."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  play:
    groove "g" x2
    groove "g"
  crash in
"""
    ir = _compile(src)
    # First bar of first play item has the crash.
    assert _instruments_at(ir.bars[0], Fraction(0)) == {"CR", "BD"}
    # Second bar of the first item is unchanged.
    assert "HH" in _instruments_at(ir.bars[1], Fraction(0))


def test_crash_in_is_inherited_through_like():
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "parent":
  bars: 1
  groove: "g"
  crash in

section "child":
  like "parent"
"""
    ir = _compile(src)
    # parent bar
    assert _instruments_at(ir.bars[0], Fraction(0)) == {"CR", "BD"}
    # child bar (inheriting crash in)
    assert _instruments_at(ir.bars[1], Fraction(0)) == {"CR", "BD"}


def test_crash_in_still_applies_when_fill_replaces_bar_one():
    """Regression: fills at bar 1 shouldn't silently swallow crash-in."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 2
  groove: "g"
  crash in
  fill at bar 1:
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
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    # The fill replaces bar 1 with sixteenth-note SN hits; crash-in adds CR on 1.
    assert "CR" in _instruments_at(bar1, Fraction(0))


def test_crash_in_absent_without_flag():
    """Regression: sections without ``crash in`` compile exactly as before."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    assert "CR" not in _instruments_at(bar1, Fraction(0))
    assert "HH" in _instruments_at(bar1, Fraction(0))


# ── Tiebreak among cymbals with equal hit counts ─────────────────────

def test_crash_in_adds_kick_when_missing():
    """Regression: crash in guarantees a BD on beat 1 (crash + kick pair)."""
    src = """
groove "g":
  HH: *8
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    instruments = _instruments_at(bar1, Fraction(0))
    assert "CR" in instruments
    assert "BD" in instruments


def test_crash_in_does_not_duplicate_existing_kick():
    """A BD already on beat 1 stays single; we don't append a duplicate."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    bd_on_one = [e for e in bar1.events if e.instrument == "BD" and e.beat_position == Fraction(0)]
    assert len(bd_on_one) == 1


def test_crash_in_adds_kick_even_when_crash_already_on_one():
    """If CR is already on beat 1 but no BD is, crash-in still adds the BD."""
    src = """
groove "g":
  CR: 1
  HH: *8 except 1
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    instruments = _instruments_at(bar1, Fraction(0))
    assert "CR" in instruments
    assert "BD" in instruments
    # Crash not duplicated.
    cr_on_one = [e for e in bar1.events if e.instrument == "CR" and e.beat_position == Fraction(0)]
    assert len(cr_on_one) == 1


def test_crash_in_tiebreak_prefers_ride_over_hihat():
    """When RD and HH tie on hit count, RD wins the rider role."""
    src = """
groove "g":
  RD: 1, 2, 3, 4
  HH: 1, 2, 3, 4
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  crash in
"""
    ir = _compile(src)
    bar1 = ir.bars[0]
    # RD beat-1 hit is replaced; HH beat-1 hit survives.
    instruments = _instruments_at(bar1, Fraction(0))
    assert "CR" in instruments
    assert "HH" in instruments
    assert "RD" not in instruments


# ── Multi-bar `crash in at <bars>` ────────────────────────────────────

def test_crash_in_at_explicit_bar_list():
    """``crash in at 1, 5`` crashes into bars 1 and 5 (and only those)."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 8
  groove: "g"
  crash in at 1, 5
"""
    ir = _compile(src)
    for offset, bar in enumerate(ir.bars):
        present = "CR" in _instruments_at(bar, Fraction(0))
        if offset in (0, 4):
            assert present, f"bar {offset + 1} should have a crash"
        else:
            assert not present, f"bar {offset + 1} must not have a crash"
            assert "HH" in _instruments_at(bar, Fraction(0))


def test_crash_in_at_explicit_bars_no_commas():
    """The preprocessor commafies the bar list — `crash in at 1 5` must work."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 8
  groove: "g"
  crash in at 1 5
"""
    ir = _compile(src)
    crashing_bars = [
        offset for offset, bar in enumerate(ir.bars)
        if "CR" in _instruments_at(bar, Fraction(0))
    ]
    assert crashing_bars == [0, 4]


def test_crash_in_at_star_every_n_bars():
    """``crash in at *8`` crashes into bars 1, 9, 17, … of the section."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 24
  groove: "g"
  crash in at *8
"""
    ir = _compile(src)
    crashing_bars = [
        offset for offset, bar in enumerate(ir.bars)
        if "CR" in _instruments_at(bar, Fraction(0))
    ]
    assert crashing_bars == [0, 8, 16]


def test_crash_in_at_star_rejects_triplet_grid():
    """``*8t`` makes no sense for a bar count — reject at parse time."""
    src = """
groove "g":
  HH: *8
  BD: 1
section "s":
  bars: 4
  groove: "g"
  crash in at *8t
"""
    with pytest.raises(Exception):
        _compile(src)


# ── Top-level ``crash in`` with per-section opt-out ──────────────────

def test_top_level_crash_in_skips_first_section():
    """Top-level ``crash in`` crashes into every section after the first."""
    src = """
crash in

groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "intro":
  bars: 1
  groove: "g"

section "verse":
  bars: 1
  groove: "g"

section "chorus":
  bars: 1
  groove: "g"
"""
    ir = _compile(src)
    # First section: no crash.
    assert "CR" not in _instruments_at(ir.bars[0], Fraction(0))
    # Subsequent sections: crash on bar 1.
    assert "CR" in _instruments_at(ir.bars[1], Fraction(0))
    assert "CR" in _instruments_at(ir.bars[2], Fraction(0))


def test_top_level_crash_in_respects_no_crash_in():
    """A section with ``no crash in`` opts out of the top-level directive."""
    src = """
crash in

groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "intro":
  bars: 1
  groove: "g"

section "bridge":
  bars: 1
  groove: "g"
  no crash in

section "chorus":
  bars: 1
  groove: "g"
"""
    ir = _compile(src)
    # intro: untouched (first section)
    assert "CR" not in _instruments_at(ir.bars[0], Fraction(0))
    # bridge: opted out
    assert "CR" not in _instruments_at(ir.bars[1], Fraction(0))
    # chorus: still crashes
    assert "CR" in _instruments_at(ir.bars[2], Fraction(0))


def test_top_level_crash_in_lets_section_override_with_explicit_spec():
    """An explicit ``crash in at …`` on a section beats the top-level default."""
    src = """
crash in

groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "intro":
  bars: 1
  groove: "g"

section "verse":
  bars: 8
  groove: "g"
  crash in at 1, 5
"""
    ir = _compile(src)
    # intro
    assert "CR" not in _instruments_at(ir.bars[0], Fraction(0))
    # verse: bars 1 and 5 of the section (= ir.bars[1] and ir.bars[5])
    assert "CR" in _instruments_at(ir.bars[1], Fraction(0))
    assert "CR" not in _instruments_at(ir.bars[2], Fraction(0))
    assert "CR" in _instruments_at(ir.bars[5], Fraction(0))
    assert "CR" not in _instruments_at(ir.bars[6], Fraction(0))


def test_no_crash_in_without_top_level_is_a_no_op():
    """``no crash in`` on a section that wasn't going to crash anyway is harmless."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  no crash in
"""
    ir = _compile(src)
    assert "CR" not in _instruments_at(ir.bars[0], Fraction(0))


def test_no_crash_in_overrides_inherited_crash_in():
    """``no crash in`` on a child section cancels a crash-in inherited via ``like``."""
    src = """
groove "g":
  HH: *8
  BD: 1, 3
  SN: 2, 4

section "parent":
  bars: 1
  groove: "g"
  crash in

section "child":
  like "parent"
  no crash in
"""
    ir = _compile(src)
    # parent crashes
    assert "CR" in _instruments_at(ir.bars[0], Fraction(0))
    # child inherited the crash but explicitly opted out
    assert "CR" not in _instruments_at(ir.bars[1], Fraction(0))
    assert "HH" in _instruments_at(ir.bars[1], Fraction(0))


def test_section_cannot_combine_crash_in_and_no_crash_in():
    """Mixing ``crash in`` and ``no crash in`` in one section is a parse error."""
    src = """
groove "g":
  HH: *8
  BD: 1
section "s":
  bars: 1
  groove: "g"
  crash in
  no crash in
"""
    with pytest.raises(Exception):
        _compile(src)


def test_top_level_crash_in_declared_twice_is_an_error():
    """Two top-level ``crash in`` directives in one file is a parse error."""
    src = """
crash in
crash in

groove "g":
  HH: *8
  BD: 1
section "s":
  bars: 1
  groove: "g"
"""
    with pytest.raises(Exception):
        _compile(src)
