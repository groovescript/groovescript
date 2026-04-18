"""Tests for snare buzz-roll support."""
from fractions import Fraction
from pathlib import Path

import pytest

from groovescript.ast_nodes import (
    BeatHit,
    FillBar,
    FillLine,
    Groove,
    InstrumentHit,
    PatternLine,
)
from groovescript.compiler import compile_fill_bar, compile_groove, compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_fixture_buzz_roll():
    """End-to-end: buzz_roll.gs parses, compiles, and emits tremolo tokens for
    buzz rolls in pattern lines, within fills, and crossing bar lines."""
    song = parse_file(str(FIXTURES / "buzz_roll.gs"))
    assert song.metadata.title == "Buzz Roll Demo"
    # Groove "buzz tie across bar" has a buzz:2 on beat 4 of bar 1 that ties
    # into bar 2.
    tie_groove = next(g for g in song.grooves if g.name == "buzz tie across bar")
    bar1_sn = next(p for p in tie_groove.bars[0] if p.instrument == "SN")
    assert bar1_sn.beats[0].modifiers == ["buzz"]
    assert bar1_sn.beats[0].buzz_duration == "2"
    # Fill uses buzz:2 on the last hit.
    buzz_fill = next(f for f in song.fills if f.name == "buzz fill")
    last_hit = buzz_fill.bars[0].lines[-1].instruments[0]
    assert last_hit.modifiers == ["buzz"]
    # Whole song compiles and emits valid LilyPond with the :32 tremolo.
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert ":32" in ly


# ── Parser tests ──────────────────────────────────────────────────────────────


def test_parse_bare_buzz_modifier_pattern_line():
    """Bare ``buzz`` modifier defaults to quarter-note duration."""
    src = """\
groove "g":
    SN: 3 buzz
"""
    song = parse(src)
    sn = song.grooves[0].pattern[0]
    beat = sn.beats[0]
    assert str(beat) == "3"
    assert beat.modifiers == ["buzz"]
    assert beat.buzz_duration == "4"


def test_parse_buzz_with_explicit_duration():
    """``buzz:2`` is parsed as a half-note buzz."""
    src = """\
groove "g":
    SN: 3 buzz:2
"""
    song = parse(src)
    sn = song.grooves[0].pattern[0]
    beat = sn.beats[0]
    assert beat.modifiers == ["buzz"]
    assert beat.buzz_duration == "2"


def test_parse_buzz_dotted_and_double_dotted():
    """Dotted and double-dotted durations round-trip through the parser."""
    for spec in ("2d", "2dd", "4d", "8dd"):
        src = f"""\
groove "g":
    SN: 1 buzz:{spec}
"""
        song = parse(src)
        assert song.grooves[0].pattern[0].beats[0].buzz_duration == spec


def test_parse_buzz_on_position_line():
    """``buzz`` after an instrument on a position→instruments line."""
    src = """\
groove "g":
    3: SN buzz:2
"""
    song = parse(src)
    # groove_pos_line → PatternLine per instrument
    sn = song.grooves[0].pattern[0]
    assert sn.instrument == "SN"
    assert sn.beats[0].modifiers == ["buzz"]
    assert sn.beats[0].buzz_duration == "2"


def test_parse_buzz_in_fill_line():
    """``buzz`` on a fill count-block line is preserved on the instrument hit."""
    src = """\
fill "f":
  count "1 2 3 4":
    3: SN buzz:2
"""
    song = parse(src)
    hit = song.fills[0].bars[0].lines[0].instruments[0]
    assert hit.modifiers == ["buzz"]
    assert hit.buzz_duration == "2"


def test_parse_buzz_in_variation_add():
    """``buzz`` on a variation add action is preserved."""
    src = """\
groove "g":
    HH: *8
    BD: 1, 3
    SN: 2, 4

section "s":
  bars: 2
  groove: "g"
  variation at bar 2:
    add SN buzz:2 at 3
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.action == "add"
    assert action.instrument == "SN"
    assert action.modifiers == ["buzz"]
    assert action.buzz_duration == "2"


def test_parse_buzz_in_variation_replace():
    """``buzz`` on a replace target is preserved."""
    src = """\
groove "g":
    SN: 2, 4

section "s":
  bars: 1
  groove: "g"
  variation at bar 1:
    replace SN with SN buzz:4 at 4
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.action == "replace"
    assert action.modifiers == ["buzz"]
    assert action.buzz_duration == "4"


