from pathlib import Path

import pytest

from groovescript.ast_nodes import Fill, FillPlaceholder, FillPlacement, InstrumentHit, StarSpec
from groovescript.compiler import compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_fixture_fill_star_syntax():
    """End-to-end: fill_star_syntax.gs exercises `*N` and `*N except …` on
    instrument pattern lines inside count-block fill bodies."""
    song = parse_file(str(FIXTURES / "fill_star_syntax.gs"))
    assert song.metadata.title == "Fill Star Syntax"
    # Fill "floor tom eighths" uses `*8 except 4 and` on FT pattern line.
    floor_tom = next(f for f in song.fills if f.name == "floor tom eighths")
    ft_line = floor_tom.bars[0].pattern_lines[0]
    assert ft_line.instrument == "FT"
    assert isinstance(ft_line.beats, StarSpec)
    assert ft_line.beats.note_value == 8
    assert "4&" in ft_line.beats.except_beats
    # Fill "hi-hat sixteenths" uses plain `*16`.
    hh_fill = next(f for f in song.fills if f.name == "hi-hat sixteenths")
    hh_line = hh_fill.bars[0].pattern_lines[0]
    assert isinstance(hh_line.beats, StarSpec)
    assert hh_line.beats.note_value == 16
    # Whole song compiles and emits.
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "drummode" in ly


def test_parse_file_fixture_multi_bar_fill():
    """End-to-end: multi_bar_fill.gs places a two-bar fill (two `count` blocks)
    at bar 7 beat 3, so bar 7 is partially overlaid and bar 8 is fully replaced."""
    song = parse_file(str(FIXTURES / "multi_bar_fill.gs"))
    assert song.metadata.title == "Multi-Bar Fill Test"
    two_bar = next(f for f in song.fills if f.name == "two-bar fill")
    assert len(two_bar.bars) == 2
    ir = compile_song(song)
    # Section has 8 bars; fill starts at bar 7 beat 3, spans into bar 8.
    assert len(ir.bars) == 8
    # Bar 8 (index 7) is fully replaced — no HH groove events remain.
    bar8 = ir.bars[7]
    assert "HH" not in {e.instrument for e in bar8.events}
    # LilyPond emits without error.
    ly = emit_lilypond(ir)
    assert "drummode" in ly

FILL_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "bar 4 fill":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "bar 4 fill" at bar 4
"""

FILL_WITH_BEAT_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "half bar fill":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "half bar fill" at bar 4 beat 3
"""


def test_parse_fill_definition():
    song = parse(FILL_SRC)
    assert len(song.fills) == 1
    assert isinstance(song.fills[0], Fill)
    assert song.fills[0].name == "bar 4 fill"


def test_parse_fill_bars():
    song = parse(FILL_SRC)
    fill = song.fills[0]
    assert len(fill.bars) == 1
    assert fill.bars[0].label == "3 e & a 4"


def test_parse_fill_lines():
    song = parse(FILL_SRC)
    lines = song.fills[0].bars[0].lines
    assert len(lines) == 5
    assert lines[0].beat == "3"
    assert lines[0].instruments == ["SN"]
    assert lines[4].beat == "4"
    assert lines[4].instruments == ["BD", "CR"]


def test_parse_fill_placement_whole_bar():
    song = parse(FILL_SRC)
    section = song.sections[0]
    assert len(section.fills) == 1
    fp = section.fills[0]
    assert isinstance(fp, FillPlacement)
    assert fp.fill_name == "bar 4 fill"
    assert fp.bar == 4
    assert fp.beat is None


def test_parse_fill_placement_with_beat():
    song = parse(FILL_WITH_BEAT_SRC)
    fp = song.sections[0].fills[0]
    assert fp.fill_name == "half bar fill"
    assert fp.bar == 4
    assert fp.beat == "3"


def test_parse_multi_bar_fill():
    src = """\
groove "beat":
    HH: *8

fill "two bar fill":
  count "bar 3 tail":
    3: SN
    4: CR
  count "bar 4 full":
    1: SN
    2: SN
    3: SN
    4: BD

section "verse":
  bars: 4
  groove: "beat"
  fill "two bar fill" at bar 3
"""
    song = parse(src)
    fill = song.fills[0]
    assert len(fill.bars) == 2
    assert fill.bars[0].label == "bar 3 tail"
    assert fill.bars[1].label == "bar 4 full"
    assert len(fill.bars[1].lines) == 4


