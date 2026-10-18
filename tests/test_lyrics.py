"""Timed lyrics: parsing, validation, inheritance, IR, and every emitter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest

from groovescript.cli import _run_compile, _run_musicxml
from groovescript.compiler import LyricSyllable, compile_song
from groovescript.errors import GrooveScriptError
from groovescript.lilypond import emit_lilypond
from groovescript.lint import check_style
from groovescript.midi import emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"

_GROOVE = (
    'groove "g":\n'
    "  BD: 1 3\n"
    "  SN: 2 4\n"
    "  HH: *8\n"
)


def _song(body: str, metadata: str = "") -> str:
    return metadata + _GROOVE + body


def _compile(src: str):
    return compile_song(parse(src))


def _texts(bar) -> list[str]:
    return [syl.text for syl in bar.lyrics]


# ── Parsing ───────────────────────────────────────────────────────────────


def test_parse_lyrics_block_pairs_count_with_words():
    song = parse(_song(
        'section "v":\n'
        "  bars: 2\n"
        '  groove: "g"\n'
        "  lyrics:\n"
        '    bar 1: "1 2& 3 4&"  "When the mor- ning"\n'
        '    bar 2: "1"          "oh~yeah"\n'
    ))
    entries = song.sections[0].lyrics
    assert [e.bar for e in entries] == [1, 2]
    assert entries[0].labels == ["1", "2&", "3", "4&"]
    assert [(t.text, t.hyphen_after) for t in entries[0].syllables] == [
        ("When", False), ("the", False), ("mor", True), ("ning", False),
    ]
    # ``~`` joins words on one onset.
    assert entries[1].syllables[0].text == "oh yeah"


def test_parse_lyrics_style_metadata():
    song = parse(_song(
        'section "v":\n  bars: 1\n  groove: "g"\n',
        metadata="metadata:\n  lyrics_style: line\n",
    ))
    assert song.metadata.lyrics_style == "line"


def test_parse_lyrics_count_words_mismatch_reports_both_counts():
    with pytest.raises(GrooveScriptError) as exc:
        parse(_song(
            'section "v":\n'
            "  bars: 1\n"
            '  groove: "g"\n'
            "  lyrics:\n"
            '    bar 1: "1 2 3" "two words"\n'
        ))
    msg = str(exc.value)
    assert "count has 3 onset(s) but words has 2 syllable(s)" in msg
    assert "this onset has no matching syllable" in msg
    assert exc.value.line == 9


def test_parse_lyrics_underscore_is_reserved():
    with pytest.raises(GrooveScriptError, match="reserved for future use"):
        parse(_song(
            'section "v":\n'
            "  bars: 1\n"
            '  groove: "g"\n'
            "  lyrics:\n"
            '    bar 1: "1 3" "hold_ it"\n'
        ))


def test_parse_lyrics_duplicate_bar_rejected():
    with pytest.raises(GrooveScriptError, match="bar 1 are given more than once"):
        parse(_song(
            'section "v":\n'
            "  bars: 2\n"
            '  groove: "g"\n'
            "  lyrics:\n"
            '    bar 1: "1" "a"\n'
            '    bar 1: "3" "b"\n'
        ))


def test_parse_like_with_lyrics_category_then_lyrics_block():
    """``like "x" with lyrics`` must not swallow the next line's ``lyrics:``
    header (and vice versa) even though both use the same word."""
    song = parse(_song(
        'section "a":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
        'section "b":\n'
        '  like "a" with fills, lyrics\n'
        "  lyrics:\n"
        '    bar 1: "1" "x"\n'
    ))
    b = song.sections[1]
    assert b.inherit.categories == frozenset({"fills", "lyrics"})
    assert [e.bar for e in b.lyrics] == [1]


# ── Compilation / validation ──────────────────────────────────────────────


def test_compile_lyrics_resolve_to_bar_positions():
    ir = _compile(_song(
        'section "v":\n'
        "  bars: 2\n"
        '  groove: "g"\n'
        "  lyrics:\n"
        '    bar 2: "1 2& 4{triplet 1, 3}" "a b c d"\n'
    ))
    assert ir.bars[0].lyrics == []
    assert [s.position for s in ir.bars[1].lyrics] == [
        Fraction(0), Fraction(3, 8), Fraction(3, 4), Fraction(3, 4) + Fraction(2, 12),
    ]
    assert ir.has_lyrics


def test_compile_lyrics_do_not_change_drum_subdivision():
    """Lyric onsets must not affect the drum bar's inferred grid."""
    plain = _compile(_song('section "v":\n  bars: 1\n  groove: "g"\n'))
    with_lyrics = _compile(_song(
        'section "v":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
        "  lyrics:\n"
        '    bar 1: "1e 2{sextuplet 2}" "a b"\n'
    ))
    assert with_lyrics.bars[0].subdivision == plain.bars[0].subdivision
    assert with_lyrics.bars[0].beat_tuplets == plain.bars[0].beat_tuplets


