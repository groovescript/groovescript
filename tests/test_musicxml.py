"""Tests for the MusicXML export module (groovescript.musicxml)."""

import re
import xml.etree.ElementTree as ET
from fractions import Fraction

import pytest

from groovescript.ast_nodes import Groove, Metadata, PatternLine, Section, Song, StarSpec
from groovescript.compiler import IRBar, IRGroove, IRSong, Event, compile_groove, compile_song
from groovescript.musicxml import (
    _DIVS_PER_BEAT,
    _bar_total_divs,
    _duration_attrs,
    _split_duration,
    emit_musicxml,
)
from groovescript.parser import parse


# ---------------------------------------------------------------------------
# Unit: _bar_total_divs
# ---------------------------------------------------------------------------

def test_bar_total_divs_4_4():
    assert _bar_total_divs("4/4") == 96  # 4 beats * 24 divs/beat


def test_bar_total_divs_6_8():
    assert _bar_total_divs("6/8") == 72  # 6 eighth-notes * 12 divs each


def test_bar_total_divs_3_4():
    assert _bar_total_divs("3/4") == 72


def test_bar_total_divs_12_8():
    assert _bar_total_divs("12/8") == 144


# ---------------------------------------------------------------------------
# Unit: _duration_attrs
# ---------------------------------------------------------------------------

def test_duration_attrs_quarter():
    t, dots, actual, normal = _duration_attrs(24)
    assert t == "quarter"
    assert dots == 0
    assert actual == normal == 1


def test_duration_attrs_eighth():
    t, dots, actual, normal = _duration_attrs(12)
    assert t == "eighth"
    assert dots == 0


def test_duration_attrs_16th():
    t, dots, actual, normal = _duration_attrs(6)
    assert t == "16th"
    assert dots == 0


def test_duration_attrs_dotted_quarter():
    t, dots, actual, normal = _duration_attrs(36)
    assert t == "quarter"
    assert dots == 1


def test_duration_attrs_triplet_eighth():
    t, dots, actual, normal = _duration_attrs(8)
    assert t == "eighth"
    assert actual == 3
    assert normal == 2


# ---------------------------------------------------------------------------
# Unit: _split_duration
# ---------------------------------------------------------------------------

def test_split_duration_quarter():
    assert _split_duration(24) == [24]


def test_split_duration_dotted_half():
    assert _split_duration(72) == [72]


def test_split_duration_sum_arbitrary():
    divs = 30  # quarter + 16th
    parts = _split_duration(divs)
    assert sum(parts) == divs


def test_split_duration_sum_always_correct():
    # All values must be representable by the duration table (minimum is 2 divs = triplet 32nd)
    for divs in [2, 3, 6, 8, 9, 12, 18, 24, 36, 48, 72, 96]:
        parts = _split_duration(divs)
        assert sum(parts) == divs, f"split_duration({divs}) = {parts} does not sum to {divs}"


# ---------------------------------------------------------------------------
# Helpers: parse XML output
# ---------------------------------------------------------------------------

def _parse_xml(data: bytes) -> ET.Element:
    text = data.decode("utf-8")
    # Remove XML declaration and multi-line DOCTYPE so ElementTree can parse
    # without resolving the external DTD.
    text = re.sub(r"<\?xml[^?]*\?>", "", text)
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text, flags=re.DOTALL)
    return ET.fromstring(text.strip())


def _measures(root: ET.Element) -> list[ET.Element]:
    return root.findall(".//measure")


def _notes_in(measure: ET.Element) -> list[ET.Element]:
    return measure.findall("note")


def _measure_duration(measure: ET.Element) -> int:
    """Sum of <duration> values for all non-chord notes in a measure."""
    total = 0
    for note in measure.findall("note"):
        if note.find("chord") is None:
            dur_el = note.find("duration")
            assert dur_el is not None
            total += int(dur_el.text)
    return total


# ---------------------------------------------------------------------------
# Integration: IRGroove (standalone)
# ---------------------------------------------------------------------------

