"""Tests for the tuplet-group feature.

Covers:
  * the brace-aware comma preprocessor (tuplet groups stay atomic in the
    outer pass; commas inside braces are still optional)
  * the parser/transformer building :class:`TupletGroup` AST nodes
  * the compiler resolving slots to ``Fraction`` event positions and
    annotating ``IRBar.beat_tuplets``
  * the validation that rejects two different tuplet kinds on the same beat
  * the LilyPond emitter wrapping each tuplet beat in ``\tuplet N/M { … }``
  * the MusicXML emitter setting ``<time-modification>actual/normal``
  * the ``*<kind>[/8]`` star shorthand
  * the count-form fill body's inline ``{kind …}`` group
"""

from fractions import Fraction

import pytest

from groovescript.compiler import compile_song
from groovescript.errors import GrooveScriptError
from groovescript.lilypond import emit_lilypond
from groovescript.musicxml import emit_musicxml
from groovescript.parser import parse
from groovescript.parser_preprocess import _preprocess_commas


# ---------------------------------------------------------------------------
# Preprocessor — brace groups stay atomic; commas inside are optional
# ---------------------------------------------------------------------------

def test_preprocess_keeps_brace_group_atomic():
    src = "HH: 1 2{sextuplet 1 2 3 4 5 6} 3 4\n"
    out = _preprocess_commas(src)
    assert out == "HH: 1, 2{sextuplet 1, 2, 3, 4, 5, 6}, 3, 4\n"


def test_preprocess_handles_modifiers_inside_brace_group():
    src = "HH: 2{sextuplet 1 accent 4 ghost}\n"
    out = _preprocess_commas(src)
    assert out == "HH: 2{sextuplet 1 accent, 4 ghost}\n"


def test_preprocess_handles_fused_slash_qualifier():
    src = "HH: 2&{triplet/8 1 3}\n"
    out = _preprocess_commas(src)
    assert out == "HH: 2&{triplet/8 1, 3}\n"


def test_preprocess_handles_split_slash_qualifier():
    src = "HH: 2&{triplet /8 1 3}\n"
    out = _preprocess_commas(src)
    assert "{triplet /8 1, 3}" in out


# ---------------------------------------------------------------------------
# Parser / transformer — TupletGroup AST shape
# ---------------------------------------------------------------------------

def _first_pattern_line(src: str, instrument: str = "HH"):
    song = parse(src)
    groove = song.grooves[0]
    for line in groove.bars[0]:
        if line.instrument == instrument:
            return line
    raise AssertionError(f"no {instrument} pattern line in groove")


def test_parser_builds_sextuplet_tuplet_group():
    src = """\
groove "g":
    HH: 1, 2{sextuplet 1, 2, 3, 4, 5, 6}, 3, 4
"""
    line = _first_pattern_line(src)
    # Beat list has: '1', TupletGroup, '3', '4'
    assert len(line.beats) == 4
    tg = line.beats[1]
    assert tg.__class__.__name__ == "TupletGroup"
    assert tg.kind == "sextuplet"
    assert tg.ratio == (6, 4)
    assert tg.span == Fraction(1)
    assert tg.anchor == "2"
    assert [s.index for s in tg.slots] == [1, 2, 3, 4, 5, 6]


def test_parser_rejects_unknown_tuplet_kind():
    src = """\
groove "g":
    HH: 2{undecuplet 1, 2, 3}
"""
    with pytest.raises(GrooveScriptError):
        parse(src)


def test_parser_rejects_out_of_range_slot():
    src = """\
groove "g":
    HH: 2{sextuplet 1, 7}
"""
    with pytest.raises((GrooveScriptError, ValueError)):
        parse(src)


def test_parser_rejects_duplicate_slot():
    src = """\
groove "g":
    HH: 2{sextuplet 1, 1, 4}
"""
    with pytest.raises((GrooveScriptError, ValueError)):
        parse(src)


def test_parser_accepts_half_beat_qualifier():
    src = """\
groove "g":
    HH: 2&{triplet/8 1, 2, 3}
"""
    line = _first_pattern_line(src)
    tg = line.beats[0]
    assert tg.kind == "triplet"
    assert tg.span == Fraction(1, 2)
    assert tg.anchor == "2&"


