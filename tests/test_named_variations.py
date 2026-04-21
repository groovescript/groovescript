"""Tests for reusable named variations and the built-in variation library.

Covers the parser (top-level ``variation "name":`` definitions and
name-only section references) plus the compiler's resolution of those
references against user-defined defs and the ``variation_library.gs``
built-ins.
"""

from fractions import Fraction

import pytest

from groovescript.ast_nodes import Variation, VariationAction, VariationDef
from groovescript.compiler import compile_song
from groovescript.errors import GrooveScriptError
from groovescript.library import get_library_variations
from groovescript.parser import parse


def test_parse_top_level_variation_def():
    """Top-level ``variation "name":`` is captured as a :class:`VariationDef`
    on ``Song.variations`` (parallel to grooves and fills)."""
    song = parse(
        """
        variation "my-var":
          add CR at 1
          replace HH with OH at 4
        """
    )
    assert len(song.variations) == 1
    v = song.variations[0]
    assert isinstance(v, VariationDef)
    assert v.name == "my-var"
    assert [a.action for a in v.actions] == ["add", "replace"]


def test_parse_name_only_section_variation_ref():
    """A section line of the form ``variation "foo" at bar N`` (no colon,
    no body) is parsed as an empty-actions :class:`Variation` — a
    reference the compiler will resolve by name."""
    song = parse(
        """
        section "A":
          bars: 4
          groove: "rock"
          variation "open-hat-4" at bar 2
        """
    )
    section = song.sections[0]
    assert len(section.variations) == 1
    ref = section.variations[0]
    assert isinstance(ref, Variation)
    assert ref.name == "open-hat-4"
    assert ref.bars == [2]
    assert ref.actions == []


def test_named_variation_reused_across_sections():
    """A single top-level variation can be referenced from multiple
    sections and multiple bars — this is the primary reuse feature."""
    song = parse(
        """
        variation "crash-on-one":
          add CR at 1

        section "A":
          bars: 2
          groove: "rock"
          variation "crash-on-one" at bar 1

        section "B":
          bars: 2
          groove: "rock"
          variation "crash-on-one" at bars 1, 2
        """
    )
    ir = compile_song(song)
    crash_bars = {
        bar.number
        for bar in ir.bars
        if any(e.instrument == "CR" for e in bar.events)
    }
    # Section A bar 1 = global bar 1; Section B = global bars 3, 4.
    assert crash_bars == {1, 3, 4}


def test_named_variation_reference_with_multi_bar_list():
    """A single reference can target several bars at once."""
    song = parse(
        """
        variation "drop-snare-bar":
          remove SN at *

        section "Break":
          bars: 4
          groove: "rock"
          variation "drop-snare-bar" at bars 2, 4
        """
    )
    ir = compile_song(song)
    snare_bars = {
        bar.number for bar in ir.bars if any(e.instrument == "SN" for e in bar.events)
    }
    # SN present in bars 1 and 3, removed in bars 2 and 4.
    assert snare_bars == {1, 3}


def test_inline_variation_still_works_alongside_named_defs():
    """Regression: inline variation blocks (with a body) must continue to
    work even when top-level defs exist in the same file."""
    song = parse(
        """
        variation "my-var":
          add CR at 1

        section "A":
          bars: 1
          groove: "rock"
          variation at bar 1:
            remove BD at *
        """
    )
    ir = compile_song(song)
    assert not any(e.instrument == "BD" for e in ir.bars[0].events)


def test_unknown_variation_reference_raises():
    """Referencing a name with no matching top-level def or library entry
    produces a diagnostic error rather than silently doing nothing."""
    song = parse(
        """
        section "A":
          bars: 1
          groove: "rock"
          variation "does-not-exist" at bar 1
        """
    )
    with pytest.raises(GrooveScriptError, match="does-not-exist"):
        compile_song(song)


def test_library_variation_resolves_without_local_def():
    """A library variation resolves at compile time when the user's file
    makes no corresponding top-level definition."""
    song = parse(
        """
        section "A":
          bars: 1
          groove: "rock"
          variation "open-hat-4" at bar 1
        """
    )
    ir = compile_song(song)
    bar = ir.bars[0]
    # "open-hat-4" replaces the HH on beat 4 with OH — so there is exactly
    # one OH event at position 3/4 (beat 4) and no HH at that position.
    oh_events = [e for e in bar.events if e.instrument == "OH"]
    hh_at_beat4 = [
        e for e in bar.events if e.instrument == "HH" and e.beat_position == Fraction(3, 4)
    ]
    assert len(oh_events) == 1
    assert oh_events[0].beat_position == Fraction(3, 4)
    assert hh_at_beat4 == []


def test_user_variation_def_overrides_library():
    """A top-level ``variation "name":`` with the same name as a library
    entry takes precedence — mirrors the groove/fill override behaviour."""
    song = parse(
        """
        variation "open-hat-4":
          add CR at 1

        section "A":
          bars: 1
          groove: "rock"
          variation "open-hat-4" at bar 1
        """
    )
    ir = compile_song(song)
    # Should behave like the overriding def (adds CR at 1), not the library
    # version (which would replace HH with OH at beat 4).
    assert any(
        e.instrument == "CR" and e.beat_position == 0 for e in ir.bars[0].events
    )
    # No OH from the library version.
    assert not any(e.instrument == "OH" for e in ir.bars[0].events)


def test_library_variations_all_load():
    """Smoke test that the bundled variation library parses cleanly and
    every entry has at least one action."""
    lib = get_library_variations()
    assert lib, "variation library should not be empty"
    for name, var_def in lib.items():
        assert var_def.name == name
        assert var_def.actions, f"library variation {name!r} has no actions"


def test_inherited_section_resolves_named_variation():
    """Regression: when a child section inherits variations via
    ``like "parent" with variations``, named references carried over from
    the parent must still resolve against the global variation map."""
    song = parse(
        """
        variation "crash-on-one":
          add CR at 1

        section "A":
          bars: 2
          groove: "rock"
          variation "crash-on-one" at bar 1

        section "B":
          like "A" with variations
        """
    )
    ir = compile_song(song)
    # Bars 1 (section A) and 3 (section B) should each have a CR.
    crash_bars = {
        bar.number
        for bar in ir.bars
        if any(e.instrument == "CR" for e in bar.events)
    }
    assert 1 in crash_bars
    assert 3 in crash_bars
