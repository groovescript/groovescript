from pathlib import Path

import pytest

from groovescript.ast_nodes import Groove, Section, Song, StarSpec
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"

MONEY_BEAT_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8
"""

ARRANGEMENT_SRC = """\
metadata:
  title: "Simple Rock"
  tempo: 120
  time_signature: 4/4

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 2&, 4
      SN: 2, 4
      HH: *8

section "intro":
  bars: 4
  groove: "money beat"

section "verse":
  bars: 6
  groove: "two bar"
"""


def test_parse_returns_song():
    song = parse(MONEY_BEAT_SRC)
    assert isinstance(song, Song)


def test_parse_single_groove():
    song = parse(MONEY_BEAT_SRC)
    assert len(song.grooves) == 1
    assert isinstance(song.grooves[0], Groove)


def test_parse_groove_name():
    song = parse(MONEY_BEAT_SRC)
    groove = song.grooves[0]
    assert groove.name == "money beat"


def test_parse_single_bar_pattern_lines():
    song = parse(MONEY_BEAT_SRC)
    groove = song.grooves[0]
    assert len(groove.bars) == 1
    assert len(groove.pattern) == 3
    assert groove.pattern[0].instrument == "BD"
    assert groove.pattern[0].beats == ["1", "3"]
    assert groove.pattern[2].beats == StarSpec(note_value=8)


def test_parse_file_fixture():
    song = parse_file(str(FIXTURES / "money_beat.gs"))
    assert len(song.grooves) == 1
    assert song.grooves[0].name == "money beat"


def test_parse_metadata_block():
    song = parse(ARRANGEMENT_SRC)
    assert song.metadata.title == "Simple Rock"
    assert song.metadata.tempo == 120
    assert song.metadata.time_signature == "4/4"


def test_parse_multiple_grooves():
    song = parse(ARRANGEMENT_SRC)
    assert len(song.grooves) == 2
    assert song.grooves[1].name == "two bar"


def test_parse_multi_bar_groove():
    song = parse(ARRANGEMENT_SRC)
    groove = song.grooves[1]
    assert len(groove.bars) == 2
    assert groove.bars[1][0].beats == ["1", "2&", "4"]


def test_parse_sections():
    song = parse(ARRANGEMENT_SRC)
    assert len(song.sections) == 2
    assert isinstance(song.sections[0], Section)
    assert song.sections[0].name == "intro"
    assert song.sections[0].bars == 4
    assert song.sections[0].groove == "money beat"


def test_parse_file_fixture_basic_arrangement():
    song = parse_file(str(FIXTURES / "basic_arrangement.gs"))
    assert song.metadata.title == "Basic Arrangement"
    assert song.metadata.tempo == 116
    assert len(song.grooves) == 2
    assert song.grooves[0].name == "money beat"
    assert song.grooves[1].name == "two bar"
    assert len(song.grooves[1].bars) == 2
    assert len(song.sections) == 2
    assert song.sections[0].name == "intro"
    assert song.sections[0].bars == 4
    assert song.sections[1].name == "verse"
    assert song.sections[1].bars == 6
    assert song.sections[1].groove == "two bar"


def test_parse_top_level_metadata_lines():
    src = """\
title: "Top Level"
tempo: 98

groove "beat":
    HH: *8
"""
    song = parse(src)
    assert song.metadata.title == "Top Level"
    assert song.metadata.tempo == 98


def test_parse_dsl_version_metadata():
    from groovescript.parser import CURRENT_DSL_VERSION
    src = f"""\
title: "Versioned"
tempo: 120
dsl_version: {CURRENT_DSL_VERSION}

groove "beat":
    BD: 1
"""
    song = parse(src)
    assert song.metadata.dsl_version == CURRENT_DSL_VERSION


def test_parse_dsl_version_missing_defaults_to_none():
    """Files without a dsl_version line parse fine; field stays None."""
    src = """\
title: "No Version"

groove "beat":
    BD: 1
"""
    song = parse(src)
    assert song.metadata.dsl_version is None


def test_parse_dsl_version_mismatch_errors():
    """Declaring a dsl_version other than the current one must fail."""
    from groovescript.errors import GrooveScriptError
    from groovescript.parser import CURRENT_DSL_VERSION
    bad_version = CURRENT_DSL_VERSION + 42
    src = f"""\
title: "Future"
dsl_version: {bad_version}

groove "beat":
    BD: 1
"""
    with pytest.raises(GrooveScriptError) as excinfo:
        parse(src)
    assert "dsl_version" in str(excinfo.value)
    assert str(bad_version) in str(excinfo.value)


def test_parse_dsl_version_inside_metadata_block():
    """dsl_version: can live inside a metadata: block."""
    from groovescript.parser import CURRENT_DSL_VERSION
    src = f"""\
metadata:
  title: "Block Form"
  tempo: 100
  dsl_version: {CURRENT_DSL_VERSION}

groove "beat":
    BD: 1
"""
    song = parse(src)
    assert song.metadata.title == "Block Form"
    assert song.metadata.dsl_version == CURRENT_DSL_VERSION


BAR_TEXT_SRC = """\
groove "annotated":
    bar 1:
      text: "Verse feel"
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 2&, 4
      SN: 2, 4
      HH: *8

section "verse":
  bars: 4
  groove: "annotated"
