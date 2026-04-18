from pathlib import Path

import pytest

from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"

FLAM_GROOVE_SRC = """\
groove "flam groove":
    BD: 1 flam, 3
    SN: 2 accent, 4 accent
    OH: 1 accent
    HH: 2, 2&, 3, 3&, 4, 4&
"""

FLAM_FILL_SRC = """\
groove "beat":
    HH: *8

fill "flam fill":
  count "3 e & a 4":
    3: SN flam
    3e: SN
    3&: SN drag
    3a: SN
    4: BD, CR

section "intro":
  bars: 1
  groove: "beat"
"""


def test_parse_beat_with_flam_modifier():
    song = parse(FLAM_GROOVE_SRC)
    bd_line = song.grooves[0].pattern[0]
    assert bd_line.instrument == "BD"
    # First beat has flam modifier; second has none
    assert bd_line.beats[0] == "1"
    assert bd_line.beats[0].modifiers == ["flam"]
    assert bd_line.beats[1] == "3"
    assert bd_line.beats[1].modifiers == []


def test_parse_beat_accent_on_instrument_line():
    song = parse(FLAM_GROOVE_SRC)
    oh_line = song.grooves[0].pattern[2]
    assert oh_line.instrument == "OH"
    assert oh_line.beats[0] == "1"
    assert oh_line.beats[0].modifiers == ["accent"]


def test_parse_fill_instrument_flam():
    song = parse(FLAM_FILL_SRC)
    fill = song.fills[0]
    line_3 = fill.bars[0].lines[0]
    assert line_3.beat == "3"
    assert line_3.instruments[0] == "SN"
    assert line_3.instruments[0].modifiers == ["flam"]


def test_parse_fill_instrument_drag():
    song = parse(FLAM_FILL_SRC)
    fill = song.fills[0]
    line_3and = fill.bars[0].lines[2]
    assert line_3and.beat == "3&"
    assert line_3and.instruments[0] == "SN"
    assert line_3and.instruments[0].modifiers == ["drag"]


def test_parse_variation_flam_modifier():
    src = """\
groove "beat":
    HH: *8

section "verse":
  bars: 2
  groove: "beat"
  variation "add flam" at bar 2:
    add SN flam at 1
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.modifiers == ["flam"]


def test_parse_file_fixture_modifiers():
    song = parse_file(str(FIXTURES / "modifiers_and_srs.gs"))
    assert song.metadata.title == "Modifiers"
    groove = song.grooves[0]
    assert groove.name == "flam groove"
    sn_line = next(p for p in groove.pattern if p.instrument == "SN")
    assert sn_line.beats[0] == "1"
    assert sn_line.beats[0].modifiers == ["flam"]
    fill = song.fills[0]
    assert fill.name == "flam fill"
    assert fill.bars[0].lines[0].instruments[0].modifiers == ["flam"]


TRIPLET_FILL_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "triplet fill":
  count "3 trip let 4":
    3: SN
    3t: SN
    3l: SN
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "triplet fill" at bar 4 beat 3
"""


def test_parse_triplet_beat_labels():
    song = parse(TRIPLET_FILL_SRC)
    fill = song.fills[0]
    beats_in_bar = [line.beat for line in fill.bars[0].lines]
    assert "3t" in beats_in_bar
    assert "3l" in beats_in_bar


def test_parse_file_fixture_triplets():
    """triplets.gs covers short (`3t`/`3l`), verbose positional (`1trip`/`1let`),
    and bare count-token (`trip`/`let`) forms — all should normalise to the
    canonical `Nt`/`Nl` short form and land on 1/12 / 2/12 triplet positions."""
    from fractions import Fraction
    from groovescript.compiler import compile_song
    from groovescript.lilypond import emit_lilypond

    song = parse_file(str(FIXTURES / "triplets.gs"))
    assert song.metadata.title == "Triplets"

    # Short-form fill: "3 trip let 4" count label with 3t / 3l beat keys.
    short_fill = next(f for f in song.fills if f.name == "triplet fill")
    short_beats = [line.beat for line in short_fill.bars[0].lines]
    assert "3t" in short_beats and "3l" in short_beats

    # Bare-token fill: "1 trip let 2" with `trip` / `let` bare keys that
    # should normalise to `1t` / `1l`.
    bare_fill = next(f for f in song.fills if f.name == "bare trip let")
    bare_beats = [line.beat for line in bare_fill.bars[0].lines]
    assert bare_beats == ["1", "1t", "1l", "2"]

    # Verbose positional groove: `1trip` / `1let` in a pattern line compile to
    # the 1/12 and 2/12 positions within the bar.
    ir = compile_song(song)
    verbose_section = next(
        (i, s) for i, s in enumerate(ir.sections) if s.name == "verbose positional"
    )
    verbose_start_bar = sum(
        s.bars for i, s in enumerate(ir.sections) if i < verbose_section[0]
    )
    first_verbose_bar = ir.bars[verbose_start_bar]
    sn_positions = sorted(
        e.beat_position for e in first_verbose_bar.events if e.instrument == "SN"
    )
    # SN at 1t, 1l, 3t, 3l → positions 1/12, 2/12, 7/12, 8/12
    assert Fraction(1, 12) in sn_positions
    assert Fraction(2, 12) in sn_positions
    assert Fraction(7, 12) in sn_positions
    assert Fraction(8, 12) in sn_positions

    # Full song emits LilyPond without error and includes a triplet tuplet.
    ly = emit_lilypond(ir)
    assert "\\tuplet 3/2" in ly