def test_parse_file_fixture_fills_basic():
    song = parse_file(str(FIXTURES / "fills_basic.gs"))
    assert song.metadata.title == "Basic Fills"
    assert song.metadata.tempo == 120
    assert len(song.grooves) == 2
    assert len(song.fills) == 1
    assert song.fills[0].name == "bar 4 fill"
    assert len(song.sections) == 2
    assert song.sections[0].name == "intro"
    assert len(song.sections[0].fills) == 1
    assert song.sections[0].fills[0].fill_name == "bar 4 fill"
    assert song.sections[0].fills[0].bar == 4
    assert song.sections[0].fills[0].beat == "3"


COUNT_NOTES_FILL_SRC = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "snare run":
  count: "3 e & a 4"
  notes: "snare snare snare snare (bass, crash)"

section "intro":
  bars: 4
  groove: "beat"
  fill "snare run" at bar 4 beat 3
"""


def test_parse_cn_fill_structure():
    """A count+notes fill produces one bar with the right label, beats, and instruments."""
    song = parse(COUNT_NOTES_FILL_SRC)
    assert len(song.fills) == 1
    fill = song.fills[0]
    assert fill.name == "snare run"
    assert len(fill.bars) == 1
    bar = fill.bars[0]
    assert bar.label == "3 e & a 4"
    assert [l.beat for l in bar.lines] == ["3", "3e", "3&", "3a", "4"]
    # "snare" → SN on the first four hits
    assert bar.lines[0].instruments == ["SN"]
    assert bar.lines[1].instruments == ["SN"]
    # "(bass, crash)" → [BD, CR]
    assert set(bar.lines[4].instruments) == {"BD", "CR"}


def test_parse_cn_fill_canonical_abbreviations():
    """Canonical abbreviations are accepted in the notes string."""
    src = """\
groove "beat":
    HH: *8

fill "kick crash":
  count: "4"
  notes: "(BD, CR)"

section "verse":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    lines = song.fills[0].bars[0].lines
    assert lines[0].beat == "4"
    assert set(lines[0].instruments) == {"BD", "CR"}


def test_parse_cn_fill_multi_bar():
    src = """\
groove "beat":
    HH: *8

fill "two bar fill":
  count: "3 e & a 4"
  notes: "SN SN SN SN (BD, CR)"
  count: "1 & 2 & 3 & 4"
  notes: "HH HH HH HH HH HH SN"

section "verse":
  bars: 4
  groove: "beat"
  fill "two bar fill" at bar 3
"""
    song = parse(src)
    fill = song.fills[0]
    assert len(fill.bars) == 2
    assert fill.bars[0].label == "3 e & a 4"
    assert fill.bars[1].label == "1 & 2 & 3 & 4"
    assert len(fill.bars[0].lines) == 5
    assert len(fill.bars[1].lines) == 7


def test_parse_cn_fill_triplet_count():
    src = """\
groove "beat":
    HH: *8

fill "triplet fill":
  count: "3 trip let 4"
  notes: "SN SN SN BD"

section "verse":
  bars: 4
  groove: "beat"
  fill "triplet fill" at bar 4 beat 3
"""
    song = parse(src)
    beats = [l.beat for l in song.fills[0].bars[0].lines]
    assert beats == ["3", "3t", "3l", "4"]


def test_parse_cn_fill_traditional_and_cn_in_same_song():
    """Both fill syntaxes can coexist in the same .gs file."""
    src = """\
groove "beat":
    HH: *8

fill "classic":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

fill "cn style":
  count: "3 e & a 4"
  notes: "SN SN SN SN (BD, CR)"

section "verse":
  bars: 4
  groove: "beat"
"""
    song = parse(src)
    assert len(song.fills) == 2
    assert song.fills[0].name == "classic"
    assert song.fills[1].name == "cn style"
    # Both should produce identical FillBar content
    classic_beats = [l.beat for l in song.fills[0].bars[0].lines]
    cn_beats = [l.beat for l in song.fills[1].bars[0].lines]
    assert classic_beats == cn_beats


def test_parse_file_fixture_count_notes_fills():
    song = parse_file(str(FIXTURES / "count_notes_fills.gs"))
    assert song.metadata.title == "Count and Notes Fills"
    fill = next(f for f in song.fills if f.name == "snare run")
    beats = [l.beat for l in fill.bars[0].lines]
    assert beats == ["3", "3e", "3&", "3a", "4"]
    assert fill.bars[0].lines[0].instruments == ["SN"]
    assert set(fill.bars[0].lines[4].instruments) == {"BD", "CR"}