@pytest.mark.parametrize(
    "lyrics, message",
    [
        ('    bar 1: "5" "x"\n', "out of range"),
        ('    bar 1: "1 1" "x y"\n', "two syllables on beat 1"),
        ('    bar 3: "1" "x"\n', "lyrics for bar 3 but the section has only 2 bars"),
    ],
)
def test_compile_lyrics_validation_errors(lyrics, message):
    with pytest.raises(GrooveScriptError, match=message) as exc:
        _compile(_song(
            'section "v":\n'
            "  bars: 2\n"
            '  groove: "g"\n'
            "  lyrics:\n" + lyrics
        ))
    assert exc.value.line == 9


def test_compile_lyrics_bar_beyond_play_block_length():
    with pytest.raises(GrooveScriptError, match="only 3 bars"):
        _compile(_song(
            'section "v":\n'
            "  play:\n"
            '    groove "g" x2\n'
            "    rest\n"
            "  lyrics:\n"
            '    bar 4: "1" "x"\n'
        ))


def test_compile_lyrics_meter_follows_target_bar():
    """A beat label is checked against the bar's own meter, including a
    meter-variation bar."""
    src = _song(
        'section "v":\n'
        "  bars: 2\n"
        '  groove: "g"\n'
        "  variation at bar 2:\n"
        "    time_signature: 3/4\n"
        "  lyrics:\n"
        '    bar 2: "3&" "x"\n'
    )
    ir = _compile(src)
    assert ir.bars[1].lyrics[0].position == Fraction(5, 6)
    with pytest.raises(GrooveScriptError, match="out of range"):
        _compile(src.replace('"3&"', '"4"'))


def test_compile_lyrics_pickup_lands_in_previous_section_last_bar():
    ir = _compile(_song(
        'section "a":\n'
        "  bars: 2\n"
        '  groove: "g"\n'
        'section "b":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
        "  lyrics:\n"
        '    bar 0: "4&" "and"\n'
        '    bar 1: "1" "go"\n'
    ))
    assert ir.bars[1].lyrics == [LyricSyllable(Fraction(7, 8), "and", False)]
    assert _texts(ir.bars[2]) == ["go"]


def test_compile_lyrics_pickup_on_first_section_rejected():
    with pytest.raises(GrooveScriptError, match="first section"):
        _compile(_song(
            'section "a":\n'
            "  bars: 1\n"
            '  groove: "g"\n'
            "  lyrics:\n"
            '    bar 0: "4&" "and"\n'
        ))


def test_compile_lyrics_pickup_collision_rejected():
    with pytest.raises(GrooveScriptError, match="collides with the previous section"):
        _compile(_song(
            'section "a":\n'
            "  bars: 1\n"
            '  groove: "g"\n'
            "  lyrics:\n"
            '    bar 1: "4&" "x"\n'
            'section "b":\n'
            "  bars: 1\n"
            '  groove: "g"\n'
            "  lyrics:\n"
            '    bar 0: "4&" "y"\n'
        ))


def test_compile_lyrics_on_placeholder_groove_allowed():
    ir = _compile(_song(
        'section "v":\n'
        "  bars: 1\n"
        "  groove: placeholder\n"
        "  lyrics:\n"
        '    bar 1: "1" "tbd"\n'
    ))
    assert ir.bars[0].is_placeholder_groove
    assert _texts(ir.bars[0]) == ["tbd"]


_INHERIT_BASE = (
    'section "verse":\n'
    "  bars: 2\n"
    '  groove: "g"\n'
    "  lyrics:\n"
    '    bar 1: "1" "first"\n'
    '    bar 2: "1" "second"\n'
)


def test_like_without_lyrics_category_does_not_copy_lyrics():
    ir = _compile(_song(_INHERIT_BASE + 'section "again":\n  like "verse"\n'))
    assert ir.bars[2].lyrics == [] and ir.bars[3].lyrics == []