THREE_FOUR_SRC = """\
title: "Waltz"
tempo: 120
time_signature: 3/4

groove "waltz":
    BD: 1
    HH: *8
    SN: 2, 3

section "A":
  bars: 4
  groove: "waltz"
"""

SIX_EIGHT_SRC = """\
title: "6/8 Groove"
tempo: 80
time_signature: 6/8

groove "compound":
    BD: 1, 4
    HH: *8
    SN: 3, 6

section "A":
  bars: 4
  groove: "compound"
"""


def test_parse_time_signature_three_four():
    song = parse(THREE_FOUR_SRC)
    assert song.metadata.time_signature == "3/4"


def test_parse_3_4_beat_labels_accepted():
    """Beat labels 1-3 are accepted in a 3/4 groove."""
    song = parse(THREE_FOUR_SRC)
    groove = song.grooves[0]
    sn_beats = groove.bars[0][2].beats  # SN line
    assert "2" in [str(b) for b in sn_beats]
    assert "3" in [str(b) for b in sn_beats]


def test_parse_time_signature_six_eight():
    song = parse(SIX_EIGHT_SRC)
    assert song.metadata.time_signature == "6/8"


def test_parse_6_8_beat_labels_up_to_6():
    """Beat labels 1-6 are accepted in a 6/8 groove."""
    song = parse(SIX_EIGHT_SRC)
    groove = song.grooves[0]
    sn_beats = groove.bars[0][2].beats  # SN line
    assert "3" in [str(b) for b in sn_beats]
    assert "6" in [str(b) for b in sn_beats]


TWELVE_EIGHT_SRC = """\
title: "12/8 Groove"
tempo: 100
time_signature: 12/8

groove "shuffle":
    BD: 1, 7
    SN: 4, 10
    HH: *8

section "A":
  bars: 2
  groove: "shuffle"
"""


def test_parse_time_signature_twelve_eight():
    song = parse(TWELVE_EIGHT_SRC)
    assert song.metadata.time_signature == "12/8"


def test_parse_12_8_beat_labels_up_to_12():
    """Beat labels 1-12 are accepted in a 12/8 groove — double-digit beats parse."""
    song = parse(TWELVE_EIGHT_SRC)
    groove = song.grooves[0]
    sn_beats = [str(b) for b in groove.bars[0][1].beats]
    assert "4" in sn_beats
    assert "10" in sn_beats
    bd_beats = [str(b) for b in groove.bars[0][0].beats]
    assert "7" in bd_beats


def test_parse_12_8_double_digit_beat_pattern_line():
    """Regression: a pattern line listing double-digit beat labels parses."""
    src = """\
title: "12/8"
time_signature: 12/8
groove "compound":
    BD: 10, 12
    HH: *8
section "A":
  bars: 1
  groove: "compound"
"""
    song = parse(src)
    bd_beats = [str(b) for b in song.grooves[0].bars[0][0].beats]
    assert bd_beats == ["10", "12"]


def test_parse_12_8_double_digit_variation_and_suffix():
    """A variation action can use double-digit beat labels (e.g. 12&)."""
    src = """\
title: "12/8"
time_signature: 12/8
groove "compound":
    BD: 1, 7
    HH: *16

section "A":
  bars: 2
  groove: "compound"
  variation at bar 2:
    add SN at 12&
"""
    song = parse(src)
    action = song.sections[0].variations[0].actions[0]
    assert action.beats[0] == "12&"


SECTION_TIME_SIGNATURE_SRC = """\
title: "Mixed Meter"
tempo: 110
time_signature: 4/4

groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "waltz":
    BD: 1
    SN: 2, 3
    HH: *4t

section "verse":
  bars: 2
  groove: "rock"

section "outro":
  bars: 2
  groove: "waltz"
  time_signature: 3/4
"""


def test_parse_section_time_signature():
    song = parse(SECTION_TIME_SIGNATURE_SRC)
    assert song.metadata.time_signature == "4/4"
    assert song.sections[0].time_signature is None
    assert song.sections[1].time_signature == "3/4"