def test_verbose_aliases_in_fill_position_notation():
    """Verbose names are accepted in fill position→instruments notation."""
    src = """\
groove "beat":
    HH: *8

fill "alias fill":
  count "4":
    4: kick, crash

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    instruments = {i for i in song.fills[0].bars[0].lines[0].instruments}
    assert instruments == {"BD", "CR"}


def test_verbose_aliases_in_fill_instrument_notation():
    """Verbose names are accepted in fill instrument→positions notation."""
    src = """\
groove "beat":
    HH: *8

fill "alias fill":
  count "3 4":
    snare: 3, 4

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    lines = song.fills[0].bars[0].lines
    assert all(l.instruments[0] == "SN" for l in lines)


PLACEHOLDER_SRC = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 4
  groove: "beat"
  fill placeholder at bar 4
  fill placeholder "build" at bar 2 beat 3
"""


def test_parse_fill_placeholder_anonymous():
    song = parse(PLACEHOLDER_SRC)
    section = song.sections[0]
    ph = section.fill_placeholders[0]
    assert isinstance(ph, FillPlaceholder)
    assert ph.label == "fill"
    assert ph.bar == 4
    assert ph.beat is None


def test_parse_fill_placeholder_custom_label():
    song = parse(PLACEHOLDER_SRC)
    section = song.sections[0]
    ph = section.fill_placeholders[1]
    assert ph.label == "build"
    assert ph.bar == 2
    assert ph.beat == "3"


def test_parse_fill_placeholder_count():
    song = parse(PLACEHOLDER_SRC)
    section = song.sections[0]
    assert len(section.fill_placeholders) == 2


def test_parse_fill_placeholder_without_beat():
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 2
  groove: "beat"
  fill placeholder at bar 1
"""
    song = parse(src)
    ph = song.sections[0].fill_placeholders[0]
    assert ph.label == "fill"
    assert ph.bar == 1
    assert ph.beat is None


def test_parse_fill_placeholder_with_beat_no_label():
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 2
  groove: "beat"
  fill placeholder at bar 1 beat 3
"""
    song = parse(src)
    ph = song.sections[0].fill_placeholders[0]
    assert ph.label == "fill"
    assert ph.bar == 1
    assert ph.beat == "3"


def test_parse_fill_placeholder_section_still_has_no_fills():
    song = parse(PLACEHOLDER_SRC)
    section = song.sections[0]
    assert section.fills == []


def test_parse_file_fixture_placeholder_fills():
    song = parse_file(str(FIXTURES / "placeholder_fills.gs"))
    # Verse has one placeholder
    assert len(song.sections[0].fill_placeholders) == 1
    # Chorus has two placeholders
    assert len(song.sections[1].fill_placeholders) == 2
    assert song.sections[1].fill_placeholders[0].label == "build"
    assert song.sections[1].fill_placeholders[1].label == "crash out"


# ── "and" alias for "&" in counts ──────────────────────────────────────────

def test_parse_and_alias_in_groove_beat_label():
    src = """\
groove "beat":
    HH: 1, 1and, 2, 2and, 3, 3and, 4, 4and
"""
    song = parse(src)
    beats = list(song.grooves[0].pattern[0].beats)
    assert beats == ["1", "1&", "2", "2&", "3", "3&", "4", "4&"]


def test_parse_and_alias_in_count_notes_count_string():
    src = """\
groove "beat":
    HH: *8

fill "eighths":
  count: "1 and 2 and 3 and 4 and"
  notes: "HH HH HH HH HH HH HH HH"

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    beats = [l.beat for l in song.fills[0].bars[0].lines]
    assert beats == ["1", "1&", "2", "2&", "3", "3&", "4", "4&"]


def test_parse_and_alias_in_classic_fill_count_block():
    src = """\
groove "beat":
    HH: *8

fill "f":
  count "1 and 2 and":
    1: SN
    1and: SN
    2: SN
    2and: SN

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    beats = [l.beat for l in song.fills[0].bars[0].lines]
    assert beats == ["1", "1&", "2", "2&"]


def test_parse_and_alias_in_section_fill_at_beat():
    src = """\
groove "beat":
    HH: *8

fill "f":
  count "2 and":
    2: SN
    2and: SN

section "v":
  bars: 2
  groove: "beat"
  fill "f" at bar 2 beat 2and
"""
    song = parse(src)
    fp = song.sections[0].fills[0]
    assert fp.beat == "2&"


# ── Comma-delimited hits in notes notation ─────────────────────────────────

def test_parse_cn_fill_comma_delimited_simple():
    src = """\
