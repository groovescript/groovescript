from pathlib import Path

import pytest

from groovescript.ast_nodes import PlayBar, PlayGroove, PlayRest
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"

CUE_SRC = """\
title: "Cue Song"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 8
  groove: "money beat"
  cue "Vocals in" at bar 1
  cue "Chorus!" at bar 5 beat 1
"""


def test_parse_cue_bar_only():
    song = parse(CUE_SRC)
    section = song.sections[0]
    cue = section.cues[0]
    assert cue.text == "Vocals in"
    assert cue.bar == 1
    assert cue.beat is None


def test_parse_cue_with_beat():
    song = parse(CUE_SRC)
    section = song.sections[0]
    cue = section.cues[1]
    assert cue.text == "Chorus!"
    assert cue.bar == 5
    assert cue.beat == "1"


def test_parse_multiple_cues():
    song = parse(CUE_SRC)
    section = song.sections[0]
    assert len(section.cues) == 2


def test_parse_file_fixture_cues_and_annotations():
    song = parse_file(str(FIXTURES / "cues_and_annotations.gs"))
    # Should have at least one section with cues
    sections_with_cues = [s for s in song.sections if s.cues]
    assert len(sections_with_cues) >= 1


SECTION_TEMPO_SRC = """\
title: "Tempo Changes"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 4
  groove: "money beat"

section "breakdown":
  bars: 4
  groove: "money beat"
  tempo: 80

section "outro":
  bars: 4
  groove: "money beat"
  tempo: 100
"""


def test_parse_section_tempo_override():
    song = parse(SECTION_TEMPO_SRC)
    intro = song.sections[0]
    breakdown = song.sections[1]
    outro = song.sections[2]
    assert intro.tempo is None          # no override; falls back to global
    assert breakdown.tempo == 80
    assert outro.tempo == 100


def test_parse_section_default_tempo_is_none():
    """A section without 'tempo:' should have tempo=None (not the global tempo)."""
    song = parse(SECTION_TEMPO_SRC)
    assert song.sections[0].tempo is None


def test_parse_file_fixture_section_tempo():
    song = parse_file(str(FIXTURES / "section_tempo.gs"))
    # At least one section should have a per-section tempo override
    sections_with_tempo = [s for s in song.sections if s.tempo is not None]
    assert len(sections_with_tempo) >= 1


PLAY_BLOCK_SRC = """\
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

fill "crash":
  count "4":
    4: BD, CR

section "verse":
  play:
    groove "money beat" x4
    bar "setup":
      BD: 1, 3
      SN: 4
      CR: 1
    rest x2
    groove "money beat" x4
    bar "setup" x1
  fill "crash" at bar 4
"""


def test_parse_play_block_section_has_play_list():
    song = parse(PLAY_BLOCK_SRC)
    section = song.sections[0]
    assert section.play is not None
    assert section.bars is None
    assert section.groove is None


def test_parse_play_block_item_count():
    song = parse(PLAY_BLOCK_SRC)
    section = song.sections[0]
    assert len(section.play) == 5  # groove x4, bar def, rest x2, groove x4, bar ref


def test_parse_play_groove_item():
    song = parse(PLAY_BLOCK_SRC)
    item = song.sections[0].play[0]
    assert isinstance(item, PlayGroove)
    assert item.groove_name == "money beat"
    assert item.repeat == 4


def test_parse_play_bar_definition():
    song = parse(PLAY_BLOCK_SRC)
    item = song.sections[0].play[1]
    assert isinstance(item, PlayBar)
    assert item.name == "setup"
    assert item.pattern is not None
    assert item.repeat == 1
    instruments = {line.instrument for line in item.pattern}
    assert "BD" in instruments
    assert "SN" in instruments
    assert "CR" in instruments


def test_parse_play_rest_item():
    song = parse(PLAY_BLOCK_SRC)
    item = song.sections[0].play[2]
    assert isinstance(item, PlayRest)
    assert item.repeat == 2


def test_parse_play_bar_reference():
    song = parse(PLAY_BLOCK_SRC)
    item = song.sections[0].play[4]
    assert isinstance(item, PlayBar)
    assert item.name == "setup"
    assert item.pattern is None  # reference, no inline body
    assert item.repeat == 1


def test_parse_play_groove_default_repeat():
    """groove without xN defaults to repeat=1."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "s":
  play:
    groove "beat"
"""
    song = parse(src)
    item = song.sections[0].play[0]
    assert isinstance(item, PlayGroove)
    assert item.repeat == 1


