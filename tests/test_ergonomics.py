"""Tests for DSL ergonomics features: star exclusion, bar-level inheritance,
and groove extension."""

from fractions import Fraction
from pathlib import Path

import pytest

from groovescript.ast_nodes import (
    BeatHit,
    Groove,
    Metadata,
    PatternLine,
    Section,
    Song,
    StarSpec,
)
from groovescript.compiler import compile_groove, compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_fixture_ergonomics():
    """End-to-end: ergonomics.gs exercises all three ergonomics features
    (star exclusion, bar-level `like:`, groove `extend:`) in one song."""
    song = parse_file(str(FIXTURES / "ergonomics.gs"))
    assert song.metadata.title == "Ergonomics Features Demo"

    # Star exclusion: open hat pattern excludes 2a, 4a.
    open_hat = next(g for g in song.grooves if g.name == "open hat pattern")
    hh_line = next(p for p in open_hat.bars[0] if p.instrument == "HH")
    assert isinstance(hh_line.beats, StarSpec)
    assert hh_line.beats.except_beats == ("2a", "4a")

    # Bar-level inheritance: two-bar groove's bar 2 references bar 1.
    two_bar = next(g for g in song.grooves if g.name == "two bar inherited")
    assert len(two_bar.bars) == 2

    # Groove extension: "rock with crash" extends "open hat pattern".
    extended = next(g for g in song.grooves if g.name == "rock with crash")
    assert extended.extend == "open hat pattern"

    # Whole song compiles and emits.
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "drummode" in ly


# ---------------------------------------------------------------------------
# B5: Star exclusion syntax  (*N except beat_list)
# ---------------------------------------------------------------------------