groove "beat":
    HH: *8

fill "f":
  count: "1 2 3 4"
  notes: "SN, SN, SN, BD"

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    lines = song.fills[0].bars[0].lines
    assert [l.instruments[0] for l in lines] == ["SN", "SN", "SN", "BD"]


def test_parse_cn_fill_comma_delimited_with_modifiers():
    src = """\
groove "beat":
    HH: *8

fill "f":
  count: "1 2 3 4"
  notes: "SN accent, SN ghost, SN flam, BD drag"

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    lines = song.fills[0].bars[0].lines
    assert lines[0].instruments[0].modifiers == ["accent"]
    assert lines[1].instruments[0].modifiers == ["ghost"]
    assert lines[2].instruments[0].modifiers == ["flam"]
    assert lines[3].instruments[0].modifiers == ["drag"]


def test_parse_cn_fill_comma_delimited_with_group_and_modifier():
    src = """\
groove "beat":
    HH: *8

fill "f":
  count: "1 2 3 4"
  notes: "SN, SN, SN, (BD, CR) accent"

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    lines = song.fills[0].bars[0].lines
    # Last group is simultaneous BD+CR, both carrying an accent
    assert set(lines[3].instruments) == {"BD", "CR"}
    for hit in lines[3].instruments:
        assert "accent" in hit.modifiers


def test_parse_cn_fill_legacy_space_delimited_still_works():
    """No top-level commas → old space-delimited parser is used."""
    src = """\
groove "beat":
    HH: *8

fill "f":
  count: "1 2 3 4"
  notes: "SN SN SN (BD, CR)"

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    lines = song.fills[0].bars[0].lines
    assert lines[0].instruments == ["SN"]
    assert set(lines[3].instruments) == {"BD", "CR"}


# ── Inline non-named fills ─────────────────────────────────────────────────

INLINE_FILL_SRC = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 4
  groove: "beat"
  fill at bar 4 beat 3:
    count "3 e & a 4":
      3: SN
      3e: SN
      3&: SN
      3a: SN
      4: BD, CR
"""


def test_parse_inline_fill_creates_inline_fill_entry():
    song = parse(INLINE_FILL_SRC)
    section = song.sections[0]
    assert len(section.inline_fills) == 1
    fill = section.inline_fills[0]
    assert fill.name.startswith("__inline_fill_")
    assert len(fill.bars) == 1
    assert len(fill.bars[0].lines) == 5


def test_parse_inline_fill_emits_placement_referencing_synthetic_name():
    song = parse(INLINE_FILL_SRC)
    section = song.sections[0]
    assert len(section.fills) == 1
    placement = section.fills[0]
    assert placement.bar == 4
    assert placement.beat == "3"
    assert placement.fill_name == section.inline_fills[0].name


def test_parse_inline_fill_whole_bar_no_beat():
    src = """\
groove "beat":
    HH: *8

section "v":
  bars: 2
  groove: "beat"
  fill at bar 2:
    count "1 2 3 4":
      1: SN
      2: SN
      3: SN
      4: BD, CR
"""
    song = parse(src)
    placement = song.sections[0].fills[0]
    assert placement.bar == 2
    assert placement.beat is None


def test_parse_inline_fill_count_notes_form():
    src = """\
groove "beat":
    HH: *8

section "v":
  bars: 2
  groove: "beat"
  fill at bar 2 beat 3:
    count: "3 e and a 4"
    notes: "SN, SN, SN, SN, (BD, CR)"
"""
    song = parse(src)
    section = song.sections[0]
    assert len(section.inline_fills) == 1
    beats = [l.beat for l in section.inline_fills[0].bars[0].lines]
    assert beats == ["3", "3e", "3&", "3a", "4"]