def test_parse_file_fixture_time_signature_3_4():
    """End-to-end: time_signature_3_4.gs compiles a waltz pattern in 3/4
    with 8th-note hats (6 per bar)."""
    from fractions import Fraction
    from groovescript.compiler import compile_song

    song = parse_file(str(FIXTURES / "time_signature_3_4.gs"))
    assert song.metadata.time_signature == "3/4"
    ir = compile_song(song)
    # First bar: BD on 1 (position 0), SN on 2/3 (1/3, 2/3), HH *8 → 6 slots.
    bar1 = ir.bars[0]
    hh_positions = sorted(e.beat_position for e in bar1.events if e.instrument == "HH")
    assert len(hh_positions) == 6
    assert hh_positions == [Fraction(i, 6) for i in range(6)]


def test_parse_file_fixture_time_signature_6_8():
    """End-to-end: time_signature_6_8.gs compiles a 6/8 compound-time groove
    with BD on 1 & 4 (position 0, 1/2) and 8 HH slots per bar."""
    from fractions import Fraction
    from groovescript.compiler import compile_song

    song = parse_file(str(FIXTURES / "time_signature_6_8.gs"))
    assert song.metadata.time_signature == "6/8"
    ir = compile_song(song)
    bar1 = ir.bars[0]
    bd_positions = sorted(e.beat_position for e in bar1.events if e.instrument == "BD")
    assert Fraction(0) in bd_positions
    assert Fraction(3, 6) in bd_positions  # beat 4 in 6/8


def test_parse_file_fixture_time_signature_12_8():
    """End-to-end: time_signature_12_8.gs compiles a 12/8 shuffle with
    double-digit beat labels (7, 10, 12)."""
    from fractions import Fraction
    from groovescript.compiler import compile_song

    song = parse_file(str(FIXTURES / "time_signature_12_8.gs"))
    assert song.metadata.time_signature == "12/8"
    # The "shuffle drive" groove references beat 12 on bar 2 of its body.
    shuffle_drive = next(g for g in song.grooves if g.name == "shuffle drive")
    bar2_bd = next(p for p in shuffle_drive.bars[1] if p.instrument == "BD")
    assert "12" in [str(b) for b in bar2_bd.beats]
    # Whole song compiles.
    ir = compile_song(song)
    assert ir.bars


POS_STYLE_GROOVE_SRC = """\
groove "pos beat":
    1: BD, HH
    1&: HH
    2: SN, HH
    2&: HH
    3: BD, HH
    3&: HH
    4: SN, HH
    4&: HH

section "verse":
  bars: 4
  groove: "pos beat"
"""

INSTR_STYLE_FILL_SRC = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "kick and crash":
  count "4":
    BD: 4
    CR: 4

section "intro":
  bars: 1
  groove: "beat"
"""

MIXED_FILL_SRC = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "snare run":
  count "3 e & a 4":
    SN: 3, 3e, 3&, 3a
    4: BD, CR

section "intro":
  bars: 4
  groove: "beat"
  fill "snare run" at bar 4 beat 3
"""


def test_parse_groove_pos_style_returns_pattern_lines():
    song = parse(POS_STYLE_GROOVE_SRC)
    groove = song.grooves[0]
    assert len(groove.bars) == 1
    # 8 position lines, each with 1-2 instruments → multiple PatternLines
    instruments_in_bar = {line.instrument for line in groove.bars[0]}
    assert "BD" in instruments_in_bar
    assert "SN" in instruments_in_bar
    assert "HH" in instruments_in_bar


def test_parse_groove_pos_style_each_line_has_single_beat():
    song = parse(POS_STYLE_GROOVE_SRC)
    groove = song.grooves[0]
    for line in groove.bars[0]:
        # Each PatternLine normalized from pos-style has exactly one beat
        assert isinstance(line.beats, list)
        assert len(line.beats) == 1


def test_parse_groove_pos_style_bd_beat_labels():
    song = parse(POS_STYLE_GROOVE_SRC)
    groove = song.grooves[0]
    bd_beats = [str(line.beats[0]) for line in groove.bars[0] if line.instrument == "BD"]
    assert "1" in bd_beats
    assert "3" in bd_beats


def test_parse_fill_instr_style_returns_fill_lines():
    song = parse(INSTR_STYLE_FILL_SRC)
    fill = song.fills[0]
    assert fill.name == "kick and crash"
    lines = fill.bars[0].lines
    # BD: 4 and CR: 4 → two FillLines
    assert len(lines) == 2
    beats = {line.beat for line in lines}
    assert beats == {"4"}
    instruments = {line.instruments[0] for line in lines}
    assert instruments == {"BD", "CR"}