# ---------------------------------------------------------------------------
# Compiler — slot positions, subdivision, bar annotation
# ---------------------------------------------------------------------------

def _compile_first_bar(src: str):
    song = parse(src)
    ir = compile_song(song)
    return ir.bars[0]


def test_compile_sextuplet_slot_positions_fall_evenly():
    src = """\
groove "g":
    HH: 2{sextuplet 1, 2, 3, 4, 5, 6}
section "s":
    bars: 1
    groove: "g"
"""
    bar = _compile_first_bar(src)
    hh_positions = sorted(e.beat_position for e in bar.events if e.instrument == "HH")
    expected = [
        Fraction(1, 4) + Fraction(k, 6) * Fraction(1, 4) for k in range(6)
    ]
    assert hh_positions == expected


def test_compile_sets_full_beat_tuplet_annotation():
    src = """\
groove "g":
    HH: 2{sextuplet 1, 2, 3, 4, 5, 6}
section "s":
    bars: 1
    groove: "g"
"""
    bar = _compile_first_bar(src)
    assert bar.beat_tuplets == [None, ("full", 6, 4), None, None]


def test_compile_sets_halves_annotation_for_half_beat_tuplets():
    src = """\
groove "g":
    HH: 1, 2, 3{triplet/8 1, 2, 3}, 3&{triplet/8 1, 2, 3}, 4
section "s":
    bars: 1
    groove: "g"
"""
    bar = _compile_first_bar(src)
    # Beat 3 (index 2) splits into two triplet halves.
    assert bar.beat_tuplets[2] == ("halves", (3, 2), (3, 2))


def test_compile_lcm_subdivision_includes_tuplet_kinds():
    src = """\
groove "g":
    HH: 1{sextuplet 1, 2, 3, 4, 5, 6}, 2, 3, 4
section "s":
    bars: 1
    groove: "g"
"""
    bar = _compile_first_bar(src)
    # LCM(2, 6) per beat * 4 beats = 24.
    assert bar.subdivision == 24


def test_compile_rejects_two_tuplet_kinds_on_same_beat():
    src = """\
groove "g":
    HH: 2{sextuplet 1, 2, 3, 4, 5, 6}
    SN: 2{quintuplet 1, 3}
section "s":
    bars: 1
    groove: "g"
"""
    with pytest.raises(GrooveScriptError):
        compile_song(parse(src))


# ---------------------------------------------------------------------------
# *<kind>[/N] star shorthand
# ---------------------------------------------------------------------------

def test_star_sextuplet_fills_every_beat():
    src = """\
groove "g":
    HH: *sextuplet
section "s":
    bars: 1
    groove: "g"
"""
    bar = _compile_first_bar(src)
    assert bar.beat_tuplets == [
        ("full", 6, 4),
        ("full", 6, 4),
        ("full", 6, 4),
        ("full", 6, 4),
    ]
    # 4 beats × 6 slots = 24 events.
    assert sum(1 for e in bar.events if e.instrument == "HH") == 24


def test_star_named_tuplet_with_half_beat_qualifier():
    src = """\
groove "g":
    HH: *triplet/8
section "s":
    bars: 1
    groove: "g"
"""
    bar = _compile_first_bar(src)
    # Each beat is split into two half-beat triplets → "halves" annotation.
    assert bar.beat_tuplets == [
        ("halves", (3, 2), (3, 2)),
        ("halves", (3, 2), (3, 2)),
        ("halves", (3, 2), (3, 2)),
        ("halves", (3, 2), (3, 2)),
    ]


# ---------------------------------------------------------------------------
# LilyPond emission
# ---------------------------------------------------------------------------