def test_parse_buzz_in_count_notes_fill():
    """``buzz`` in a count+notes notes string attaches to the instrument."""
    src = """\
fill "f":
  count: "1 2 3 4"
  notes: "SN SN SN buzz:4 SN"
"""
    song = parse(src)
    bar = song.fills[0].bars[0]
    hit = bar.lines[2].instruments[0]
    assert hit.instrument == "SN"
    assert hit.modifiers == ["buzz"]
    assert hit.buzz_duration == "4"


# ── Compiler tests ────────────────────────────────────────────────────────────


def test_compile_buzz_event_has_duration():
    """A compiled buzz event carries the correct bar-relative duration."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(
                instrument="SN",
                beats=[BeatHit("3", ["buzz"], buzz_duration="2")],
            ),
        ]],
    )
    ir = compile_groove(g)
    event = ir.events[0]
    assert event.instrument == "SN"
    assert event.duration == Fraction(1, 2)  # half-note = half a bar in 4/4
    assert "buzz" in event.modifiers


def test_compile_buzz_quarter_default():
    """A bare ``buzz`` modifier compiles to a quarter-note span (1/4 of 4/4)."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(
                instrument="SN",
                beats=[BeatHit("1", ["buzz"], buzz_duration="4")],
            ),
        ]],
    )
    ir = compile_groove(g)
    assert ir.events[0].duration == Fraction(1, 4)


def test_compile_buzz_dotted():
    """A dotted buzz compiles to 1.5× the base span."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(
                instrument="SN",
                beats=[BeatHit("1", ["buzz"], buzz_duration="4d")],
            ),
        ]],
    )
    ir = compile_groove(g)
    # Dotted quarter in 4/4 = 3/8 of a bar.
    assert ir.events[0].duration == Fraction(3, 8)


def test_compile_buzz_on_non_snare_raises():
    """Buzz rolls are snare-only."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(
                instrument="HH",
                beats=[BeatHit("1", ["buzz"], buzz_duration="4")],
            ),
        ]],
    )
    with pytest.raises(ValueError, match="only supported on SN"):
        compile_groove(g)


def test_compile_buzz_past_song_end_raises():
    """A buzz whose tie continuation has no next bar to land in is rejected."""
    src = """\
groove "g":
    SN: 4 buzz:2

section "s":
  bars: 1
  groove: "g"
"""
    song = parse(src)
    with pytest.raises(ValueError, match="ties past the end of the song"):
        compile_song(song)


@pytest.mark.parametrize("bad_mod", ["flam", "drag", "double", "ghost"])
def test_compile_buzz_incompatible_modifier(bad_mod):
    """``buzz`` is incompatible with flam/drag/double/ghost."""
    g = Groove(
        name="g",
        bars=[[
            PatternLine(
                instrument="SN",
                beats=[BeatHit("1e", ["buzz", bad_mod], buzz_duration="4")],
            ),
        ]],
    )
    with pytest.raises(ValueError, match="incompatible"):
        compile_groove(g)


def test_compile_buzz_overlapping_hh_raises():
    """A hand-played event inside the buzz span is rejected."""
    src = """\
groove "g":
    HH: *8
    SN: 3 buzz:2

section "s":
  bars: 1
  groove: "g"
"""
    song = parse(src)
    with pytest.raises(ValueError, match="overlaps a snare buzz roll span"):
        compile_song(song)


def test_compile_buzz_with_bd_overlap_allowed():
    """A foot-played BD inside the buzz span is allowed."""
    src = """\
groove "g":
    BD: 1, 3, 4
    SN: 3 buzz:2

section "s":
  bars: 1
  groove: "g"
"""
    song = parse(src)
    ir = compile_song(song)
    # BD events on beats 3 and 4 should still be present alongside the buzz.
    bar1 = ir.bars[0]
    bd_events = [e for e in bar1.events if e.instrument == "BD"]
    assert len(bd_events) == 3


def test_compile_buzz_with_hf_overlap_allowed():
    """A foot-played hi-hat chick (HF) inside the buzz span is allowed."""
    src = """\
groove "g":
    HF: 3, 4
    SN: 3 buzz:2

section "s":
  bars: 1
  groove: "g"
"""
    song = parse(src)
    ir = compile_song(song)
    hf_events = [e for e in ir.bars[0].events if e.instrument == "HF"]
    assert len(hf_events) == 2


