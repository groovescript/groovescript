"""Tests for the ``lint --style`` stylistic checker."""

from __future__ import annotations

from groovescript.compiler import compile_groove, compile_song
from groovescript.lint import check_notation, check_style
from groovescript.parser import parse


def _lint(src: str) -> list[str]:
    song = parse(src, filename="song.gs")
    return [w.message for w in check_style(src, song)]


# ── Mixed instrument→positions vs position→instruments styles ────────────


def test_mixed_groove_styles_are_warned() -> None:
    """A single-bar groove body that contains both an instrument-headed
    line (``BD: 1, 3``) and a position-headed line (``1: CR``) flags a
    single "mixed style" warning pointing at the later line.
    """
    src = (
        'groove "rock":\n'
        "    BD: 1, 3\n"
        "    SN: 2, 4\n"
        "    1: CR\n"
        'section "s":\n'
        "  bars: 1\n"
        "  groove: \"rock\"\n"
    )
    song = parse(src, filename="song.gs")
    warnings = check_style(src, song)
    mixed = [w for w in warnings if "mixes" in w.message]
    assert len(mixed) == 1
    assert mixed[0].line == 4
    assert mixed[0].hint is not None


def test_consistent_groove_style_is_silent() -> None:
    src = (
        'groove "rock":\n'
        "    BD: 1, 3\n"
        "    SN: 2, 4\n"
        'section "s":\n'
        "  bars: 1\n"
        "  groove: \"rock\"\n"
    )
    assert _lint(src) == []


def test_mixed_styles_are_scoped_per_bar_in_multi_bar_grooves() -> None:
    """A multi-bar groove where each bar independently uses one style
    (bar 1 instrument→positions, bar 2 position→instruments) does NOT
    warn — the check is scoped per bar, not across the whole groove.
    """
    src = (
        'groove "two bar":\n'
        "    bar 1:\n"
        "      BD: 1, 3\n"
        "      SN: 2, 4\n"
        "    bar 2:\n"
        "      1: BD, HH\n"
        "      2: SN, HH\n"
        'section "s":\n'
        "  bars: 2\n"
        "  groove: \"two bar\"\n"
    )
    assert _lint(src) == []


def test_mixed_styles_within_a_single_bar_block_is_warned() -> None:
    src = (
        'groove "two bar":\n'
        "    bar 1:\n"
        "      BD: 1, 3\n"
        "      1: CR\n"
        "    bar 2:\n"
        "      BD: 1\n"
        'section "s":\n'
        "  bars: 2\n"
        "  groove: \"two bar\"\n"
    )
    song = parse(src, filename="song.gs")
    warnings = check_style(src, song)
    mixed = [w for w in warnings if "mixes" in w.message]
    assert len(mixed) == 1
    # The warning points at the offending second-style line, inside bar 1.
    assert mixed[0].line == 4


# ── Unused grooves / fills ────────────────────────────────────────────────


def test_unused_groove_is_warned() -> None:
    src = (
        'groove "used":\n'
        "    BD: 1\n"
        'groove "unused":\n'
        "    BD: 2\n"
        'section "s":\n'
        "  bars: 1\n"
        "  groove: \"used\"\n"
    )
    messages = _lint(src)
    assert any("'unused' is defined but never used" in m for m in messages)
    assert not any("'used' is defined but never used" in m for m in messages)


def test_unused_fill_is_warned() -> None:
    src = (
        'groove "g":\n'
        "    BD: 1\n"
        'fill "crash":\n'
        "  count: 1 2 3 4\n"
        "  notes: BD, BD, BD, BD\n"
        'section "s":\n'
        "  bars: 1\n"
        "  groove: \"g\"\n"
    )
    messages = _lint(src)
    assert any("'crash' is defined but never used" in m for m in messages)


def test_extend_target_groove_is_not_reported_as_unused() -> None:
    """A groove referenced only via another groove's ``extend:`` should
    still count as "used" — removing it would break the extension.
    """
    src = (
        'groove "base":\n'
        "    BD: 1, 3\n"
        'groove "fancy":\n'
        "  extend: \"base\"\n"
        "  CR: 1\n"
        'section "s":\n'
        "  bars: 1\n"
        "  groove: \"fancy\"\n"
    )
    messages = _lint(src)
    assert not any("'base'" in m for m in messages)


# ── `like` references to missing sections ────────────────────────────────


def test_like_reference_to_missing_section_is_warned() -> None:
    src = (
        'groove "g":\n'
        "    BD: 1\n"
        'section "verse":\n'
        "  bars: 1\n"
        "  groove: \"g\"\n"
        'section "chorus":\n'
        "  bars: 1\n"
        "  like \"vers\"\n"  # typo: should be "verse"
    )
    song = parse(src, filename="song.gs")
    warnings = check_style(src, song)
    like_warnings = [w for w in warnings if "`like " in w.message]
    assert len(like_warnings) == 1
    # The hint should suggest the closest real section name.
    assert like_warnings[0].hint is not None
    assert "verse" in like_warnings[0].hint