"""


def test_parse_bar_text_stored_on_groove():
    song = parse(BAR_TEXT_SRC)
    groove = song.grooves[0]
    assert groove.bar_texts[1] == "Verse feel"
    assert 2 not in groove.bar_texts


EXTEND_TEXT_SRC = """\
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "main groove":
    extend: "rock"
    add BD at 3&
    text: "Quarter note pulse"
"""


def test_parse_extend_body_top_level_text_targets_bar_one():
    """Regression: a bare ``text:`` at the top of an ``extend:`` body annotates
    bar 1 of the resolved groove. Previously the parser rejected this entirely
    because ``extend_body_item`` only accepted variation actions."""
    song = parse(EXTEND_TEXT_SRC)
    groove = next(g for g in song.grooves if g.name == "main groove")
    assert groove.bar_texts == {1: "Quarter note pulse"}


def test_extend_body_duplicate_top_level_text_errors():
    """Two bare ``text:`` lines target the same bar 1 slot, so the parser
    must reject the duplicate rather than silently keeping one."""
    src = """\
groove "rock":
    BD: 1, 3

groove "main":
    extend: "rock"
    text: "first"
    text: "second"
"""
    with pytest.raises(Exception, match="text"):
        parse(src)


ALIAS_GROOVE_SRC = """\
groove "alias beat":
    kick: 1, 3
    snare: 2, 4
    hat: *8
"""


def test_alias_groove_kick_normalizes_to_bd():
    song = parse(ALIAS_GROOVE_SRC)
    instruments = {l.instrument for l in song.grooves[0].bars[0]}
    assert "BD" in instruments
    assert "kick" not in instruments


def test_alias_groove_snare_normalizes_to_sn():
    song = parse(ALIAS_GROOVE_SRC)
    instruments = {l.instrument for l in song.grooves[0].bars[0]}
    assert "SN" in instruments
    assert "snare" not in instruments


def test_alias_groove_hat_normalizes_to_hh():
    song = parse(ALIAS_GROOVE_SRC)
    instruments = {l.instrument for l in song.grooves[0].bars[0]}
    assert "HH" in instruments
    assert "hat" not in instruments


def test_lowercase_abbreviations_in_groove():
    """Lowercase abbreviations (sn, hh, bd) normalize to canonical forms."""
    src = """\
groove "lower":
    bd: 1, 3
    sn: 2, 4
    hh: *8
"""
    song = parse(src)
    instruments = {l.instrument for l in song.grooves[0].bars[0]}
    assert instruments == {"BD", "SN", "HH"}


@pytest.mark.parametrize("alias,canonical", [
    # verbose long-form aliases
    ("kick", "BD"), ("bass", "BD"),
    ("snare", "SN"),
    ("click", "SCS"), ("cross-stick", "SCS"),
    ("hat", "HH"), ("hihat", "HH"),
    ("open", "OH"), ("openhat", "OH"),
    ("ride", "RD"),
    ("crash", "CR"),
    ("floortom", "FT"), ("lowtom", "FT"),
    ("hightom", "HT"), ("hitom", "HT"),
    ("midtom", "MT"),
    # lowercase abbreviation aliases
    ("bd", "BD"), ("sn", "SN"), ("scs", "SCS"),
    ("hh", "HH"), ("oh", "OH"), ("rd", "RD"), ("cr", "CR"),
    ("ft", "FT"), ("ht", "HT"), ("mt", "MT"),
])
def test_instrument_alias_normalizes_to_canonical(alias, canonical):
    """Every verbose and lowercase alias resolves to its canonical abbreviation."""
    from groovescript.parser import _normalize_instrument
    assert _normalize_instrument(alias) == canonical


def test_parse_file_fixture_instrument_name_variations():
    song = parse_file(str(FIXTURES / "instrument_name_variations.gs"))
    assert song.metadata.title == "Instrument Name Variations"

    # kick→BD, snare→SN, hat→HH on the classic "alias groove".
    alias_groove = next(g for g in song.grooves if g.name == "alias groove")
    assert {l.instrument for l in alias_groove.bars[0]} == {"BD", "SN", "HH"}

    # cross-stick→SCS on "cross-stick groove".
    cs_groove = next(g for g in song.grooves if g.name == "cross-stick groove")
    assert "SCS" in {l.instrument for l in cs_groove.bars[0]}

    # click→SCS on "click groove".
    click_groove = next(g for g in song.grooves if g.name == "click groove")
    assert "SCS" in {l.instrument for l in click_groove.bars[0]}

    # lowtom→FT on "floor tom groove".
    ft_groove = next(g for g in song.grooves if g.name == "floor tom groove")
    assert "FT" in {l.instrument for l in ft_groove.bars[0]}

    # Fill uses snare/kick/crash verbose forms.
    fill = next(f for f in song.fills if f.name == "alias fill")
    fill_instruments = {i for l in fill.bars[0].lines for i in l.instruments}
    assert fill_instruments == {"SN", "BD", "CR"}

    # "verse" section carries an "add ride … remove hat" variation.
    verse = next(s for s in song.sections if s.name == "verse")
    variation = verse.variations[0]
    add_action = next(a for a in variation.actions if a.action == "add")
    remove_action = next(a for a in variation.actions if a.action == "remove")
    assert add_action.instrument == "RD"
    assert remove_action.instrument == "HH"