def test_like_with_lyrics_overrides_per_bar():
    """The inheritor's ``bar N:`` replaces the parent's entry for that bar;
    the parent's other bars are kept (no duplicate-onset error)."""
    ir = _compile(_song(
        _INHERIT_BASE
        + 'section "again":\n'
        '  like "verse" with lyrics\n'
        "  lyrics:\n"
        '    bar 2: "1" "new"\n'
    ))
    assert _texts(ir.bars[2]) == ["first"]
    assert _texts(ir.bars[3]) == ["new"]


# ── LilyPond ──────────────────────────────────────────────────────────────


_TWO_BAR_SRC = _song(
    'section "v":\n'
    "  bars: 4\n"
    '  groove: "g"\n'
    "  lyrics:\n"
    '    bar 1: "1 2& 3" "hel- lo there"\n'
)


def test_lilypond_without_lyrics_is_unchanged_by_template_placeholders():
    ly = emit_lilypond(_compile(_song('section "v":\n  bars: 1\n  groove: "g"\n')))
    assert "{{" not in ly
    assert "Lyrics" not in ly and "<<\n" not in ly


def test_lilypond_placeholder_text_in_lyrics_is_not_substituted():
    """Regression: template placeholders are filled in one pass, so a
    syllable that looks like ``{{BODY}}`` is engraved literally instead of
    pulling the drum body into the lyrics."""
    ly = emit_lilypond(_compile(_song(
        'section "v":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
        "  lyrics:\n"
        '    bar 1: "1" "{{BODY}}"\n'
    )))
    assert '"{{BODY}}"' in ly
    assert ly.count("\\drummode") == 1


def test_lilypond_staff_style_is_default():
    ly = emit_lilypond(_compile(_TWO_BAR_SRC))
    assert "\\new RhythmicStaff" in ly
    assert "\\RemoveAllEmptyStaves" in ly
    assert 'instrumentName = "Vox"' in ly
    # Implied durations: 1 → 2& (dotted quarter), 2& → 3 (eighth), 3 → bar end.
    assert "c4. c8 c2 |" in ly
    assert '"hel" -- "lo" "there"' in ly


def test_lilypond_line_style_uses_null_voice():
    ly = emit_lilypond(_compile(_TWO_BAR_SRC), lyrics_style="line")
    assert "\\new NullVoice" in ly
    assert "\\new RhythmicStaff" not in ly
    assert "s4*4 |" in ly  # bars without lyrics are skips


def test_lilypond_cli_style_overrides_metadata():
    src = "metadata:\n  lyrics_style: line\n" + _TWO_BAR_SRC
    assert "\\new NullVoice" in emit_lilypond(_compile(src))
    assert "\\new RhythmicStaff" in emit_lilypond(_compile(src), lyrics_style="staff")


def test_lilypond_lyrics_off_prints_drums_only():
    plain = emit_lilypond(_compile(_song('section "v":\n  bars: 4\n  groove: "g"\n')))
    off = emit_lilypond(_compile(_TWO_BAR_SRC), lyrics_style="off")
    assert "Lyrics" not in off
    # Lyric bars still never compact, so only the lyric-free bars group.
    assert off != plain


def test_lilypond_lyric_bars_never_compact():
    ly = emit_lilypond(_compile(_TWO_BAR_SRC))
    # Bar 1 carries lyrics; only bars 2-4 fold into a repeat.
    assert "\\repeat volta 3" in ly
    assert "\\repeat volta 4" not in ly


def test_lilypond_rest_before_first_onset_and_tuplet_beat():
    ly = emit_lilypond(_compile(_song(
        'section "v":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
        "  lyrics:\n"
        '    bar 1: "2 3trip 4" "a b c"\n'
    )))
    # "a" on 2 holds into the first triplet eighth of beat 3.
    assert "r4 c4~ \\tuplet 3/2 { c8 c4 } c4 |" in ly


def test_lilypond_repeat_section_with_lyrics_written_out():
    """Regression: a ``repeat:`` section whose passes carry lyrics must be
    written out in full, without a misleading "Play Nx" label, and the
    second pass must not re-enter the repeat path."""
    ly = emit_lilypond(_compile(_song(
        'section "v":\n'
        "  bars: 4\n"
        '  groove: "g"\n'
        "  repeat: 2\n"
        "  lyrics:\n"
        '    bar 1: "1" "x"\n'
        'section "w":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
    )))
    drum = ly.split("\\drummode", 1)[1]
    assert "Play 2x" not in drum
    assert "\\repeat volta 2" not in drum
    # Bars 2-4 of the written-out section still compact among themselves.
    assert "\\repeat volta 3" in drum