def test_compile_buzz_in_fill():
    """Buzz in a fill bar compiles cleanly and carries a duration on the event."""
    fb = FillBar(
        label="1 2 3 4",
        lines=[
            FillLine(beat="3", instruments=[InstrumentHit("SN", ["buzz"], buzz_duration="2")]),
        ],
    )
    ir = compile_fill_bar(fb)
    assert ir.events[0].duration == Fraction(1, 2)


# ── LilyPond emitter tests ────────────────────────────────────────────────────


def _song_ly(src: str) -> str:
    song = parse(src)
    ir = compile_song(song)
    return emit_lilypond(ir)


def test_emit_buzz_quarter_note():
    """A quarter-note buzz emits ``sn4:32``."""
    src = """\
groove "g":
    SN: 1 buzz:4

section "s":
  bars: 1
  groove: "g"
"""
    ly = _song_ly(src)
    assert "sn4:32" in ly


def test_emit_buzz_half_note_at_downbeat():
    """A half-note buzz on beat 3 emits ``sn2:32``."""
    src = """\
groove "g":
    SN: 3 buzz:2

section "s":
  bars: 1
  groove: "g"
"""
    ly = _song_ly(src)
    assert "sn2:32" in ly


def test_emit_buzz_dotted_emits_dot():
    """A dotted-half buzz renders with a dotted-duration token."""
    src = """\
groove "g":
    SN: 2 buzz:2d

section "s":
  bars: 1
  groove: "g"
"""
    ly = _song_ly(src)
    # LilyPond uses "2." for a dotted half.
    assert "sn2.:32" in ly


def test_emit_buzz_with_accent():
    """Accent on a buzz event attaches ``->``."""
    src = """\
groove "g":
    SN: 3 buzz:2 accent

section "s":
  bars: 1
  groove: "g"
"""
    ly = _song_ly(src)
    assert "sn2:32->" in ly


def test_emit_buzz_with_bd_overlap_emits_voice_split():
    """A buzz span overlapping BD renders as a localized voice split."""
    src = """\
groove "g":
    BD: 3, 4
    SN: 3 buzz:2

section "s":
  bars: 1
  groove: "g"
"""
    ly = _song_ly(src)
    assert "<<" in ly and ">>" in ly
    assert "{ sn2:32 }" in ly
    assert r"\\" in ly  # voice-split separator
    assert "bd4 bd4" in ly


def test_emit_buzz_without_foot_overlap_has_no_voice_split():
    """A buzz with no overlapping foot events emits a plain token."""
    src = """\
groove "g":
    BD: 1
    SN: 3 buzz:2

section "s":
  bars: 1
  groove: "g"
"""
    ly = _song_ly(src)
    # Voice split should not appear.
    assert "<<" not in ly
    assert "sn2:32" in ly


def test_compile_buzz_ties_across_barline():
    """Regression: buzz at beat 4 with buzz:2 in a 2-bar groove ties into bar 2.

    Before cross-bar buzz support this raised "extends past the end of the bar";
    now it splits into two tied half-buzz events (a quarter in bar 1 + a quarter
    in bar 2 with the head event marked tied_to_next).
    """
    src = """\
groove "g":
    bar 1:
        SN: 4 buzz:2
    bar 2:
        BD: 1

section "s":
  bars: 2
  groove: "g"
"""
    song = parse(src)
    ir = compile_song(song)
    bar1, bar2 = ir.bars
    bar1_buzzes = [e for e in bar1.events if "buzz" in e.modifiers]
    bar2_buzzes = [e for e in bar2.events if "buzz" in e.modifiers]
    assert len(bar1_buzzes) == 1
    head = bar1_buzzes[0]
    assert head.beat_position == Fraction(3, 4)
    assert head.duration == Fraction(1, 4)
    assert head.tied_to_next is True
    # Bar 2 has the continuation at beat 1.
    continuations = [e for e in bar2_buzzes if e.beat_position == 0]
    assert len(continuations) == 1
    assert continuations[0].duration == Fraction(1, 4)
    assert continuations[0].tied_to_next is False  # ends within bar 2