class TestStarExclusion:
    """Tests for ``*N except <beat_list>`` pattern-line syntax."""

    def test_parse_star_except_basic(self):
        """``*8 except 2, 4`` parses into a StarSpec with except_beats."""
        song = parse("""\
groove "hat":
    HH: *8 except 2, 4

section "s":
  bars: 1
  groove: "hat"
""")
        pattern = song.grooves[0].bars[0]
        hh = [p for p in pattern if p.instrument == "HH"][0]
        assert isinstance(hh.beats, StarSpec)
        assert hh.beats.note_value == 8
        assert hh.beats.except_beats == ("2", "4")

    def test_parse_star_except_16th_suffixes(self):
        """``*16 except 2a, 4a`` correctly parses 16th-note beat labels."""
        song = parse("""\
groove "hat":
    HH: *16 except 2a, 4a

section "s":
  bars: 1
  groove: "hat"
""")
        hh = [p for p in song.grooves[0].bars[0] if p.instrument == "HH"][0]
        assert isinstance(hh.beats, StarSpec)
        assert hh.beats.note_value == 16
        assert hh.beats.except_beats == ("2a", "4a")

    def test_parse_star_except_without_commas(self):
        """Comma-free form ``*16 except 2a 4a`` is preprocessed correctly."""
        song = parse("""\
groove "hat":
    HH: *16 except 2a 4a

section "s":
  bars: 1
  groove: "hat"
""")
        hh = [p for p in song.grooves[0].bars[0] if p.instrument == "HH"][0]
        assert hh.beats.except_beats == ("2a", "4a")

    def test_compile_star_except_excludes_positions(self):
        """Excluded beats are omitted from the expanded star pattern."""
        groove = Groove(
            name="hat",
            bars=[[PatternLine(instrument="HH", beats=StarSpec(note_value=8, except_beats=("2", "4")))]],
        )
        ir = compile_groove(groove)
        hh_positions = sorted(e.beat_position for e in ir.events if e.instrument == "HH")
        # *8 in 4/4 produces 8 hits; except 2, 4 removes 2 → 6 hits
        assert len(hh_positions) == 6
        # Beat 2 = 1/4, Beat 4 = 3/4 should NOT be present
        assert Fraction(1, 4) not in hh_positions
        assert Fraction(3, 4) not in hh_positions

    def test_compile_star_except_16th_gaps(self):
        """``*16 except 2a, 4a`` produces 14 hits (16 - 2 exclusions)."""
        groove = Groove(
            name="hat16",
            bars=[[PatternLine(instrument="HH", beats=StarSpec(note_value=16, except_beats=("2a", "4a")))]],
        )
        ir = compile_groove(groove)
        hh_positions = sorted(e.beat_position for e in ir.events if e.instrument == "HH")
        assert len(hh_positions) == 14
        # 2a = Fraction(7, 16), 4a = Fraction(15, 16)
        assert Fraction(7, 16) not in hh_positions
        assert Fraction(15, 16) not in hh_positions

    def test_compile_star_except_triplet(self):
        """``*8t except 2t`` excludes the triplet position."""
        groove = Groove(
            name="trip",
            bars=[[PatternLine(instrument="HH", beats=StarSpec(note_value=8, triplet=True, except_beats=("2t",)))]],
        )
        ir = compile_groove(groove)
        hh_positions = sorted(e.beat_position for e in ir.events if e.instrument == "HH")
        # *8t in 4/4: 8th triplets = 12 hits; minus 1 = 11
        assert len(hh_positions) == 11
        # 2t = beat 2, triplet subdivision → (1 + 1/3) / 4
        excluded_pos = (Fraction(1) + Fraction(1, 3)) / 4
        assert excluded_pos not in hh_positions

    def test_compile_full_song_star_except(self):
        """End-to-end: star except compiles through the full pipeline."""
        song = parse("""\
groove "open hat":
    BD: 1, 3
    SN: 2, 4
    HH: *8 except 2, 4
    OH: 2, 4

section "verse":
  bars: 2
  groove: "open hat"
""")
        ir = compile_song(song)
        bar1 = ir.bars[0]
        hh_positions = {e.beat_position for e in bar1.events if e.instrument == "HH"}
        oh_positions = {e.beat_position for e in bar1.events if e.instrument == "OH"}
        # HH should NOT be at beats 2 and 4
        assert Fraction(1, 4) not in hh_positions
        assert Fraction(3, 4) not in hh_positions
        # OH should be at beats 2 and 4
        assert Fraction(1, 4) in oh_positions
        assert Fraction(3, 4) in oh_positions

    def test_star_except_str_representation(self):
        """StarSpec.__str__ includes the except clause when present."""
        spec = StarSpec(note_value=16, except_beats=("2a", "4a"))
        assert str(spec) == "*16 except 2a, 4a"

    def test_star_except_str_without_exclusions(self):
        """StarSpec.__str__ omits except when no exclusions."""
        spec = StarSpec(note_value=8)
        assert str(spec) == "*8"

    def test_star_except_bare_suffix_expansion(self):
        """Bare suffix tokens in except list are expanded (e.g. ``1 and``)."""
        song = parse("""\
groove "hat":
    HH: *8 except 1 and 3 and

section "s":
  bars: 1
  groove: "hat"
""")
        hh = [p for p in song.grooves[0].bars[0] if p.instrument == "HH"][0]
        assert hh.beats.except_beats == ("1", "1&", "3", "3&")


# ---------------------------------------------------------------------------
# A3: Bar-level inheritance  (like: bar N)
# ---------------------------------------------------------------------------