def test_like_reference_to_existing_section_is_silent() -> None:
    src = (
        'groove "g":\n'
        "    BD: 1\n"
        'section "verse":\n'
        "  bars: 1\n"
        "  groove: \"g\"\n"
        'section "chorus":\n'
        "  bars: 1\n"
        "  like \"verse\"\n"
    )
    messages = _lint(src)
    assert not any("`like " in m for m in messages)


# ── check_notation: simultaneous hand-instrument limit ───────────────────


def test_three_simultaneous_hand_instruments_warns() -> None:
    """Regression: check_notation warns when >2 hand-played instruments share a beat position."""
    src = """\
groove "busy":
    1: HH, SN, OH
    2: BD
    3: HH
    4: SN
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    warnings = check_notation(ir)
    assert len(warnings) == 1
    w = warnings[0]
    assert "3 hand-played instruments" in w.message
    assert "HH" in w.message
    assert "SN" in w.message
    assert "OH" in w.message
    assert w.hint is not None


def test_two_simultaneous_hand_instruments_is_silent() -> None:
    """Two hand-played instruments at the same beat is physically possible and should not warn."""
    src = """\
groove "normal":
    1: HH, SN
    2: BD
    3: HH, SN
    4: BD
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    assert check_notation(ir) == []


def test_foot_plus_hand_instruments_do_not_count_toward_limit() -> None:
    """BD and HF are foot-played; they don't count toward the 2-hand limit."""
    src = """\
groove "kick heavy":
    1: BD, HH, SN
    2: HF, HH, SN
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    assert check_notation(ir) == []


def test_check_notation_on_irsong_warns_in_arranged_bar() -> None:
    """check_notation flags simultaneous hand hits in a compiled IRSong."""
    src = """\
groove "busy":
    1: HH, SN, OH
    2: BD

section "verse":
  bars: 1
  groove: "busy"
"""
    song = parse(src)
    ir = compile_song(song)
    warnings = check_notation(ir)
    assert len(warnings) == 1
    assert "3 hand-played instruments" in warnings[0].message


def test_notation_warning_carries_source_line() -> None:
    """Regression: notation warnings from groove pattern lines must carry the
    source line so `groovescript lint` can render a Rust-style diagnostic with
    a file:line pointer instead of a bare bar number.
    """
    src = """\
groove "busy":
    1: HH, SN, OH
    2: BD
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    warnings = check_notation(ir)
    assert len(warnings) == 1
    # The conflicting pattern line is line 2 of the source.
    assert warnings[0].line == 2


def test_notation_warning_from_modify_add_flam_points_at_variation() -> None:
    """Regression: when `modify add flam` on an existing hit creates a hand
    conflict with another instrument at the same beat, the warning should
    point at the variation line (that's the newly-introduced conflict
    source), not the unchanged pattern line that just happened to be there.
    """
    src = """\
groove "base":
    1: HH
    2: SN
    3: HH
    4: SN, HH

section "verse":
  bars: 1
  groove: "base"
  variation at bar 1:
    modify add flam to snare at 4
"""
    song = parse(src)
    ir = compile_song(song)
    warnings = check_notation(ir)
    assert len(warnings) == 1
    # `modify add flam to snare at 4` is on line 11 of the source.
    assert warnings[0].line == 11


# ── check_notation: flam + simultaneous hand instrument ──────────────────


def test_flam_with_simultaneous_hand_instrument_warns() -> None:
    """Regression: flam uses both hands, so any other simultaneous hand instrument must be flagged."""
    src = """\
groove "flamming":
    1: SN flam, HH
    2: BD
    3: HH
    4: SN
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    warnings = check_notation(ir)
    assert len(warnings) == 1
    w = warnings[0]
    assert "flam" in w.message
    assert "SN" in w.message
    assert "HH" in w.message
    assert w.hint is not None


def test_flam_alone_on_hand_instrument_is_silent() -> None:
    """A flam with no other simultaneous hand instrument is physically fine."""
    src = """\
groove "solo flam":
    1: SN flam
    2: BD
    3: HH
    4: SN
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    assert check_notation(ir) == []


def test_flam_with_foot_instrument_is_silent() -> None:
    """A flam alongside only foot instruments (BD, HF) should not warn."""
    src = """\
groove "flam kick":
    1: SN flam, BD
    2: HH
    3: SN
    4: HH
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    assert check_notation(ir) == []