def test_parse_file_fixture_dsl_changes():
    """Consolidated DSL ergonomics showcase. Every feature from the DSL-changes
    backlog batches appears at least once; this test spot-checks the major
    ones and verifies the whole fixture compiles + emits."""
    from groovescript.compiler import compile_song
    from groovescript.lilypond import emit_lilypond

    song = parse_file(str(FIXTURES / "dsl_changes.gs"))
    assert song.metadata.title == "DSL Changes Showcase"

    # "and" shorthand + optional commas: HH beats include 1&, 2&, 3&, 4&.
    money_beat = next(g for g in song.grooves if g.name == "money beat")
    hh = next(p for p in money_beat.pattern if p.instrument == "HH")
    assert "1&" in hh.beats and "4&" in hh.beats

    # Unquoted count/notes groove body is preserved as count_notes tuple.
    sixteenth_run = next(g for g in song.grooves if g.name == "sixteenth run")
    assert sixteenth_run.count_notes is not None
    count_str, notes_str = sixteenth_run.count_notes
    assert "e" in count_str and "and" in count_str
    assert "SN" in notes_str

    # Comma-delimited notes with per-hit accent modifier.
    dynamic_run = next(f for f in song.fills if f.name == "dynamic run")
    first_hit = dynamic_run.bars[0].lines[0].instruments[0]
    assert first_hit.modifiers == ["accent"]

    # Whitespace-only simultaneous group `(BD CR)` in `notes:`.
    shot = next(f for f in song.fills if f.name == "shot")
    first_line_instrs = [i.instrument for i in shot.bars[0].lines[0].instruments]
    assert set(first_line_instrs) == {"BD", "CR"}

    # Intro has an anonymous variation.
    intro = next(s for s in song.sections if s.name == "intro")
    assert intro.variations[0].name is None

    # Verse has multi-instrument remove/add/replace variations.
    verse = next(s for s in song.sections if s.name == "verse")
    remove_action = verse.variations[0].actions[0]
    assert remove_action.action == "remove"
    # Multi-instrument action carries multiple instruments in one action.
    replace_var = verse.variations[2]
    assert replace_var.actions[0].action == "replace"

    # Chorus has an inline fill and a substitute variation.
    chorus = next(s for s in song.sections if s.name == "chorus")
    assert len(chorus.inline_fills) == 1
    assert chorus.fills[0].fill_name == chorus.inline_fills[0].name
    sub_var = next(v for v in chorus.variations if v.name == "shot")
    assert sub_var.actions[0].action == "substitute"

    # Bridge places a named fill at multiple bars via a bar list — this
    # expands into one FillPlacement per bar.
    bridge = next(s for s in song.sections if s.name == "bridge")
    build_placements = [p for p in bridge.fills if p.fill_name == "build"]
    assert sorted(p.bar for p in build_placements) == [4, 8]

    # Bridge has space-separated bar list on a `modify add` variation.
    flam_var = next(
        v for v in bridge.variations if v.actions[0].action == "modify_add"
    )
    assert set(flam_var.bars) == {2, 6}

    # Outro has an anonymous inline groove (unnamed, declared inside the section).
    outro = next(s for s in song.sections if s.name == "outro")
    assert len(outro.inline_grooves) == 1

    # Whole song compiles and renders.
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\drummode" in ly or "drummode" in ly


# ── Optional commas + bare-suffix expansion in beat lists ────────────────
#
# The comma-insertion and bare-suffix preprocessors share the same line
# rewriter (`_preprocess_commas` in parser.py), so we cover both features
# together with one parameterized test per code path: pattern-line
# RHS, variation-action RHS, and position-line negative path.

@pytest.mark.parametrize("rhs,expected", [
    # optional commas — simple beat list
    ("1 3",                                   ["1", "3"]),
    # optional commas — mixed comma + space on one line
    ("1, 2 3, 4",                             ["1", "2", "3", "4"]),
    # optional commas — full 16th positional grid
    ("1 1e 1& 1a 2 2e 2& 2a 3 3e 3& 3a 4 4e 4& 4a",
     ["1", "1e", "1&", "1a", "2", "2e", "2&", "2a",
      "3", "3e", "3&", "3a", "4", "4e", "4&", "4a"]),
    # optional commas — `and` long-form alias
    ("1 1and 2 2and 3 3and 4 4and",
     ["1", "1&", "2", "2&", "3", "3&", "4", "4&"]),
    # bare suffix — `and` shorthand
    ("1 and 2 and 3 and 4 and",
     ["1", "1&", "2", "2&", "3", "3&", "4", "4&"]),
    # bare suffix — `&` shorthand
    ("1 & 2 & 3 & 4 &",
     ["1", "1&", "2", "2&", "3", "3&", "4", "4&"]),
    # bare suffix — sixteenth suffixes (e, and, a)
    ("1 e and a 2 e and a 3 e and a 4 e and a",
     ["1", "1e", "1&", "1a", "2", "2e", "2&", "2a",
      "3", "3e", "3&", "3a", "4", "4e", "4&", "4a"]),
    # bare suffix — triplet suffixes (trip, let)
    ("1 trip let 2 trip let 3 trip let 4 trip let",
     ["1", "1t", "1l", "2", "2t", "2l",
      "3", "3t", "3l", "4", "4t", "4l"]),
    # bare + positional suffix mixed
    ("1 & 2 2& 3 and 4 4and",
     ["1", "1&", "2", "2&", "3", "3&", "4", "4&"]),
])
def test_parse_pattern_line_beat_list_variants(rhs, expected):
    """Comma-free and bare-suffix beat lists on a pattern line."""
    src = f"""\
groove "beat":
    HH: {rhs}
"""
    song = parse(src)
    assert list(song.grooves[0].pattern[0].beats) == expected