def test_lilypond_wraps_sextuplet_in_tuplet_block():
    src = """\
groove "g":
    HH: 2{sextuplet 1, 2, 3, 4, 5, 6}
section "s":
    bars: 1
    groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\tuplet 6/4 {" in ly


def test_lilypond_uses_per_kind_ratios():
    """Each named tuplet emits its own LilyPond ratio."""
    cases = [
        ("triplet 1, 2, 3", "\\tuplet 3/2 {"),
        ("quintuplet 1, 2, 3, 4, 5", "\\tuplet 5/4 {"),
        ("sextuplet 1, 2, 3, 4, 5, 6", "\\tuplet 6/4 {"),
        ("septuplet 1, 2, 3, 4, 5, 6, 7", "\\tuplet 7/4 {"),
        ("nonuplet 1, 2, 3, 4, 5, 6, 7, 8, 9", "\\tuplet 9/8 {"),
    ]
    for body, marker in cases:
        src = f"""\
groove "g":
    HH: 2{{{body}}}
section "s":
    bars: 1
    groove: "g"
"""
        ly = emit_lilypond(compile_song(parse(src)))
        assert marker in ly, f"missing {marker} for body {body!r}"


def test_lilypond_emits_two_triplet_brackets_for_half_beat():
    src = """\
groove "g":
    HH: 3{triplet/8 1, 2, 3}, 3&{triplet/8 1, 2, 3}
section "s":
    bars: 1
    groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    # Two independent triplet wrappers, not one sextuplet.
    assert ly.count("\\tuplet 3/2 {") >= 2


# ---------------------------------------------------------------------------
# MusicXML emission
# ---------------------------------------------------------------------------

def test_musicxml_emits_time_modification_for_sextuplet():
    src = """\
groove "g":
    HH: 2{sextuplet 1, 2, 3, 4, 5, 6}
section "s":
    bars: 1
    groove: "g"
"""
    xml = emit_musicxml(compile_song(parse(src))).decode("utf-8")
    assert "<actual-notes>6</actual-notes>" in xml
    assert "<normal-notes>4</normal-notes>" in xml


def test_musicxml_keeps_quintuplet_distinct_from_triplet():
    src = """\
groove "g":
    HH: 1{quintuplet 1, 2, 3, 4, 5}
section "s":
    bars: 1
    groove: "g"
"""
    xml = emit_musicxml(compile_song(parse(src))).decode("utf-8")
    assert "<actual-notes>5</actual-notes>" in xml
    assert "<normal-notes>4</normal-notes>" in xml


# ---------------------------------------------------------------------------
# Count-form fills
# ---------------------------------------------------------------------------

def test_count_form_fill_with_sextuplet_group():
    src = """\
groove "basic":
    HH: 1, 2, 3, 4
fill "tom run":
    count: "1 2{sextuplet 1, 2, 3, 4, 5, 6} 3 4"
    notes: "BD HT MT FT BD HT MT BD SN"
section "s":
    bars: 1
    groove: "basic"
    fill "tom run" at bar 1
"""
    ir = compile_song(parse(src))
    bar = ir.bars[0]
    # The fill replaces the bar from beat 1 onward, so beat 2 is sextuplet.
    assert bar.beat_tuplets[1] == ("full", 6, 4)
    # 6 sextuplet hits + 1 (BD) + 1 (BD) + 1 (SN) = 9 events from the fill.
    inst_at_beat2_first = [
        e for e in bar.events if e.beat_position == Fraction(1, 4)
    ]
    # Slot 1 of the sextuplet on beat 2 = HT (per the notes string above).
    assert any(e.instrument == "HT" for e in inst_at_beat2_first)


def test_count_form_fill_anchor_must_be_specified():
    """A bare ``{sextuplet …}`` at the start of a count string is an error."""
    src = """\
fill "x":
    count: "{sextuplet 1, 2, 3, 4, 5, 6} 3 4"
    notes: "BD BD BD BD BD BD BD BD"
section "s":
    bars: 1
    groove: placeholder
    fill "x" at bar 1
"""
    with pytest.raises((GrooveScriptError, ValueError)):
        parse(src)


# ---------------------------------------------------------------------------
# Regression: legacy triplet path still works alongside new groups
# ---------------------------------------------------------------------------

