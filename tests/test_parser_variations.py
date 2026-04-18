from pathlib import Path

import pytest

from groovescript.ast_nodes import InheritSpec, Section, Variation, VariationAction
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"

VARIATION_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "chorus":
  bars: 8
  groove: "money beat"
  variation "chorus lift" at bar 8:
    replace HH with CR at 1
    add SN ghost at 2&
    remove BD at 3
"""

LIKE_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 8
  groove: "money beat"

section "verse 2":
  like "verse"
"""


def test_parse_section_variation_block_and_actions():
    """A named variation block lands on the section with the right actions."""
    song = parse(VARIATION_SRC)
    section = song.sections[0]
    assert len(section.variations) == 1
    v = section.variations[0]
    assert isinstance(v, Variation)
    assert v.name == "chorus lift"
    assert v.bars == [8]

    replace, add, remove = v.actions
    assert all(isinstance(a, VariationAction) for a in (replace, add, remove))

    assert replace.action == "replace"
    assert replace.instrument == "HH"
    assert replace.target_instrument == "CR"
    assert replace.beats == ["1"]
    assert replace.modifiers == []

    assert add.action == "add"
    assert add.instrument == "SN"
    assert add.beats == ["2&"]
    assert add.modifiers == ["ghost"]

    assert remove.action == "remove"
    assert remove.instrument == "BD"
    assert remove.beats == ["3"]
    assert remove.modifiers == []


def test_parse_variation_accent_modifier():
    src = """\
groove "beat":
    HH: *8

section "verse":
  bars: 2
  groove: "beat"
  variation "accented" at bar 2:
    add SN accent at 1
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.modifiers == ["accent"]


def test_parse_variation_star_beats():
    src = """\
groove "beat":
    HH: *8

section "verse":
  bars: 2
  groove: "beat"
  variation "swap" at bar 2:
    replace HH with OH at *
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.beats == "*"


def test_parse_like_section():
    song = parse(LIKE_SRC)
    assert len(song.sections) == 2
    like_section = song.sections[1]
    assert isinstance(like_section, Section)
    assert like_section.name == "verse 2"
    assert like_section.inherit == InheritSpec(parent="verse")
    assert like_section.bars is None
    assert like_section.groove is None


def test_parse_like_section_with_categories():
    """``like "x" with fills, variations`` parses into an InheritSpec with those categories."""
    src = """\
groove "beat":
    BD: 1, 3
    HH: *8

section "verse":
  bars: 4
  groove: "beat"

section "verse 2":
  like "verse" with fills, variations
"""
    song = parse(src)
    verse2 = song.sections[1]
    assert verse2.inherit == InheritSpec(
        parent="verse", categories=frozenset({"fills", "variations"})
    )


def test_parse_like_with_categories_comma_optional():
    """Commas between categories are optional."""
    src = """\
groove "beat":
    BD: 1, 3
    HH: *8

section "verse":
  bars: 4
  groove: "beat"

section "verse 2":
  like "verse" with fills cues
"""
    song = parse(src)
    verse2 = song.sections[1]
    assert verse2.inherit == InheritSpec(
        parent="verse", categories=frozenset({"fills", "cues"})
    )


def test_parse_like_duplicate_category_raises():
    src = """\
groove "beat":
    BD: 1, 3

section "verse":
  bars: 4
  groove: "beat"

section "verse 2":
  like "verse" with fills, fills
"""
    with pytest.raises(Exception, match="duplicate inherit category"):
        parse(src)


def test_parse_file_fixture_variations_and_inheritance():
    song = parse_file(str(FIXTURES / "variations_and_inheritance.gs"))
    assert song.metadata.title == "Variations and Inheritance"
    assert song.metadata.tempo == 120
    assert len(song.grooves) == 2
    assert len(song.fills) == 1
    # chorus has a variation
    chorus = next(s for s in song.sections if s.name == "chorus")
    assert len(chorus.variations) == 1
    assert chorus.variations[0].name == "chorus lift"
    # verse 2 uses like
    verse2 = next(s for s in song.sections if s.name == "verse 2")
    assert verse2.inherit is not None
    assert verse2.inherit.parent == "verse"