def test_lilypond_vocal_measures_follow_printed_drum_bars():
    """The vocal rhythm has one measure per printed drum bar, so repeats and
    multi-bar rests keep the two staves aligned."""
    ly = emit_lilypond(_compile(_song(
        'section "v":\n'
        "  play:\n"
        '    groove "g" x4\n'
        "    rest x3\n"
        "    bar \"b\":\n"
        "      SN: 1\n"
        "  lyrics:\n"
        '    bar 8: "1" "hey"\n'
    )))
    vocal = ly.split('\\new Voice = "lyricsrhythm"', 1)[1].split("\\new Lyrics", 1)[0]
    assert vocal.count("|") == 3
    assert "R1 |" in vocal and "R1*3 |" in vocal and "c1 |" in vocal


# ── MIDI / MusicXML / lint / CLI ──────────────────────────────────────────


def test_midi_lyric_meta_events_on_dedicated_track():
    data = emit_midi(_compile(_TWO_BAR_SRC))
    assert data[10:12] == b"\x00\x03"  # three tracks
    assert b"\xff\x03\x06Lyrics" in data
    assert b"\xff\x05\x04hel-" in data  # trailing hyphen kept (karaoke style)
    assert b"\xff\x05\x05there" in data


def test_midi_without_lyrics_has_two_tracks():
    data = emit_midi(_compile(_song('section "v":\n  bars: 1\n  groove: "g"\n')))
    assert data[10:12] == b"\x00\x02"


def test_musicxml_voice_part_with_syllabic():
    raw = emit_musicxml(_compile(_TWO_BAR_SRC))
    root = ET.fromstring(raw.split(b"\n", 4)[4])
    assert [p.get("id") for p in root.findall("part")] == ["P1", "P2"]
    voice = root.find("part[@id='P2']")
    lyrics = [
        (l.find("syllabic").text, l.find("text").text) for l in voice.iter("lyric")
    ]
    assert lyrics == [("begin", "hel"), ("end", "lo"), ("single", "there")]
    for measure in voice.findall("measure"):
        total = sum(int(n.find("duration").text) for n in measure.findall("note"))
        assert total == 4 * 2520


def test_musicxml_lyrics_can_be_suppressed():
    raw = emit_musicxml(_compile(_TWO_BAR_SRC), include_lyrics=False)
    assert b'id="P2"' not in raw


def test_lint_style_lyrics_warnings():
    src = _song(
        'section "v":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
        '  cue "a" at bar 1 beat 1\n'
        '  cue "b" at bar 1 beat 2\n'
        '  cue "c" at bar 1 beat 3\n'
        '  cue "d" at bar 1 beat 4\n'
        "  lyrics:\n"
        '    bar 1: "1" "wor-"\n'
    )
    messages = [w.message for w in check_style(src, parse(src))]
    assert any("ends with a hyphen" in m for m in messages)
    assert any("4 cues placed on beats" in m for m in messages)


def test_cli_compile_lyrics_style_flag(tmp_path: Path):
    src = tmp_path / "s.gs"
    src.write_text(_TWO_BAR_SRC)
    out = tmp_path / "s.ly"
    assert _run_compile(str(src), str(out), lyrics_style="line") == 0
    assert "\\new NullVoice" in out.read_text()
    assert _run_compile(str(src), str(out), lyrics_style="off") == 0
    assert "Lyrics" not in out.read_text()


def test_cli_musicxml_lyrics_off(tmp_path: Path):
    src = tmp_path / "s.gs"
    src.write_text(_TWO_BAR_SRC)
    out = tmp_path / "s.xml"
    assert _run_musicxml(str(src), str(out), lyrics_style="off") == 0
    assert b'id="P2"' not in out.read_bytes()


@pytest.mark.parametrize("name", ["lyrics_basic", "lyrics_staff"])
def test_lyrics_fixtures_match_committed_ly(name):
    ir = compile_song(parse_file(str(FIXTURES / f"{name}.gs")))
    assert emit_lilypond(ir) == (FIXTURES / f"{name}.ly").read_text()