def test_legacy_triplet_suffix_still_renders_as_triplet():
    """Regression: pre-tuplet-group code path (1t/1l labels) untouched."""
    src = """\
groove "g":
    HH: 1, 1t, 1l, 2, 3, 4
section "s":
    bars: 1
    groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\tuplet 3/2 {" in ly


def test_showcase_fixture_compiles_cleanly():
    """The committed showcase fixture must continue to round-trip."""
    from pathlib import Path

    fixture = (
        Path(__file__).parent / "fixtures" / "tuplets_showcase.gs"
    )
    text = fixture.read_text()
    song = parse(text)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\tuplet 6/4 {" in ly       # sextuplet beats
    assert "\\tuplet 5/4 {" in ly       # quintuplet beats
    assert "\\tuplet 7/4 {" in ly       # septuplet beats
    assert "\\tuplet 9/8 {" in ly       # nonuplet beats
    # MusicXML round-trip parses without errors.
    assert emit_musicxml(ir)


# ---------------------------------------------------------------------------
# Regression tests for bugs found in the post-merge review
# ---------------------------------------------------------------------------

def test_tuplet_in_play_block_propagates_to_emitter():
    """Regression: ``play:`` blocks used to drop tuplet annotations,
    causing sextuplet bars to render as triplets in LilyPond/MusicXML."""
    src = """\
groove "sext":
    HH: 1, 2{sextuplet 1, 2, 3, 4, 5, 6}, 3, 4
    BD: 1, 3