def test_parse_play_rest_default_repeat():
    """rest without xN defaults to repeat=1."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "s":
  play:
    groove "beat"
    rest
"""
    song = parse(src)
    item = song.sections[0].play[1]
    assert isinstance(item, PlayRest)
    assert item.repeat == 1


def test_parse_play_bar_pattern_preserved():
    """A play bar body with explicit pattern lines parses into a PlayBar."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "s":
  play:
    groove "beat"
    bar "fill bar":
      BD: 1
      CR: 1
"""
    song = parse(src)
    item = song.sections[0].play[1]
    assert isinstance(item, PlayBar)
    assert item.pattern is not None
    instruments = {line.instrument for line in item.pattern}
    assert instruments == {"BD", "CR"}


def test_parse_play_section_retains_fills():
    """fill placements are still parsed under a play: section."""
    song = parse(PLAY_BLOCK_SRC)
    section = song.sections[0]
    assert len(section.fills) == 1
    assert section.fills[0].fill_name == "crash"
    assert section.fills[0].bar == 4


INLINE_PLAY_GROOVE_SRC = """\
groove "main":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  play:
    groove "main" x2
    groove x2:
        BD: 1, 3
        SN: 2, 4
        HH: *16
    groove:
        BD: 1
        SN: 3
        HH: *8
    rest
"""


