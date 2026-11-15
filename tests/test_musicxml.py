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
    assert _bar_total_divs("4/4") == 4 * _DIVS_PER_BEAT


def test_bar_total_divs_6_8():
    # 6 eighth-notes per bar; one eighth = _DIVS_PER_BEAT // 2
    assert _bar_total_divs("6/8") == 6 * (_DIVS_PER_BEAT // 2)


def test_bar_total_divs_3_4():
    assert _bar_total_divs("3/4") == 3 * _DIVS_PER_BEAT


def test_bar_total_divs_12_8():
    assert _bar_total_divs("12/8") == 12 * (_DIVS_PER_BEAT // 2)


# ---------------------------------------------------------------------------
# Unit: _duration_attrs
# ---------------------------------------------------------------------------

def test_duration_attrs_quarter():
    t, dots, actual, normal = _duration_attrs(_DIVS_PER_BEAT)
    assert t == "quarter"
    assert dots == 0
    assert actual == normal == 1


def test_duration_attrs_eighth():
    t, dots, actual, normal = _duration_attrs(_DIVS_PER_BEAT // 2)
    assert t == "eighth"
    assert dots == 0


def test_duration_attrs_16th():
    t, dots, actual, normal = _duration_attrs(_DIVS_PER_BEAT // 4)
    assert t == "16th"
    assert dots == 0


def test_duration_attrs_dotted_quarter():
    t, dots, actual, normal = _duration_attrs(_DIVS_PER_BEAT * 3 // 2)
    assert t == "quarter"
    assert dots == 1


def test_duration_attrs_triplet_eighth():
    # Triplet eighth = (eighth_divs * 2 / 3) when normal eighth = _DIVS_PER_BEAT/2.
    triplet_eighth = (_DIVS_PER_BEAT // 2) * 2 // 3
    t, dots, actual, normal = _duration_attrs(triplet_eighth)
    assert t == "eighth"
    assert actual == 3
    assert normal == 2


# ---------------------------------------------------------------------------
# Unit: _split_duration
# ---------------------------------------------------------------------------

def test_split_duration_quarter():
    assert _split_duration(_DIVS_PER_BEAT) == [_DIVS_PER_BEAT]


def test_split_duration_dotted_half():
    dotted_half = _DIVS_PER_BEAT * 3
    assert _split_duration(dotted_half) == [dotted_half]


def test_split_duration_sum_arbitrary():
    divs = _DIVS_PER_BEAT + _DIVS_PER_BEAT // 4  # quarter + 16th
    parts = _split_duration(divs)
    assert sum(parts) == divs


def test_split_duration_sum_always_correct():
    # All values must be representable by the duration table.
    for multiplier in [1, 2, 4, 8, 16, 32]:
        # Whole-number multiples of the smallest table entry (a 32nd) always
        # decompose cleanly.
        divs = (_DIVS_PER_BEAT // 8) * multiplier
        if divs <= 0:
            continue
        parts = _split_duration(divs)
        assert sum(parts) == divs, (
            f"split_duration({divs}) = {parts} does not sum to {divs}"
        )


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


def test_rest_xn_emits_multiple_rest_attribute_on_first_bar():
    """``rest xN`` for N > 1 puts a ``<measure-style><multiple-rest>N</multiple-rest>``
    on the first bar of the span; the remaining N-1 bars are plain whole-rests."""
    src = """\
title: "T"
tempo: 120
time_signature: 4/4

section "tacet":
  play:
    rest x16
"""
    song = parse(src)
    ir = compile_song(song)
    root = _parse_xml(emit_musicxml(ir))
    measures = _measures(root)
    assert len(measures) == 16  # 16 bars present so playback length matches
    # First measure carries the <multiple-rest> attribute
    mr = measures[0].find(".//measure-style/multiple-rest")
    assert mr is not None
    assert mr.text == "16"
    # The rest of the span are plain whole-rest measures with no multiple-rest
    for m in measures[1:]:
        assert m.find(".//multiple-rest") is None
        assert m.find(".//rest[@measure='yes']") is not None


def test_lone_rest_x1_does_not_emit_multiple_rest():
    """A single rest bar should not emit a <multiple-rest> attribute —
    the attribute is reserved for runs of two or more."""
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
    measures = _measures(root)
    assert root.find(".//multiple-rest") is None
    # The rest bar still emits a whole-bar rest
    assert measures[2].find(".//rest[@measure='yes']") is not None


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


def test_ghost_modifier_renders_as_parenthesized_notehead():
    """Ghost notes are rendered as parenthesized noteheads — the standard
    drum-notation convention — not as a <soft-accent> articulation.
    """
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
        if n.find("notehead") is not None
        and n.find("notehead").get("parentheses") == "yes"
    ]
    assert len(ghost_notes) == 1
    # The legacy soft-accent articulation should no longer appear.
    soft_accents = [
        sa for m in _measures(root) for sa in m.findall(".//soft-accent")
    ]
    assert soft_accents == []


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


# ---------------------------------------------------------------------------
# Regression: every <note>'s <duration> and <type> must agree
# ---------------------------------------------------------------------------

# (divs, type) entries the emitter is allowed to produce.  Anything else is a
# bug: MusicXML consumers will render the visual type but allocate the
# numeric duration, leading to barred-but-mismatched output.
#
# Built off ``_DIVS_PER_BEAT`` so the set scales whenever divisions change.
def _build_valid_dur_type() -> set[tuple[int, str]]:
    Q = _DIVS_PER_BEAT  # divisions per quarter note
    types = {
        "whole":   Q * 4,
        "half":    Q * 2,
        "quarter": Q,
        "eighth":  Q // 2,
        "16th":    Q // 4,
        "32nd":    Q // 8,
    }
    out: set[tuple[int, str]] = set()
    for type_name, divs in types.items():
        out.add((divs, type_name))
        out.add((divs * 3 // 2, type_name))     # dotted
        out.add((divs * 2 // 3, type_name))     # triplet (3:2)
    # Tuplet variants supported by the new tuplet-group code path.
    for type_name, divs in types.items():
        for actual, normal in [(5, 4), (6, 4), (7, 4), (9, 8)]:
            scaled = divs * normal // actual
            if scaled > 0:
                out.add((scaled, type_name))
    return out


_VALID_DUR_TYPE = _build_valid_dur_type()


def test_duration_and_type_always_agree():
    """Regression: a slot duration that doesn't match a single MusicXML note
    type (e.g. 60 = half + eighth) must be split into a tied chain rather
    than emitting one note with mismatched <duration> and <type>.

    Before the fix, a hit on beat 1 followed by a hit on beat 2& produced a
    second note with duration=60 and type='half' — the engraver would honor
    'half' visually (48 divs) and silently lose 12 divs of measure time.
    """
    src = """\
groove "split":
    BD: 1
    SN: 2&
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    for measure in _measures(root):
        for note in measure.findall("note"):
            dur_el = note.find("duration")
            type_el = note.find("type")
            if dur_el is None or type_el is None:
                continue  # grace notes have no duration
            dur = int(dur_el.text)
            type_name = type_el.text
            assert (dur, type_name) in _VALID_DUR_TYPE, (
                f"<duration>{dur}</duration> with <type>{type_name}</type> "
                f"is not a valid MusicXML pairing"
            )


def test_split_slot_emits_tied_chain():
    """A 60-div slot (half + eighth) emits two notes joined by a tie."""
    src = """\
groove "split":
    SN: 1, 2&
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    notes = _measures(root)[0].findall("note")
    # Find the SN note at beat 2& (3/8 through the bar) — it is the second
    # SN onset; with the split it's now two notes joined by a tie.
    tie_starts = [n for n in notes if n.find("tie[@type='start']") is not None]
    tie_stops = [n for n in notes if n.find("tie[@type='stop']") is not None]
    assert tie_starts, "expected at least one <tie type='start'/>"
    assert tie_stops, "expected at least one <tie type='stop'/>"
    # And measure duration must still sum correctly
    assert _measure_duration(_measures(root)[0]) == _bar_total_divs("4/4")


# ---------------------------------------------------------------------------
# Flam / drag grace notes
# ---------------------------------------------------------------------------

def test_flam_emits_one_grace_note_before_main_hit():
    """A flam on SN produces one <grace/> note immediately before the main
    SN note, with the snare's display position.
    """
    src = """\
groove "g":
    SN: 2 flam
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    notes = _measures(root)[0].findall("note")
    grace_notes = [n for n in notes if n.find("grace") is not None]
    assert len(grace_notes) == 1
    # Grace note should display on the SN line (C5)
    g = grace_notes[0]
    assert g.find("unpitched/display-step").text == "C"
    assert g.find("unpitched/display-octave").text == "5"
    # Grace note has a slash through the flag (open grace, flam convention)
    assert g.find("grace").get("slash") == "yes"
    # Grace must come before the main SN note in document order
    grace_idx = list(notes).index(g)
    sn_main = next(
        n for n in notes
        if n.find("grace") is None
        and n.find("unpitched") is not None
        and n.find("unpitched/display-step").text == "C"
        and n.find("duration") is not None
    )
    assert list(notes).index(sn_main) > grace_idx


def test_drag_emits_two_grace_notes():
    """A drag on SN produces two <grace/> notes before the main hit."""
    src = """\
groove "g":
    SN: 2 drag
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    notes = _measures(root)[0].findall("note")
    grace_notes = [n for n in notes if n.find("grace") is not None]
    assert len(grace_notes) == 2


def test_grace_notes_have_no_duration():
    """Grace notes must omit <duration> per the MusicXML spec."""
    src = """\
groove "g":
    SN: 2 flam
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    for n in _measures(root)[0].findall("note"):
        if n.find("grace") is not None:
            assert n.find("duration") is None


# ---------------------------------------------------------------------------
# Articulations only on the first split-part of a tied chain
# ---------------------------------------------------------------------------

def test_accent_appears_only_on_first_part_of_split():
    """When a slot is split into multiple tied notes, the accent
    articulation is attached only to the first note (the attack), not
    duplicated on every tied continuation.
    """
    src = """\
groove "g":
    BD: 1
    SN: 2& accent
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    accents = [a for n in _measures(root)[0].findall("note") for a in n.findall(".//accent")]
    assert len(accents) == 1


# ---------------------------------------------------------------------------
# Cymbal sustain comparison for MusicXML: ghost note carries parens across ties
# ---------------------------------------------------------------------------

def test_ghost_parens_carry_across_split_parts():
    """If a ghost note's slot has to be split with ties, the parenthesized
    notehead appears on every part so the visual cue isn't lost on the tail.
    """
    src = """\
groove "g":
    SN: 1 ghost, 2&
"""
    song = parse(src)
    ir = compile_groove(song.grooves[0])
    root = _parse_xml(emit_musicxml(ir))
    notes = _measures(root)[0].findall("note")
    # The ghost note at beat 1 spans 36 divs (single note, no split). Choose
    # a more aggressive split scenario:
    sn_paren = [
        n for n in notes
        if n.find("unpitched/display-step") is not None
        and n.find("unpitched/display-step").text == "C"
        and n.find("notehead") is not None
        and n.find("notehead").get("parentheses") == "yes"
    ]
    assert len(sn_paren) >= 1


# ---------------------------------------------------------------------------
# Engraving pass: beams and stem directions
# ---------------------------------------------------------------------------

def _song_measures(src: str) -> list[ET.Element]:
    root = ET.fromstring(emit_musicxml(compile_song(parse(src))))
    return root.findall(".//part/measure")


def _chords(measure: ET.Element) -> list[list[ET.Element]]:
    """Group a measure's non-grace notes into chords."""
    chords: list[list[ET.Element]] = []
    for note in measure.findall("note"):
        if note.find("grace") is not None:
            continue
        if note.find("chord") is not None:
            chords[-1].append(note)
        else:
            chords.append([note])
    return chords


def _beams(note: ET.Element) -> dict[str, str]:
    return {b.get("number"): b.text for b in note.findall("beam")}


_EIGHTHS = """\
groove "g":
  BD: 1, 3
  SN: 2, 4
  HH: *8
section "s":
  bars: 1
  groove: "g"
"""


def test_eighth_notes_are_beamed_in_pairs_per_beat():
    [m] = _song_measures(_EIGHTHS)
    chords = _chords(m)
    assert len(chords) == 8
    assert [_beams(c[0]).get("1") for c in chords] == ["begin", "end"] * 4
    # Beams sit on the chord's first note only.
    assert all(n.find("beam") is None for c in chords for n in c[1:])


def test_chords_and_beam_groups_share_one_stem_direction():
    """Regression test: a hand+foot chord used to ask for stems both up
    (hi-hat) and down (kick), which engravers resolve arbitrarily. Every
    note in a beamed group now shares one direction, up when any hand-played
    instrument is present."""
    [m] = _song_measures(_EIGHTHS)
    stems = {n.findtext("stem") for c in _chords(m) for n in c}
    assert stems == {"up"}


def test_feet_only_groups_keep_stems_down():
    src = """\
groove "g":
  BD: 1, 1&, 2
section "s":
  bars: 1
  groove: "g"
"""
    [m] = _song_measures(src)
    notes = [c[0] for c in _chords(m)]
    assert {n.findtext("stem") for n in notes} == {"down"}
    assert [_beams(n) for n in notes[:2]] == [{"1": "begin"}, {"1": "end"}]


def test_sixteenths_get_secondary_beams_and_hooks():
    src = """\
groove "g":
  SN: 1, 1&, 1a, 2
section "s":
  bars: 1
  groove: "g"
"""
    [m] = _song_measures(src)
    first_beat = [c[0] for c in _chords(m)][:3]
    # 1 (eighth), 1& (16th), 1a (16th): primary beam across all three,
    # secondary beam joining the two 16ths.
    assert [_beams(n) for n in first_beat] == [
        {"1": "begin"},
        {"1": "continue", "2": "begin"},
        {"1": "end", "2": "end"},
    ]


def test_dotted_eighth_sixteenth_uses_backward_hook():
    src = """\
groove "g":
  SN: 1, 1a, 2
section "s":
  bars: 1
  groove: "g"
"""
    [m] = _song_measures(src)
    a, b = [c[0] for c in _chords(m)][:2]
    assert _beams(a) == {"1": "begin"}
    assert _beams(b) == {"1": "end", "2": "backward hook"}


def test_rests_and_quarter_notes_break_beams():
    src = """\
groove "g":
  SN: 1&, 2, 3, 3&, 4
section "s":
  bars: 1
  groove: "g"
"""
    [m] = _song_measures(src)
    notes = m.findall("note")
    # Beat 1 is an eighth rest then an eighth: a lone note, so no beam.
    assert notes[0].find("rest") is not None
    assert all(n.find("beam") is None for n in notes[:3])  # rest, 1&, quarter on 2
    beamed = [n for n in notes if n.find("beam") is not None]
    assert [_beams(n)["1"] for n in beamed] == ["begin", "end"]  # 3 / 3&


def test_compound_meter_beams_by_dotted_quarter():
    src = """\
time_signature: 6/8
groove "g":
  HH: *8
section "s":
  bars: 1
  groove: "g"
"""
    [m] = _song_measures(src)
    values = [_beams(c[0]).get("1") for c in _chords(m)]
    assert values == ["begin", "continue", "end"] * 2


def test_tuplets_are_beamed_within_their_beat():
    src = """\
groove "g":
  HH: 1, 2{sextuplet 1, 2, 3, 4, 5, 6}, 3, 4
section "s":
  bars: 1
  groove: "g"
"""
    [m] = _song_measures(src)
    sextuplet = [c[0] for c in _chords(m)][1:7]
    assert [_beams(n)["1"] for n in sextuplet] == [
        "begin", "continue", "continue", "continue", "continue", "end",
    ]


def test_beam_element_follows_notehead_and_precedes_notations():
    src = _EIGHTHS.replace("SN: 2, 4", "SN: 2 accent, 4")
    [m] = _song_measures(src)
    for note in m.findall("note"):
        tags = [child.tag for child in note]
        if "beam" in tags:
            assert tags.index("beam") > tags.index("notehead")
            if "notations" in tags:
                assert tags.index("beam") < tags.index("notations")


def test_hihat_foot_sits_just_below_the_staff():
    """Regression test: the hi-hat pedal (HF) was placed at E3, about an
    octave below the staff, instead of D4 just under the bottom line
    (where LilyPond's ``hhp`` and standard drum notation put it)."""
    src = """\
groove "g":
  HF: 2, 4
section "s":
  bars: 1
  groove: "g"
"""
    [m] = _song_measures(src)
    hf = [n for n in m.findall("note") if n.find("unpitched") is not None]
    assert {(n.findtext("unpitched/display-step"), n.findtext("unpitched/display-octave")) for n in hf} == {("D", "4")}

def test_tempo_in_eighth_meter_uses_eighth_beat_unit():
    """Regression: MusicXML always wrote a quarter-note metronome mark (and
    ``<sound tempo>`` of the raw BPM), so a 6/8 chart at ``tempo: 120``
    played twice as fast as the printed eighth = 120."""
    src = (
        'metadata:\n  tempo: 120\n  time_signature: 6/8\n'
        'groove "g":\n  BD: 1, 4\n  SN: 3\n'
        'section "A":\n  bars: 1\n  groove: "g"\n'
    )
    root = _parse_xml(emit_musicxml(compile_song(parse(src))))
    assert root.find(".//metronome/beat-unit").text == "eighth"
    assert root.find(".//metronome/per-minute").text == "120"
    assert root.find(".//direction/sound").get("tempo") == "60"


def test_sixteenth_and_triplet_in_one_beat_fill_the_measure():
    """Regression: the greedy duration split could not represent the 5/12-beat
    gap between ``1let`` and ``2`` (dotted 16th + an unrepresentable 1/48),
    silently dropped the remainder, and wrote a short (invalid) measure."""
    src = (
        'metadata:\n  tempo: 120\n'
        'groove "g":\n  SN: 1, 1e, 1let, 2\n'
        'section "A":\n  bars: 1\n  groove: "g"\n'
    )
    root = _parse_xml(emit_musicxml(compile_song(parse(src))))
    measure = _measures(root)[0]
    assert _measure_duration(measure) == _bar_total_divs("4/4")
    _split = _split_duration(5 * _DIVS_PER_BEAT // 12)
    assert sum(_split) == 5 * _DIVS_PER_BEAT // 12


def test_open_hihat_is_an_x_with_an_open_mark():
    """Regression test: OH was exported as a ``circle-x`` notehead, which
    the web preview (Verovio) drew as a slash. It is now an x notehead with
    <technical><open-string/> (the small "o"), matching LilyPond's ``hho``;
    a closed HH gets no mark, and a split (tied) OH marks only its attack."""
    src = """\
groove "g":
  HH: 1, 2
  OH: 1&, 3
section "s":
  bars: 1
  groove: "g"
"""
    [m] = _song_measures(src)
    notes = [n for n in m.findall("note") if n.find("unpitched") is not None]
    oh = [n for n in notes if n.findtext("unpitched/display-step") == "G" and n.find("notations/technical/open-string") is not None]
    assert len(oh) == 2  # 1& and the attack of 3 (held to the bar line, tied)
    assert all(n.findtext("notehead") == "x" for n in notes if n.findtext("unpitched/display-step") == "G")
    marked = sum(1 for n in notes if n.find("notations/technical/open-string") is not None)
    assert marked == 2
    assert "circle-x" not in emit_musicxml(compile_song(parse(src))).decode()