section "play":
    play:
        groove "sext" x2
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\tuplet 6/4 {" in ly, "play-block tuplet not rendered"
    assert "\\tuplet 3/2 {" not in ly, (
        "play-block tuplet collapsed into triplet path (the original bug)"
    )


def test_tuplet_in_inline_play_bar_propagates():
    """Regression: inline ``bar "X":`` inside ``play:`` lost tuplet info too."""
    src = """\
section "s":
    play:
        bar "A":
            HH: 1, 2{sextuplet 1, 2, 3, 4, 5, 6}, 3, 4
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\tuplet 6/4 {" in ly


def test_tuplet_in_6_8_uses_correct_slot_durations_in_lilypond():
    """Regression: 6/8 (beat_unit=8) tuplets used to emit quarter-based slot
    durations, producing a bar whose engraved length disagreed with the
    time signature."""
    src = """\
title: "x"
time_signature: 6/8
groove "g":
    HH: 1{quintuplet 1, 2, 3, 4, 5}, 2, 3, 4, 5, 6
section "s":
    bars: 1
    groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    # In 6/8 the beat is an 8th note, so 5:4 quintuplet slots are 32nds
    # (5 in the time of 4 32nds = an 8th).
    assert "\\tuplet 5/4 { hh32 hh32 hh32 hh32 hh32 }" in ly
    assert "hh8" in ly  # remaining beats render as 8th-note quarters
    assert "hh4" not in ly  # no quarter-note leakage


def test_tuplet_in_6_8_uses_correct_slot_divs_in_musicxml():
    """Regression: same bug for MusicXML — divisions per slot must shrink
    when beat_unit shifts from 4 to 8."""
    src = """\
time_signature: 6/8
groove "g":
    HH: 1{quintuplet 1, 2, 3, 4, 5}, 2, 3, 4, 5, 6
section "s":
    bars: 1
    groove: "g"
"""
    xml = emit_musicxml(compile_song(parse(src))).decode("utf-8")
    # 1260 = 8th note (= 1 beat in 6/8); 252 = 1260/5 = quintuplet slot.
    assert "<duration>252</duration>" in xml
    # The 8th-note remainder beats should appear as <type>eighth</type>.
    assert "<type>eighth</type>" in xml
    # Tuplet bracket markers are emitted alongside the time-modification.
    assert 'type="start"' in xml and "<tuplet" in xml
    assert 'type="stop"' in xml


def test_off_tuplet_hit_on_tuplet_beat_is_rejected():
    """Regression: silent data loss — a 16th-note hit on a beat that has
    a sextuplet annotation used to disappear from LilyPond/MusicXML
    because the emitters only enumerate slot positions."""
    src = """\
groove "g":
    HH: 2{sextuplet 1, 2, 3, 4, 5, 6}
    SN: 2, 2e, 2&, 2a
section "s":
    bars: 1
    groove: "g"
"""
    with pytest.raises(GrooveScriptError, match="not on one of its slot positions"):
        compile_song(parse(src))


def test_off_tuplet_extend_add_is_rejected():
    """Regression: ``add SN at 2e`` over a sextuplet beat used to silently
    drop the SN hit because position 5/16 is not on the sextuplet grid."""
    src = """\
groove "base":
    HH: 2{sextuplet 1, 2, 3, 4, 5, 6}
groove "ext":
    extend: "base"
    add SN at 2e
section "s":
    bars: 1
    groove: "ext"
"""
    with pytest.raises(GrooveScriptError, match="not on one of its slot positions"):
        compile_song(parse(src))


def test_variation_with_tuplet_target_rejected_cleanly():
    """Regression: ``add CR at 2{sextuplet 1, 2}`` used to crash with
    ``AttributeError: 'TupletGroup' object has no attribute 'startswith'``
    instead of producing a clean diagnostic."""
    src = """\
groove "g":
    HH: 1, 2, 3, 4
section "s":
    bars: 1
    groove: "g"
    variation at bar 1:
        add CR at 2{sextuplet 1, 2}
"""
    with pytest.raises(GrooveScriptError, match="cannot target a tuplet group"):
        compile_song(parse(src))


def test_modify_add_with_tuplet_target_rejected_cleanly():
    src = """\
groove "g":
    HH: 2{sextuplet 1, 2, 3, 4, 5, 6}
section "s":
    bars: 1
    groove: "g"
    variation at bar 1:
        modify add accent to HH at 2{sextuplet 1}
"""
    with pytest.raises(GrooveScriptError, match="cannot target a tuplet group"):
        compile_song(parse(src))


def test_buzz_inside_tuplet_slot_rejected():
    """Regression: ``SN: 2{sextuplet 1 buzz, …}`` used to silently
    downgrade buzz to a plain hit because the tuplet emitter has no
    tremolo path."""
    src = """\
groove "g":
    SN: 2{sextuplet 1 buzz:16, 4 buzz:16}
section "s":
    bars: 1
    groove: "g"
"""
    with pytest.raises(GrooveScriptError, match="'buzz' modifier is not allowed inside a tuplet group"):
        compile_song(parse(src))


def test_fill_placed_mid_tuplet_beat_rejected():
    """Regression: a fill placed at e.g. ``beat 3a`` over a groove with a
    sextuplet on beat 3 used to corrupt the merged annotation, which
    then routed the bar through the legacy triplet emitter and dropped
    most of the sextuplet hits."""
    src = """\
groove "g":
    HH: 1, 2, 3{sextuplet 1, 2, 3, 4, 5, 6}, 4
fill "f":
    count: "3a 4"
    notes: "(BD CR) SN"
section "s":
    bars: 1
    groove: "g"
    fill "f" at bar 1 beat 3a
"""
    with pytest.raises(GrooveScriptError, match="falls inside a tuplet"):
        compile_song(parse(src))


def test_half_beat_tuplet_right_half_with_16th_renders_two_16ths():
    """Regression: the non-tuplet half of a half-beat tuplet split used
    to emit a single 8th-note slot, dropping any 16th-grid hit in the
    other 16th of the half. With the fix, the half emits two 16ths
    when there's a hit at the half's 16th-mid."""
    src = """\
groove "g":
    HH: 1, 2, 3{triplet/8 1, 2, 3}, 3a, 4
section "s":
    bars: 1
    groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    # Left half = the triplet, right half = two 16ths (the 3& position
    # and the 3a position, with a rest on 3&).
    assert "\\tuplet 3/2 { hh16 hh16 hh16 } r16 hh16" in ly


def test_count_form_half_beat_error_points_to_pattern_line_form():
    """Regression: the count-form half-beat-tuplet error message used to
    just say ``anchor sub-beats explicitly instead`` without telling
    the user what the alternative looks like."""
    src = """\
groove "g":
    HH: *4
fill "f":
    count: "1 2{triplet/8 1, 2, 3} 3 4"
    notes: "BD BD BD BD BD BD BD"
section "s":
    bars: 1
    groove: "g"
    fill "f" at bar 1
"""
    with pytest.raises(GrooveScriptError, match=r"pattern line"):
        compile_song(parse(src))