def test_parse_inline_play_groove_item_count():
    song = parse(INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    # 4 play items: named-groove, inline-groove(x2), inline-groove, rest
    assert len(section.play) == 4


def test_parse_inline_play_groove_registers_grooves_on_section():
    song = parse(INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    # Two inline grooves under the play: block.
    assert len(section.inline_grooves) == 2
    assert all(g.name.startswith("__inline_play_groove_") for g in section.inline_grooves)


def test_parse_inline_play_groove_repeat_count():
    song = parse(INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    # item[1] is the x2 inline groove
    item = section.play[1]
    assert isinstance(item, PlayGroove)
    assert item.repeat == 2
    assert item.groove_name.startswith("__inline_play_groove_")


def test_parse_inline_play_groove_default_repeat():
    song = parse(INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    # item[2] is the inline groove with no xN → defaults to 1
    item = section.play[2]
    assert isinstance(item, PlayGroove)
    assert item.repeat == 1


def test_parse_inline_play_groove_body_preserved():
    """The inline groove body lands on Section.inline_grooves with correct pattern."""
    from groovescript.ast_nodes import StarSpec
    song = parse(INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    # The x2 groove has HH: *16 — find it by its HH star value.
    def _has_hh16(groove):
        for line in groove.bars[0]:
            if line.instrument == "HH" and isinstance(line.beats, StarSpec) and line.beats.note_value == 16:
                return True
        return False
    g16 = next(g for g in section.inline_grooves if _has_hh16(g))
    instruments = {line.instrument for line in g16.bars[0]}
    assert instruments == {"BD", "SN", "HH"}


def test_compile_inline_play_groove_end_to_end():
    """An inline play groove compiles without errors and emits LilyPond."""
    from groovescript.compiler import compile_song
    from groovescript.lilypond import emit_lilypond
    song = parse(INLINE_PLAY_GROOVE_SRC)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\score" in ly


MULTIBAR_INLINE_PLAY_GROOVE_SRC = """\
groove "main":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  play:
    groove x2:
      bar 1:
        HH: *8
        SN: 2, 4
        BD: 1, 3
      bar 2:
        HH: *8
        BD: 1, 3and
"""


def test_parse_inline_play_groove_multibar_body():
    """An inline play groove with bar N: blocks produces a multi-bar Groove."""
    song = parse(MULTIBAR_INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    assert len(section.inline_grooves) == 1
    groove = section.inline_grooves[0]
    assert len(groove.bars) == 2
    bar1_instruments = {line.instrument for line in groove.bars[0]}
    bar2_instruments = {line.instrument for line in groove.bars[1]}
    assert bar1_instruments == {"HH", "SN", "BD"}
    assert bar2_instruments == {"HH", "BD"}


def test_compile_inline_play_groove_multibar_end_to_end():
    """A multi-bar inline play groove compiles and repeats correctly."""
    from groovescript.compiler import compile_song
    song = parse(MULTIBAR_INLINE_PLAY_GROOVE_SRC)
    ir = compile_song(song)
    # 2 bars per inline groove * repeat=2 = 4 bars
    assert len(ir.bars) == 4


EXTEND_INLINE_PLAY_GROOVE_SRC = """\
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  play:
    groove x2:
      extend: "rock"
"""


def test_parse_inline_play_groove_extend_body():
    """An inline play groove with extend: inherits from the named base groove."""
    song = parse(EXTEND_INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    assert len(section.inline_grooves) == 1
    groove = section.inline_grooves[0]
    assert groove.extend == "rock"


def test_compile_inline_play_groove_extend_end_to_end():
    """An extend: inline play groove resolves to the base groove's pattern."""
    from groovescript.compiler import compile_song
    song = parse(EXTEND_INLINE_PLAY_GROOVE_SRC)
    ir = compile_song(song)
    # 1 bar per extend * repeat=2 = 2 bars
    assert len(ir.bars) == 2
    # Extended groove must carry the base groove's instruments.
    instruments = {ev.instrument for bar in ir.bars for ev in bar.events}
    assert {"BD", "SN", "HH"}.issubset(instruments)


NAMED_INLINE_PLAY_GROOVE_SRC = """\
groove "base":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  play:
    groove "ride the tom" x2:
        floortom: *8
        kick: 1, 3
        snare: 2, 4
    groove "base" x1
    groove "ride the tom" x2
"""


def test_parse_named_inline_play_groove_uses_user_name():
    """A named inline play groove registers under the user-supplied name."""
    song = parse(NAMED_INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    assert len(section.inline_grooves) == 1
    assert section.inline_grooves[0].name == "ride the tom"


def test_parse_named_inline_play_groove_later_reference_resolves():
    """Subsequent ``groove "<name>" xN`` items reference the inline definition."""
    song = parse(NAMED_INLINE_PLAY_GROOVE_SRC)
    section = song.sections[0]
    # play items: inline-definition, named "base" x1, named "ride the tom" x2
    assert len(section.play) == 3
    first, _, third = section.play
    assert isinstance(first, PlayGroove)
    assert first.groove_name == "ride the tom"
    assert first.repeat == 2
    assert isinstance(third, PlayGroove)
    assert third.groove_name == "ride the tom"
    assert third.repeat == 2


def test_compile_named_inline_play_groove_end_to_end():
    """Named inline play groove compiles; later references resolve to it."""
    from groovescript.compiler import compile_song
    song = parse(NAMED_INLINE_PLAY_GROOVE_SRC)
    ir = compile_song(song)
    # inline def x2 (1 bar) + "base" x1 (1 bar) + named ref x2 (1 bar) = 5 bars
    assert len(ir.bars) == 5
    # Bars 0,1,3,4 are "ride the tom" bars — must contain floortom (FT) events.
    floortom_bar_indices = {
        i for i, bar in enumerate(ir.bars)
        for ev in bar.events if ev.instrument == "FT"
    }
    assert floortom_bar_indices == {0, 1, 3, 4}


def test_parse_play_errors_mixing_bars_and_play():
    src = """\
groove "beat":
    BD: 1
    SN: 2
    HH: *8

section "bad":
  bars: 4
  groove: "beat"
  play:
    groove "beat" x4
"""
    with pytest.raises(Exception, match="mutually exclusive"):
        parse(src)


def test_parse_play_errors_mixing_repeat_and_play():
    src = """\
groove "beat":
    BD: 1
    SN: 2
    HH: *8

section "bad":
  repeat: 2
  play:
    groove "beat" x4
"""
    with pytest.raises(Exception):
        parse(src)


def test_parse_file_fixture_full_song_example():
    song = parse_file(str(FIXTURES / "full_song_example.gs"))
    assert song.metadata.title == "Full Song Example"
    assert len(song.sections) == 7
    # verify some complex structure
    bridge = next(s for s in song.sections if s.name == "bridge")
    assert bridge.repeat == 2
    assert len(bridge.variations) == 1


def test_parse_file_fixture_chained_like():
    """End-to-end: chained_like.gs chains ``like`` through three sections
    (verse → verse 2 → verse 3); all three should inherit the groove, bars,
    and the fill placement from the first."""
    from groovescript.compiler import compile_song

    song = parse_file(str(FIXTURES / "chained_like.gs"))
    assert song.metadata.title == "Chained Like"
    sections = {s.name: s for s in song.sections}
    assert sections["verse 2"].inherit is not None
    assert sections["verse 2"].inherit.parent == "verse"
    assert sections["verse 3"].inherit is not None
    assert sections["verse 3"].inherit.parent == "verse 2"
    # After compile, all three sections share the same resolved groove and bars.
    ir = compile_song(song)
    assert len(ir.sections) == 3
    verse_section, verse2_section, verse3_section = ir.sections
    assert verse_section.bars == verse2_section.bars == verse3_section.bars == 4