def test_groove_produces_valid_xml_structure():
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    data = emit_musicxml(ir)
    root = _parse_xml(data)

    assert root.tag == "score-partwise"
    assert root.attrib["version"] == "4.0"
    assert root.find("part-list/score-part") is not None


def test_groove_measure_count():
    src = """\
groove "two bar":
    bar 1:
        BD: 1, 3
        SN: 2, 4
        HH: *8
    bar 2:
        BD: 1, 2&, 4
        SN: 2, 4
        HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    data = emit_musicxml(ir)
    root = _parse_xml(data)
    assert len(_measures(root)) == 2


def test_groove_measure_duration_sums_to_bar():
    """Regression: note + rest durations must exactly fill each measure."""
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    data = emit_musicxml(ir)
    root = _parse_xml(data)
    expected = _bar_total_divs("4/4")
    for measure in _measures(root):
        assert _measure_duration(measure) == expected


def test_groove_attributes_on_first_measure():
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    first = _measures(root)[0]
    attrs = first.find("attributes")
    assert attrs is not None
    assert attrs.findtext("divisions") == str(_DIVS_PER_BEAT)
    assert attrs.findtext("clef/sign") == "percussion"
    assert attrs.findtext("time/beats") == "4"
    assert attrs.findtext("time/beat-type") == "4"


def test_groove_tempo_direction():
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    first = _measures(root)[0]
    sound = first.find(".//sound")
    assert sound is not None
    assert sound.attrib.get("tempo") == "120"


def test_groove_notehead_types():
    """Hi-hat notes should have 'x' notehead; bass drum should have 'normal'."""
    src = """\
groove "beat":
    BD: 1
    HH: 1
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    noteheads = [n.findtext("notehead") for n in _measures(root)[0].findall("note")]
    assert "x" in noteheads
    assert "normal" in noteheads


# ---------------------------------------------------------------------------
# Integration: IRSong (full arrangement)
# ---------------------------------------------------------------------------

def test_song_measure_count_matches_bars():
    src = """\
metadata:
  title: "Test Song"
  tempo: 120
  time_signature: 4/4

groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 4
  groove: "beat"
"""
    song = parse(src)
    ir = compile_song(song)
    root = _parse_xml(emit_musicxml(ir))
    assert len(_measures(root)) == 4


def test_song_measure_durations_correct():
    """Every measure must sum to the bar's total divisions."""
    src = """\
metadata:
  title: "Test"
  tempo: 100
  time_signature: 4/4

groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "A":
  bars: 2
  groove: "beat"
"""
    song = parse(src)
    ir = compile_song(song)
    root = _parse_xml(emit_musicxml(ir))
    expected = _bar_total_divs("4/4")
    for measure in _measures(root):
        assert _measure_duration(measure) == expected


def test_song_title_in_work():
    src = """\
metadata:
  title: "My Drum Score"
  tempo: 120
  time_signature: 4/4

groove "beat":
    SN: 2, 4
    HH: *8

section "A":
  bars: 1
  groove: "beat"
"""
    song = parse(src)
    ir = compile_song(song)
    root = _parse_xml(emit_musicxml(ir))
    assert root.findtext("work/work-title") == "My Drum Score"


def test_song_section_name_as_rehearsal_mark():
    src = """\
metadata:
  title: "T"
  tempo: 120
  time_signature: 4/4

groove "beat":
    SN: 2, 4
    HH: *8

section "Verse":
  bars: 2
  groove: "beat"
"""
    song = parse(src)
    ir = compile_song(song)
    root = _parse_xml(emit_musicxml(ir))
    first_measure = _measures(root)[0]
    rehearsal = first_measure.find(".//rehearsal")
    assert rehearsal is not None
    assert rehearsal.text == "Verse"