def test_parse_pattern_line_without_commas_preserves_modifiers():
    """Modifiers attach to the beat they follow even in comma-free form."""
    src = """\
groove "beat":
    BD: 1 flam 3 accent
    HH: *8
"""
    song = parse(src)
    bd = song.grooves[0].pattern[0]
    assert list(bd.beats) == ["1", "3"]
    assert bd.beats[0].modifiers == ["flam"]
    assert bd.beats[1].modifiers == ["accent"]


def test_parse_pattern_line_without_commas_star_rhs():
    """A star RHS without commas still produces a StarSpec."""
    src = """\
groove "beat":
    HH: *8
"""
    song = parse(src)
    assert song.grooves[0].pattern[0].beats == StarSpec(note_value=8)


def test_parse_groove_pos_line_without_commas():
    """Position→instrument lines also accept whitespace-separated items."""
    src = """\
groove "beat":
    1: BD HH
    2: SN HH
    3: BD HH
    4: SN HH
"""
    song = parse(src)
    g = song.grooves[0]
    instruments_at_1 = [l.instrument for l in g.pattern if l.beats == ["1"]]
    assert set(instruments_at_1) == {"BD", "HH"}


def test_parse_fill_line_without_commas():
    """Fill `count+notes` position lines accept whitespace-delimited instruments."""
    src = """\
groove "beat":
    HH: *8

fill "f":
  count "1 2 3 4":
    1: SN BD
    2: HH flam CR
    3: SN
    4: BD CR

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    lines = song.fills[0].bars[0].lines
    assert {str(i) for i in lines[0].instruments} == {"SN", "BD"}
    hh_hit = next(i for i in lines[1].instruments if str(i) == "HH")
    cr_hit = next(i for i in lines[1].instruments if str(i) == "CR")
    assert hh_hit.modifiers == ["flam"]
    assert cr_hit.modifiers == []
    assert {str(i) for i in lines[3].instruments} == {"BD", "CR"}


@pytest.mark.parametrize("action_line,expected_beats,extra_check", [
    # comma-free add with trailing modifier
    ("add SN ghost at 1 3",          ["1", "3"],       lambda a: a.modifiers == ["ghost"]),
    # comma-free remove
    ("remove BD at 2 4",             ["2", "4"],       lambda a: True),
    # comma-free replace with target instrument
    ("replace HH with CR at 1 3",    ["1", "3"],       lambda a: a.target_instrument == "CR"),
    # bare-suffix add
    ("add SN ghost at 2 and",        ["2", "2&"],      lambda a: a.modifiers == ["ghost"]),
    # bare-suffix replace
    ("replace HH with CR at 1 and 3 and",
                                     ["1", "1&", "3", "3&"],
                                     lambda a: a.target_instrument == "CR"),
])
def test_parse_variation_action_beat_list_variants(action_line, expected_beats, extra_check):
    """Comma-free and bare-suffix beat lists in variation actions."""
    src = f"""\
groove "beat":
    HH: *8

section "v":
  bars: 4
  groove: "beat"
  variation at bar 4:
    {action_line}
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.beats == expected_beats
    assert extra_check(action)


def test_parse_pos_line_ignores_bare_suffix_logic():
    """Position→instrument lines don't apply bare-suffix resolution."""
    # `1: BD HH` on a position line — "HH" is an instrument, not a suffix,
    # so this should parse as BD + HH at position 1.
    src = """\
groove "beat":
    1: BD HH
    2: SN HH
"""
    song = parse(src)
    # Verify position 1 has both BD and HH
    instruments_at_1 = sorted({l.instrument for l in song.grooves[0].pattern if l.beats == ["1"]})
    assert instruments_at_1 == ["BD", "HH"]


def test_preprocess_commas_leaves_strings_alone():
    from groovescript.parser import _preprocess_commas
    src = """\
title: "A song"
groove "money beat":
"""
    # Strings must not be mangled by the preprocessor.
    assert '"A song"' in _preprocess_commas(src)
    assert '"money beat"' in _preprocess_commas(src)