@pytest.mark.parametrize("action_line,expected_instrument,expected_target", [
    ("add kick at 1, 3",               "BD", None),
    ("remove hat at *",                "HH", None),
    ("replace hat with open at *",     "HH", "OH"),
])
def test_alias_in_variation_action(action_line, expected_instrument, expected_target):
    """Verbose instrument aliases resolve inside variation actions."""
    src = f"""\
groove "beat":
    HH: *8

section "v":
  bars: 2
  groove: "beat"
  variation "v" at bar 2:
    {action_line}
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.instrument == expected_instrument
    if expected_target is not None:
        assert action.target_instrument == expected_target


ANONYMOUS_VARIATION_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "chorus":
  bars: 8
  groove: "money beat"
  variation at bar 8:
    replace HH with CR at 1
    add SN ghost at 2&
"""


def test_parse_anonymous_variation_has_none_name():
    song = parse(ANONYMOUS_VARIATION_SRC)
    v = song.sections[0].variations[0]
    assert v.name is None
    assert v.bars == [8]
    assert len(v.actions) == 2


def test_parse_anonymous_variation_actions_round_trip():
    song = parse(ANONYMOUS_VARIATION_SRC)
    actions = song.sections[0].variations[0].actions
    assert actions[0].action == "replace"
    assert actions[0].instrument == "HH"
    assert actions[0].target_instrument == "CR"
    assert actions[1].action == "add"
    assert actions[1].modifiers == ["ghost"]


def test_parse_mixed_named_and_anonymous_variations():
    src = """\
groove "beat":
    HH: *8

section "v":
  bars: 4
  groove: "beat"
  variation "first" at bar 2:
    add SN at 1
  variation at bar 3:
    add BD at 3
"""
    song = parse(src)
    variations = song.sections[0].variations
    assert variations[0].name == "first"
    assert variations[1].name is None


# ── Variation substitute action ────────────────────────────────────────────
#
# A variation may substitute the target bar's events with a fresh count+notes
# body — same positional grammar as a count+notes fill, stored on the AST as
# VariationAction(action="substitute", count_notes=(count_str, notes_str)).

def test_parse_variation_substitute_action():
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "chorus":
  bars: 2
  groove: "money beat"
  variation "shot" at bar 2:
    count: 1 and 2 and 3 and 4 and
    notes: BD, HH, SN, HH, BD, HH, SN, (BD CR)
"""
    song = parse(src)
    variation = song.sections[0].variations[0]
    assert len(variation.actions) == 1
    action = variation.actions[0]
    assert isinstance(action, VariationAction)
    assert action.action == "substitute"
    assert action.count_notes == (
        "1 and 2 and 3 and 4 and",
        "BD, HH, SN, HH, BD, HH, SN, (BD CR)",
    )


# ── Multi-instrument variation actions ────────────────────────────────────
#
# `add`, `remove`, and `replace` accept a space-separated list of instruments
# in a single action; the transformer expands each into one VariationAction
# per instrument so the downstream AST shape is unchanged.

def test_parse_variation_remove_multiple_instruments_expands_to_actions():
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    remove snare hat at 2
"""
    song = parse(src)
    actions = song.sections[0].variations[0].actions
    assert len(actions) == 2
    assert all(a.action == "remove" for a in actions)
    assert [a.instrument for a in actions] == ["SN", "HH"]
    assert all(a.beats == ["2"] for a in actions)


def test_parse_variation_remove_unquoted_bare_beats():
    """Multi-instrument remove plus a space-separated beat list."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    remove snare hat at 2 3
"""
    song = parse(src)
    actions = song.sections[0].variations[0].actions
    assert len(actions) == 2
    assert [a.beats for a in actions] == [["2", "3"], ["2", "3"]]


def test_parse_variation_add_multiple_instruments_with_modifiers():
    """Trailing modifiers attach to the instrument they immediately follow."""
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    add snare ghost kick accent at 1
"""
    song = parse(src)
    actions = song.sections[0].variations[0].actions
    assert len(actions) == 2
    assert actions[0].instrument == "SN"
    assert actions[0].modifiers == ["ghost"]
    assert actions[1].instrument == "BD"
    assert actions[1].modifiers == ["accent"]


def test_parse_variation_replace_multiple_pairs():
    """`replace a b with x y at N` pairs sources with targets in order."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    replace snare hat with ride crash at 1