def test_song_tempo_change_emits_new_direction():
    src = """\
metadata:
  title: "T"
  tempo: 100
  time_signature: 4/4

groove "beat":
    SN: 2, 4
    HH: *8

section "A":
  bars: 2
  groove: "beat"

section "B":
  bars: 2
  groove: "beat"
  tempo: 140
"""
    song = parse(src)
    ir = compile_song(song)
    root = _parse_xml(emit_musicxml(ir))
    # Measure 3 (first bar of section B) should have a tempo direction
    measures = _measures(root)
    tempo_120 = measures[0].find(".//sound[@tempo='100']")
    assert tempo_120 is not None
    tempo_140 = measures[2].find(".//sound[@tempo='140']")
    assert tempo_140 is not None


def test_song_time_signature_change():
    src = """\
metadata:
  title: "T"
  tempo: 120
  time_signature: 4/4

groove "waltz":
    SN: 2, 3
    HH: *8

section "A":
  bars: 1
  groove: "waltz"
  time_signature: 3/4
"""
    song = parse(src)
    ir = compile_song(song)
    root = _parse_xml(emit_musicxml(ir))
    measures = _measures(root)
    # 3/4 bar has 72 divisions
    assert _measure_duration(measures[0]) == _bar_total_divs("3/4")
    time_el = measures[0].find(".//time")
    assert time_el is not None
    assert time_el.findtext("beats") == "3"


def test_rest_bar_emits_measure_rest():
    """A bar marked is_rest should produce a whole-bar rest."""
    src = """\
title: "T"
tempo: 120
time_signature: 4/4

groove "beat":
    SN: 2, 4
    HH: *8

section "verse":
  play:
    groove "beat" x2
    rest x1
"""
    song = parse(src)
    ir = compile_song(song)
    root = _parse_xml(emit_musicxml(ir))
    rest_measures = [
        m for m in _measures(root)
        if m.find(".//rest[@measure='yes']") is not None
    ]
    assert len(rest_measures) > 0


# ---------------------------------------------------------------------------
# XML structure checks
# ---------------------------------------------------------------------------

def test_output_starts_with_xml_declaration():
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    data = emit_musicxml(ir)
    assert data.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')


def test_output_contains_doctype():
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    data = emit_musicxml(ir)
    assert b"DOCTYPE score-partwise" in data


def test_simultaneous_hits_use_chord_element():
    """BD and HH on the same beat must use <chord/> for the second note."""
    src = """\
groove "beat":
    BD: 1
    HH: 1
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    notes = _measures(root)[0].findall("note")
    chord_notes = [n for n in notes if n.find("chord") is not None]
    assert len(chord_notes) >= 1


def test_triplet_notes_have_time_modification():
    """Triplet 8th notes (8 divs) must carry a <time-modification> element."""
    src = """\
groove "triplet":
    SN: 1t, 1trip, 1l
    HH: *8t
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    all_notes = [n for m in _measures(root) for n in m.findall("note")]
    triplet_notes = [n for n in all_notes if n.find("time-modification") is not None]
    assert len(triplet_notes) > 0


def test_accent_modifier_adds_articulation():
    src = """\
groove "beat":
    SN: 2 accent
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    accent_notes = [
        n for m in _measures(root)
        for n in m.findall("note")
        if n.find(".//accent") is not None
    ]
    assert len(accent_notes) == 1


def test_ghost_modifier_adds_soft_accent():
    src = """\
groove "beat":
    SN: 2 ghost
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    ghost_notes = [
        n for m in _measures(root)
        for n in m.findall("note")
        if n.find(".//soft-accent") is not None
    ]
    assert len(ghost_notes) == 1


def test_6_8_measure_duration():
    src = """\
groove "compound":
    SN: 1, 4
    HH: *8
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    # Override time signature via arrangement
    src2 = """\
metadata:
  title: "T"
  tempo: 120
  time_signature: 6/8

groove "compound":
    SN: 1, 4
    HH: *8

section "A":
  bars: 1
  groove: "compound"
"""
    song2 = parse(src2)
    ir2 = compile_song(song2)
    root = _parse_xml(emit_musicxml(ir2))
    assert _measure_duration(_measures(root)[0]) == _bar_total_divs("6/8")