def test_preprocess_commas_leaves_single_token_rhs_alone():
    from groovescript.parser import _preprocess_commas
    src = """\
groove "beat":
    BD: *8
"""
    out = _preprocess_commas(src)
    # ``*8`` should be preserved verbatim by the preprocessor (no comma
    # insertion or other rewriting on a single-token RHS).
    assert "BD: *8" in out


# ── Unquoted count: / notes: values in fills ──────────────────────────────

def test_parse_unquoted_count_and_notes_in_fill():
    """`count:`/`notes:` accept bare values without surrounding quotes."""
    src = """\
fill "roll":
  count: 1 e and a
  notes: SN, SN, SN, SN

groove "beat":
    BD: 1, 3
    HH: *8

section "s":
  bars: 1
  groove: "beat"
  fill "roll" at bar 1
"""
    song = parse(src)
    assert len(song.fills) == 1
    bar = song.fills[0].bars[0]
    assert [line.beat for line in bar.lines] == ["1", "1e", "1&", "1a"]


def test_parse_quoted_count_and_notes_still_work():
    """Quoted `count:`/`notes:` values remain valid."""
    src = """\
fill "roll":
  count: "1 e and a"
  notes: "SN, SN, SN, SN"
"""
    song = parse(src)
    bar = song.fills[0].bars[0]
    assert len(bar.lines) == 4


def test_parse_unquoted_values_with_trailing_comment():
    """Trailing comments after an unquoted `count:`/`notes:` value are stripped."""
    src = """\
fill "roll":
  count: 1 e and a   # four 16ths
  notes: SN, SN, SN, SN   // legacy spaced form
"""
    song = parse(src)
    assert len(song.fills[0].bars[0].lines) == 4


def test_fill_count_without_notes_defaults_to_snare():
    """Regression: a count+notes fill bar with the ``notes:`` line omitted
    fills every count slot with a single snare hit. Snare-on-every-slot is
    the default starting point for a fill, so the user shouldn't have to
    repeat ``SN`` for each count token."""
    src = """\
fill "snare roll":
  count: "3 e and a 4 e and a"

groove "beat":
    HH: *8

section "v":
  bars: 1
  groove: "beat"
  fill "snare roll" at bar 1 beat 3
"""
    song = parse(src)
    bar = song.fills[0].bars[0]
    assert [line.beat for line in bar.lines] == [
        "3", "3e", "3&", "3a", "4", "4e", "4&", "4a"
    ]
    assert all(line.instruments == [InstrumentHit("SN")] for line in bar.lines)


def test_fill_count_without_notes_unquoted_form():
    """Regression: the unquoted-value form of ``count:`` also defaults to
    snare hits when ``notes:`` is omitted."""
    src = """\
fill "roll":
  count: 1 e and a

groove "beat":
    HH: *8

section "s":
  bars: 1
  groove: "beat"
  fill "roll" at bar 1
"""
    song = parse(src)
    bar = song.fills[0].bars[0]
    assert [line.beat for line in bar.lines] == ["1", "1e", "1&", "1a"]
    assert all(line.instruments == [InstrumentHit("SN")] for line in bar.lines)


def test_inline_fill_count_without_notes_defaults_to_snare():
    """Regression: an inline fill body using count+notes form with notes
    omitted defaults each slot to a snare hit, just like a top-level fill."""
    src = """\
groove "beat":
    HH: *8

section "v":
  bars: 4
  groove: "beat"
  fill at bar 4 beat 3:
    count: "3 e and a 4"
"""
    song = parse(src)
    bar = song.sections[0].inline_fills[0].bars[0]
    assert [line.beat for line in bar.lines] == ["3", "3e", "3&", "3a", "4"]
    assert all(line.instruments == [InstrumentHit("SN")] for line in bar.lines)


def test_multi_bar_fill_mixes_default_and_explicit_notes():
    """Regression: in a multi-bar count+notes fill, individual bars may omit
    ``notes:`` (defaulting to snare) while other bars supply explicit notes."""
    src = """\
fill "two bar build":
  count: "3 e and a 4 e and a"
  count: "1 e and a 2 e and a 3 e and a 4"
  notes: "SN, SN, SN, SN, SN, SN, SN, SN, SN, SN, SN, SN, (BD, CR)"

groove "beat":
    HH: *8

section "v":
  bars: 2
  groove: "beat"
  fill "two bar build" at bar 1
"""
    song = parse(src)
    bars = song.fills[0].bars
    assert len(bars) == 2
    assert all(line.instruments == [InstrumentHit("SN")] for line in bars[0].lines)
    assert bars[1].lines[-1].instruments == [InstrumentHit("BD"), InstrumentHit("CR")]