def test_compile_whole_note_buzz_at_beat_4_spans_two_bars():
    """A whole-note buzz starting at beat 4 spans exactly two bars (1 + 3 beats)."""
    src = """\
groove "g":
    bar 1:
        SN: 4 buzz:1
    bar 2:
        BD: 4

section "s":
  bars: 2
  groove: "g"
"""
    song = parse(src)
    ir = compile_song(song)
    bar1, bar2 = ir.bars
    head = next(e for e in bar1.events if "buzz" in e.modifiers)
    assert head.beat_position == Fraction(3, 4)
    assert head.duration == Fraction(1, 4)
    assert head.tied_to_next is True
    tail = next(e for e in bar2.events if "buzz" in e.modifiers and e.beat_position == 0)
    assert tail.duration == Fraction(3, 4)
    assert tail.tied_to_next is False


def test_compile_buzz_tie_overlap_with_hand_in_next_bar_raises():
    """A continuation that lands on a hand-played event in the next bar errors."""
    src = """\
groove "g":
    bar 1:
        HH: *4
        SN: 4 buzz:2
    bar 2:
        HH: *4

section "s":
  bars: 2
  groove: "g"
"""
    song = parse(src)
    with pytest.raises(ValueError, match="overlaps a snare buzz roll"):
        compile_song(song)


def test_compile_buzz_tie_with_bd_overlap_in_next_bar_allowed():
    """A continuation overlapping a foot-played BD in the next bar is allowed."""
    src = """\
groove "g":
    bar 1:
        BD: 1, 3
        SN: 4 buzz:2
    bar 2:
        BD: 1, 3

section "s":
  bars: 2
  groove: "g"
"""
    song = parse(src)
    ir = compile_song(song)
    # Continuation in bar 2 at beat 1 should coexist with BD on beat 1 / 3.
    bar2 = ir.bars[1]
    continuations = [e for e in bar2.events if "buzz" in e.modifiers and e.beat_position == 0]
    assert len(continuations) == 1


def test_emit_buzz_tie_across_barline_emits_tilde():
    """A cross-bar buzz emits ``~`` after the head and a fresh tremolo in next bar."""
    src = """\
groove "g":
    bar 1:
        SN: 4 buzz:2
    bar 2:
        BD: 1

section "s":
  bars: 2
  groove: "g"
"""
    ly = _song_ly(src)
    # Head bar emits a tied quarter buzz; continuation bar emits a quarter buzz.
    assert "sn4:32~" in ly
    # The second sn4:32 (continuation) should also appear.
    assert ly.count("sn4:32") >= 2


def test_emit_buzz_tie_no_foot_overlap_omits_voice_split():
    """A tied buzz with no foot overlap on either side emits plain tokens."""
    src = """\
groove "g":
    bar 1:
        SN: 4 buzz:2
    bar 2:
        SN: 3

section "s":
  bars: 2
  groove: "g"
"""
    ly = _song_ly(src)
    # No voice split should be introduced.
    assert "<<" not in ly
    assert "sn4:32~" in ly


def test_emit_buzz_tie_with_foot_overlap_in_continuation_wraps_both_sides():
    """Foot overlap in the continuation forces a voice split on both tie ends
    so LilyPond does not drop the tie across mismatched voice contexts.
    """
    src = """\
groove "g":
    bar 1:
        BD: 1, 3
        SN: 4 buzz:2
    bar 2:
        BD: 1, 3

section "s":
  bars: 2
  groove: "g"
"""
    ly = _song_ly(src)
    # Head bar wraps tied buzz with an empty second voice (rest only).
    assert "<< { sn4:32~ } \\\\ { r4 } >>" in ly
    # Continuation bar wraps with the foot event in the second voice.
    assert "<< { sn4:32 } \\\\ { bd4 } >>" in ly


def test_emit_buzz_tie_past_song_end_raises():
    """A buzz that ties past the last bar of the song is rejected."""
    src = """\
groove "g":
    SN: 4 buzz:2

section "s":
  bars: 1
  groove: "g"
"""
    song = parse(src)
    with pytest.raises(ValueError, match="ties past the end of the song"):
        compile_song(song)


def test_emit_buzz_at_off_beat():
    """A buzz starting on an off-beat (e.g. 3&) renders correctly."""
    src = """\
groove "g":
    HH: 1, 2, 3
    SN: 3& buzz:4

section "s":
  bars: 1
  groove: "g"
"""
    ly = _song_ly(src)
    # The buzz is a quarter note starting at 3& so it spans 3& to 4&.
    assert "sn4:32" in ly