class TestBarLevelInheritance:
    """Tests for ``like: bar N`` within multi-bar groove patterns."""

    def test_parse_like_bar(self):
        """``like: bar 1`` in bar 2 copies bar 1's pattern lines."""
        song = parse("""\
groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      like: bar 1
      BD: 1, 2&, 4

section "s":
  bars: 2
  groove: "two bar"
""")
        groove = song.grooves[0]
        assert len(groove.bars) == 2
        bar1_instruments = {p.instrument for p in groove.bars[0]}
        bar2_instruments = {p.instrument for p in groove.bars[1]}
        # Bar 2 should have BD (overridden), SN (inherited), HH (inherited)
        assert bar2_instruments == {"BD", "SN", "HH"}
        assert bar1_instruments == {"BD", "SN", "HH"}

    def test_compile_like_bar_overrides_instrument(self):
        """Bar 2 with ``like: bar 1`` + ``BD: 1, 2&, 4`` overrides only BD."""
        song = parse("""\
groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      like: bar 1
      BD: 1, 2&, 4

section "s":
  bars: 2
  groove: "two bar"
""")
        ir = compile_song(song)
        bar2 = ir.bars[1]
        bd_positions = sorted(e.beat_position for e in bar2.events if e.instrument == "BD")
        # BD in bar 2: 1, 2&, 4 → positions 0, 3/8, 3/4
        assert bd_positions == [Fraction(0), Fraction(3, 8), Fraction(3, 4)]
        # SN inherited from bar 1: beats 2, 4 → positions 1/4, 3/4
        sn_positions = sorted(e.beat_position for e in bar2.events if e.instrument == "SN")
        assert sn_positions == [Fraction(1, 4), Fraction(3, 4)]
        # HH inherited from bar 1: *8 → 8 positions
        hh_count = len([e for e in bar2.events if e.instrument == "HH"])
        assert hh_count == 8

    def test_compile_like_bar_adds_new_instrument(self):
        """Bar 2 with ``like: bar 1`` can add a new instrument not in bar 1."""
        song = parse("""\
groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
    bar 2:
      like: bar 1
      CR: 1

section "s":
  bars: 2
  groove: "two bar"
""")
        ir = compile_song(song)
        bar2 = ir.bars[1]
        bar2_instruments = {e.instrument for e in bar2.events}
        assert "BD" in bar2_instruments  # inherited
        assert "SN" in bar2_instruments  # inherited
        assert "CR" in bar2_instruments  # added

    def test_like_bar_pure_copy(self):
        """``like: bar 1`` with no overrides produces an identical copy of bar 1."""
        song = parse("""\
groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      like: bar 1

section "s":
  bars: 2
  groove: "two bar"
""")
        ir = compile_song(song)
        bar1_events = sorted(
            (e.beat_position, e.instrument) for e in ir.bars[0].events
        )
        bar2_events = sorted(
            (e.beat_position, e.instrument) for e in ir.bars[1].events
        )
        assert bar1_events == bar2_events

    def test_like_bar_unknown_reference_raises(self):
        """Referencing a non-existent bar raises ValueError."""
        with pytest.raises(Exception, match="bar 5"):
            parse("""\
groove "bad":
    bar 1:
      BD: 1, 3
    bar 2:
      like: bar 5
      SN: 2, 4

section "s":
  bars: 2
  groove: "bad"
""")

    def test_like_bar_three_bars(self):
        """Bar 3 can reference bar 1, and bar 2 stays independent."""
        song = parse("""\
groove "three bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1
      SN: 3
    bar 3:
      like: bar 1
      CR: 1

section "s":
  bars: 3
  groove: "three bar"
""")
        ir = compile_song(song)
        # Bar 2 should only have BD and SN (no HH, no CR)
        bar2_instruments = {e.instrument for e in ir.bars[1].events}
        assert bar2_instruments == {"BD", "SN"}
        # Bar 3 should have BD, SN, HH (inherited) + CR (added)
        bar3_instruments = {e.instrument for e in ir.bars[2].events}
        assert bar3_instruments == {"BD", "SN", "HH", "CR"}


# ---------------------------------------------------------------------------
# E11: Groove extension  (extend: keyword)
# ---------------------------------------------------------------------------