def test_parse_multiple_inline_fills_have_distinct_names():
    src = """\
groove "beat":
    HH: *8

section "a":
  bars: 4
  groove: "beat"
  fill at bar 2:
    count "1":
      1: SN
  fill at bar 4:
    count "1":
      1: BD, CR
"""
    song = parse(src)
    section = song.sections[0]
    assert len(section.inline_fills) == 2
    names = [f.name for f in section.inline_fills]
    assert len(set(names)) == 2


# ── Star syntax in fills ──────────────────────────────────────────────


def test_parse_fill_star_syntax():
    """Regression: fills should accept *N star syntax on instrument lines."""
    src = """\
groove "beat":
    HH: *8

fill "star fill":
  count "1 2 3 4":
    FT: *8

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    fill_bar = song.fills[0].bars[0]
    assert len(fill_bar.pattern_lines) == 1
    assert fill_bar.pattern_lines[0].instrument == "FT"
    assert isinstance(fill_bar.pattern_lines[0].beats, StarSpec)
    assert fill_bar.pattern_lines[0].beats.note_value == 8


def test_parse_fill_star_except_syntax():
    """Regression: fills should accept *N except beat_list syntax."""
    src = """\
groove "beat":
    HH: *8

fill "star except fill":
  count "1 2 3 4":
    FT: *8 except 4 and

section "v":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    fill_bar = song.fills[0].bars[0]
    assert len(fill_bar.pattern_lines) == 1
    star = fill_bar.pattern_lines[0].beats
    assert isinstance(star, StarSpec)
    assert star.note_value == 8
    assert star.except_beats == ("4", "4&")


# ── Multi-bar fill placements ─────────────────────────────────────────────
#
# Regression tests for backlog item "I'd like to be able to have the same
# fill in multiple bars." The grammar accepts a bar-number list after
# ``at bar`` / ``at bars`` for both named placements and inline fills,
# and the parser expands each bar into its own :class:`FillPlacement`.

def test_parse_named_fill_at_multiple_bars_comma():
    src = """\
groove "beat":
    HH: *8

fill "build":
  count "4":
    4: CR

section "s":
  bars: 8
  groove: "beat"
  fill "build" at bar 4, 8
"""
    song = parse(src)
    fills = song.sections[0].fills
    assert len(fills) == 2
    assert [fp.bar for fp in fills] == [4, 8]
    assert all(fp.fill_name == "build" for fp in fills)
    assert all(fp.beat is None for fp in fills)


def test_parse_named_fill_at_multiple_bars_plural_space_separated():
    """``fill "x" at bars 4 8`` parses the same as ``fill "x" at bar 4, 8``."""
    src = """\
groove "beat":
    HH: *8

fill "build":
  count "4":
    4: CR

section "s":
  bars: 8
  groove: "beat"
  fill "build" at bars 4 8
"""
    song = parse(src)
    fills = song.sections[0].fills
    assert [fp.bar for fp in fills] == [4, 8]


def test_parse_named_fill_at_multiple_bars_with_beat():
    """Backlog example: ``fill "x" at bar 4, 8 beat 3``."""
    src = """\
groove "beat":
    HH: *8

fill "tail":
  count "3 e and a 4":
    3: SN
    3e: SN
    3and: SN
    3a: SN
    4: BD, CR

section "s":
  bars: 8
  groove: "beat"
  fill "tail" at bar 4, 8 beat 3
"""
    song = parse(src)
    fills = song.sections[0].fills
    assert [fp.bar for fp in fills] == [4, 8]
    assert [fp.beat for fp in fills] == ["3", "3"]


def test_parse_inline_fill_at_multiple_bars_with_beat():
    """Inline fills also support multi-bar placement.

    Regression test for the exact error reported in the backlog:
    ``fill at bar 4, 8 beat 3:`` must parse.
    """
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 8
  groove: "beat"
  fill at bar 4, 8 beat 3:
    count "3 e and a 4":
      3: SN
      3e: SN
      3and: SN
      3a: SN
      4: BD, CR
"""
    song = parse(src)
    section = song.sections[0]
    fills = section.fills
    assert [fp.bar for fp in fills] == [4, 8]
    assert [fp.beat for fp in fills] == ["3", "3"]
    # A single inline fill definition is shared by both placements.
    assert len(section.inline_fills) == 1
    assert fills[0].fill_name == fills[1].fill_name == section.inline_fills[0].name