def test_parse_fill_instr_style_multiple_beats():
    song = parse(MIXED_FILL_SRC)
    fill = song.fills[0]
    lines = fill.bars[0].lines
    # SN: 3, 3e, 3&, 3a → 4 FillLines (instr style)
    # 4: BD, CR          → 1 FillLine with two instruments (classic pos style)
    # total: 5 FillLines
    assert len(lines) == 5
    sn_lines = [l for l in lines if l.instruments[0] == "SN"]
    assert len(sn_lines) == 4
    beat4_lines = [l for l in lines if l.beat == "4"]
    assert len(beat4_lines) == 1
    assert set(beat4_lines[0].instruments) == {"BD", "CR"}


def test_parse_mixed_multibar_groove_pos_style():
    """A multi-bar groove can use classic style in bar 1 and pos style in bar 2."""
    src = """\
groove "mixed":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      1: BD, HH
      2: SN, HH
      3: BD, HH
      4: SN, HH

section "verse":
  bars: 4
  groove: "mixed"
"""
    song = parse(src)
    groove = song.grooves[0]
    assert len(groove.bars) == 2
    # bar 1 classic: 3 PatternLines (BD, SN, HH)
    bar1_instruments = {l.instrument for l in groove.bars[0]}
    assert bar1_instruments == {"BD", "SN", "HH"}
    # bar 2 pos-style: PatternLines for BD, SN, HH at single beats
    bar2_instruments = {l.instrument for l in groove.bars[1]}
    assert bar2_instruments == {"BD", "SN", "HH"}


def test_parse_groove_pos_style_with_modifier():
    """Position→instruments notation supports modifiers on instrument hits."""
    src = """\
groove "fancy":
    1: BD flam, HH

section "v":
  bars: 1
  groove: "fancy"
"""
    song = parse(src)
    bd_line = next(l for l in song.grooves[0].bars[0] if l.instrument == "BD")
    assert bd_line.beats[0].modifiers == ["flam"]


def test_parse_fill_instr_style_with_modifier():
    """Instrument→positions notation in fills supports modifiers on beat hits."""
    src = """\
groove "beat":
    HH: *8

fill "fancy fill":
  count "3 e":
    SN: 3 flam, 3e

section "intro":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    fill = song.fills[0]
    flam_line = next(l for l in fill.bars[0].lines if l.beat == "3")
    assert flam_line.instruments[0].modifiers == ["flam"]
    plain_line = next(l for l in fill.bars[0].lines if l.beat == "3e")
    assert plain_line.instruments[0].modifiers == []


def test_parse_file_fixture_dual_notation():
    song = parse_file(str(FIXTURES / "dual_notation.gs"))
    assert song.metadata.title == "Dual Notation"
    assert song.metadata.tempo == 120
    # Should have grooves using both notations
    groove_names = {g.name for g in song.grooves}
    assert "money beat" in groove_names   # classic style
    assert "open beat" in groove_names    # pos style
    assert "two bar" in groove_names      # mixed multi-bar
    # Should have fills using both notations
    fill_names = {f.name for f in song.fills}
    assert "crash landing" in fill_names  # instr style
    assert "snare run" in fill_names      # mixed style


# ── Comma-free simultaneous-hit groups inside notes: strings ──────────────
#
# Paren groups in `notes:` values accept either comma or whitespace
# separation between instruments (`(bass crash)` ≡ `(bass, crash)`).

def test_parse_comma_free_simultaneous_group_in_fill():
    """`(crash bass)` inside a count+notes fill is equivalent to `(crash, bass)`."""
    src = """\
fill "shot":
  count: 1 and
  notes: (crash bass), snare

groove "beat":
    HH: *8

section "s":
  bars: 1
  groove: "beat"
  fill "shot" at bar 1
"""
    song = parse(src)
    bar = song.fills[0].bars[0]
    assert len(bar.lines) == 2
    first_instruments = sorted(str(i) for i in bar.lines[0].instruments)
    assert first_instruments == ["BD", "CR"]


def test_parse_comma_free_simultaneous_group_with_outer_modifier():
    """A modifier after a paren group attaches to every instrument in the group."""
    src = """\
fill "smash":
  count: 1
  notes: (crash bass) accent
"""
    song = parse(src)
    instruments = song.fills[0].bars[0].lines[0].instruments
    assert {str(i) for i in instruments} == {"BD", "CR"}
    for inst in instruments:
        assert "accent" in inst.modifiers


def test_parse_comma_free_simultaneous_group_with_per_instrument_modifier():
    """Modifiers inside a whitespace-separated group attach to the preceding instrument only."""
    src = """\
fill "mix":
  count: 1
  notes: (snare accent bass)
"""
    song = parse(src)
    instruments = song.fills[0].bars[0].lines[0].instruments
    by_name = {str(i): i for i in instruments}
    assert set(by_name.keys()) == {"SN", "BD"}
    assert "accent" in by_name["SN"].modifiers
    assert by_name["BD"].modifiers == []