"""
    song = parse(src)
    actions = song.sections[0].variations[0].actions
    assert len(actions) == 2
    assert actions[0].action == "replace"
    assert actions[0].instrument == "SN"
    assert actions[0].target_instrument == "RD"
    assert actions[1].instrument == "HH"
    assert actions[1].target_instrument == "CR"


def test_parse_variation_replace_pair_with_target_modifiers():
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    replace hat with crash accent at 1
"""
    song = parse(src)
    actions = song.sections[0].variations[0].actions
    assert actions[0].instrument == "HH"
    assert actions[0].target_instrument == "CR"
    assert actions[0].modifiers == ["accent"]


def test_parse_variation_replace_arity_mismatch_errors():
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    replace snare hat with crash at 1
"""
    with pytest.raises(Exception, match="number of source"):
        parse(src)


# ── Multi-bar variation (A1) ────────────────────────────────────────────────

def test_parse_variation_at_multiple_bars():
    """'variation at bars 4, 8:' applies the same actions to multiple bars."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "chorus":
  bars: 8
  groove: "beat"
  variation "crashes" at bars 4, 8:
    replace HH with CR at 1
"""
    song = parse(src)
    v = song.sections[0].variations[0]
    assert v.name == "crashes"
    assert v.bars == [4, 8]
    assert len(v.actions) == 1
    assert v.actions[0].action == "replace"


def test_parse_anonymous_variation_at_multiple_bars():
    """Anonymous variation with 'bars' keyword and multiple targets."""
    src = """\
groove "beat":
    HH: *8

section "v":
  bars: 4
  groove: "beat"
  variation at bars 2, 3, 4:
    add SN at 2
"""
    song = parse(src)
    v = song.sections[0].variations[0]
    assert v.name is None
    assert v.bars == [2, 3, 4]


# ── Regression: space-separated bar list in ``variation at bars`` ─────────
#
# Regression test for backlog item "variation at bars 1 5: doesn't work.
# Requires the comma". ``variation at bars 1 5:`` must parse the same as
# ``variation at bars 1, 5:``.

def test_parse_variation_at_bars_space_separated_no_comma():
    """``variation at bars 1 5:`` should parse without an explicit comma."""
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 8
  groove: "beat"
  variation at bars 1 5:
    add CR at 1
"""
    song = parse(src)
    v = song.sections[0].variations[0]
    assert v.bars == [1, 5]


def test_parse_variation_named_at_bars_space_separated_no_comma():
    """Named variation with space-separated bar list."""
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 8
  groove: "beat"
  variation "crashes" at bars 2 4 6 8:
    add CR at 1
"""
    song = parse(src)
    v = song.sections[0].variations[0]
    assert v.name == "crashes"
    assert v.bars == [2, 4, 6, 8]


# ── Modify actions: add/remove modifiers on existing events ────────────────
#
# DSL addition: `modify add <mod> at <target>` and
# `modify remove <mod> at <target>` adjust modifiers on events that already
# exist at the target beat positions, without touching the instruments.

def test_parse_modify_add_flam_action():
    src = """\
groove "beat":
    SN: 2, 4
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    modify add flam at 2
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.action == "modify_add"
    assert action.modifiers == ["flam"]
    assert action.beats == ["2"]


def test_parse_modify_remove_accent_action():
    src = """\
groove "beat":
    SN: 2, 4

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    modify remove accent at 1
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.action == "modify_remove"
    assert action.modifiers == ["accent"]
    assert action.beats == ["1"]


def test_parse_modify_add_multiple_modifiers_and_beats():
    """``modify add`` accepts multiple modifiers and a beat list."""
    src = """\
groove "beat":
    SN: 1, 2, 3, 4

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    modify add flam accent at 2, 4
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.action == "modify_add"
    assert action.modifiers == ["flam", "accent"]
    assert action.beats == ["2", "4"]


def test_parse_modify_add_at_star_applies_to_all_beats():
    """``modify add`` with ``at *`` targets every beat in the bar."""
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    modify add ghost at *
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.action == "modify_add"
    assert action.beats == "*"