class TestGrooveExtension:
    """Tests for ``extend: "base_groove"`` groove inheritance."""

    def test_parse_extend_no_pattern(self):
        """``extend: "rock"`` with no pattern block copies rock verbatim."""
        song = parse("""\
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "rock with crash":
  extend: "rock"

section "s":
  bars: 1
  groove: "rock with crash"
""")
        # After parsing, extend is set but bars may be empty (resolution
        # happens at compile time).
        groove = [g for g in song.grooves if g.name == "rock with crash"][0]
        assert groove.extend == "rock"

    def test_compile_extend_copies_base(self):
        """An extend-only groove (no pattern overrides) compiles identically to the base."""
        song = parse("""\
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "rock copy":
  extend: "rock"

section "a":
  bars: 1
  groove: "rock"

section "b":
  bars: 1
  groove: "rock copy"
""")
        ir = compile_song(song)
        rock_events = sorted(
            (e.beat_position, e.instrument) for e in ir.bars[0].events
        )
        copy_events = sorted(
            (e.beat_position, e.instrument) for e in ir.bars[1].events
        )
        assert rock_events == copy_events

    def test_compile_extend_adds_instrument(self):
        """Extending with a new instrument adds it on top of the base."""
        song = parse("""\
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "rock with crash":
  extend: "rock"
    CR: 1

section "s":
  bars: 1
  groove: "rock with crash"
""")
        ir = compile_song(song)
        bar = ir.bars[0]
        instruments = {e.instrument for e in bar.events}
        assert instruments == {"BD", "SN", "HH", "CR"}
        # CR at beat 1 (position 0)
        cr_positions = [e.beat_position for e in bar.events if e.instrument == "CR"]
        assert cr_positions == [Fraction(0)]

    def test_compile_extend_overrides_instrument(self):
        """Extending with an existing instrument replaces the base's line for that instrument."""
        song = parse("""\
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "half-time rock":
  extend: "rock"
    BD: 1
    SN: 3

section "s":
  bars: 1
  groove: "half-time rock"
""")
        ir = compile_song(song)
        bar = ir.bars[0]
        bd_positions = sorted(e.beat_position for e in bar.events if e.instrument == "BD")
        sn_positions = sorted(e.beat_position for e in bar.events if e.instrument == "SN")
        # BD overridden: only beat 1
        assert bd_positions == [Fraction(0)]
        # SN overridden: only beat 3
        assert sn_positions == [Fraction(1, 2)]
        # HH inherited: still *8
        hh_count = len([e for e in bar.events if e.instrument == "HH"])
        assert hh_count == 8

    def test_compile_extend_chain(self):
        """Grooves can chain: C extends B extends A."""
        song = parse("""\
groove "base":
    BD: 1, 3
    SN: 2, 4

groove "with hat":
  extend: "base"
    HH: *8

groove "with crash":
  extend: "with hat"
    CR: 1

section "s":
  bars: 1
  groove: "with crash"
""")
        ir = compile_song(song)
        instruments = {e.instrument for e in ir.bars[0].events}
        assert instruments == {"BD", "SN", "HH", "CR"}

    def test_compile_extend_unknown_base_raises(self):
        """Extending a non-existent groove raises ValueError."""
        song = parse("""\
groove "bad":
  extend: "nonexistent"

section "s":
  bars: 1
  groove: "bad"
""")
        with pytest.raises(ValueError, match="unknown groove"):
            compile_song(song)

    def test_compile_extend_multi_bar_base(self):
        """Extending a multi-bar groove inherits all bars."""
        song = parse("""\
groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 2&, 4
      SN: 2, 4
      HH: *8

groove "two bar crash":
  extend: "two bar"
    CR: 1

section "s":
  bars: 2
  groove: "two bar crash"
""")
        ir = compile_song(song)
        # Both bars should have CR at beat 1
        for bar in ir.bars:
            instruments = {e.instrument for e in bar.events}
            assert "CR" in instruments
            assert "BD" in instruments
            assert "SN" in instruments
            assert "HH" in instruments

    def test_compile_extend_library_groove(self):
        """A groove can extend a built-in library groove."""
        song = parse("""\
groove "rock with crash":
  extend: "rock"
    CR: 1

section "s":
  bars: 1
  groove: "rock with crash"
""")
        ir = compile_song(song)
        instruments = {e.instrument for e in ir.bars[0].events}
        assert "CR" in instruments
        assert "BD" in instruments
        assert "HH" in instruments

    def test_compile_extend_preserves_base_unchanged(self):
        """Using extend does not mutate the base groove."""
        song = parse("""\
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "rock with crash":
  extend: "rock"
    CR: 1

section "a":
  bars: 1
  groove: "rock"

section "b":
  bars: 1
  groove: "rock with crash"
""")
        ir = compile_song(song)
        # rock (bar 1) should NOT have CR
        rock_instruments = {e.instrument for e in ir.bars[0].events}
        assert "CR" not in rock_instruments
        assert rock_instruments == {"BD", "SN", "HH"}
        # rock with crash (bar 2) should have CR
        extended_instruments = {e.instrument for e in ir.bars[1].events}
        assert "CR" in extended_instruments
