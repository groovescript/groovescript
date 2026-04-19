"""MusicXML export: converts GrooveScript IR to MusicXML bytes.

Outputs a MusicXML 4.0 score-partwise document with a single percussion part.
Each IRBar maps to one <measure>; beat positions (stored as exact Fractions) are
converted to integer division offsets so the XML is standard-compliant.

Notes at the same beat position are grouped as chords via the <chord/> element.
Gaps between note groups are filled with rests so each measure's total duration
equals the bar's time signature.
"""

from __future__ import annotations

import datetime
import io
from fractions import Fraction
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement, ElementTree

from .compiler import Event, IRBar, IRGroove, IRSong

_DIVS_PER_BEAT = 24   # divisions per quarter note
_DEFAULT_TEMPO = 120
_DEFAULT_TS = "4/4"

# ---------------------------------------------------------------------------
# Instrument display properties on the percussion staff
# (display_step, display_octave, notehead_type, stem_direction)
# Positions follow standard drum notation conventions (treble-clef-based
# coordinate system used by MusicXML unpitched notes).
# ---------------------------------------------------------------------------
_DISPLAY: dict[str, tuple[str, int, str, str]] = {
    "BD":  ("F", 4, "normal",   "down"),
    "SN":  ("C", 5, "normal",   "up"),
    "SCS": ("C", 5, "x",        "up"),
    "HH":  ("G", 5, "x",        "up"),
    "OH":  ("G", 5, "circle-x", "up"),
    "HF":  ("E", 3, "x",        "down"),
    "RD":  ("F", 5, "x",        "up"),
    "CR":  ("A", 5, "x",        "up"),
    "FT":  ("A", 4, "normal",   "down"),
    "MT":  ("D", 5, "normal",   "down"),
    "HT":  ("E", 5, "normal",   "up"),
}

# Duration table: (divisions, type_name, dots, actual_notes, normal_notes)
# actual/normal != 1/1 signals a tuplet requiring <time-modification>.
# Sorted largest-first so greedy decomposition picks the biggest fit.
_DURATION_TABLE: list[tuple[int, str, int, int, int]] = [
    (96, "whole",   0, 1, 1),
    (72, "half",    1, 1, 1),   # dotted half
    (48, "half",    0, 1, 1),
    (36, "quarter", 1, 1, 1),   # dotted quarter
    (32, "half",    0, 3, 2),   # triplet half
    (24, "quarter", 0, 1, 1),
    (18, "eighth",  1, 1, 1),   # dotted eighth
    (16, "quarter", 0, 3, 2),   # triplet quarter
    (12, "eighth",  0, 1, 1),
    ( 9, "16th",    1, 1, 1),   # dotted 16th
    ( 8, "eighth",  0, 3, 2),   # triplet eighth
    ( 6, "16th",    0, 1, 1),
    ( 4, "16th",    0, 3, 2),   # triplet 16th
    ( 3, "32nd",    0, 1, 1),
    ( 2, "32nd",    0, 3, 2),   # triplet 32nd
]

_DUR_BY_SIZE = sorted(_DURATION_TABLE, key=lambda x: x[0], reverse=True)


# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------

def _bar_total_divs(ts: str) -> int:
    """Total divisions in one full bar of the given time signature."""
    n, d = ts.split("/")
    return int(Fraction(int(n) * 4, int(d)) * _DIVS_PER_BEAT)


def _duration_attrs(divs: int) -> tuple[str, int, int, int]:
    """Return (type_name, dots, actual_notes, normal_notes) for *divs* divisions."""
    for d, t, dots, actual, normal in _DURATION_TABLE:
        if d == divs:
            return t, dots, actual, normal
    for d, t, dots, actual, normal in _DUR_BY_SIZE:
        if d <= divs:
            return t, dots, actual, normal
    return "32nd", 0, 1, 1


def _split_duration(divs: int) -> list[int]:
    """Decompose *divs* into valid note-duration values (greedy, largest first).

    Guarantees the returned values sum to *divs* so measure totals stay correct.
    """
    result: list[int] = []
    remaining = divs
    while remaining > 0:
        for d, _, _, _, _ in _DUR_BY_SIZE:
            if d <= remaining:
                result.append(d)
                remaining -= d
                break
        else:
            break
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def emit_musicxml(ir: IRSong | IRGroove) -> bytes:
    """Convert an IRSong or standalone IRGroove to MusicXML 4.0 bytes."""
    if isinstance(ir, IRGroove):
        return _musicxml_from_groove(ir)
    return _musicxml_from_song(ir)


# ---------------------------------------------------------------------------
# IRSong path
# ---------------------------------------------------------------------------

def _musicxml_from_song(song: IRSong) -> bytes:
    default_ts = song.metadata.time_signature
    default_bpm = song.metadata.tempo if song.metadata.tempo is not None else _DEFAULT_TEMPO
    title = song.metadata.title or ""

    root = _score_root(title)
    root.find("part-list").append(_score_part("P1", "Drumset"))  # type: ignore[union-attr]

    part = SubElement(root, "part", id="P1")
    _fill_part(part, song.bars, default_ts, default_bpm)

    return _serialize(root)


def _fill_part(
    part: Element,
    bars: list[IRBar],
    default_ts: str,
    default_bpm: int,
) -> None:
    cur_ts = default_ts
    cur_bpm = default_bpm

    for i, bar in enumerate(bars):
        ts = bar.time_signature if bar.time_signature is not None else cur_ts
        bpm = bar.tempo if bar.tempo is not None else cur_bpm
        is_first = i == 0

        measure = SubElement(part, "measure", number=str(bar.number))

        if is_first or ts != cur_ts:
            attrs = SubElement(measure, "attributes")
            if is_first:
                SubElement(attrs, "divisions").text = str(_DIVS_PER_BEAT)
                key = SubElement(attrs, "key")
                SubElement(key, "fifths").text = "0"
            _add_time(attrs, ts)
            if is_first:
                clef = SubElement(attrs, "clef")
                SubElement(clef, "sign").text = "percussion"

        if is_first or bpm != cur_bpm:
            _add_tempo_direction(measure, bpm)

        if bar.section_name is not None:
            _add_rehearsal(measure, bar.section_name)

        bar_divs = _bar_total_divs(ts)
        if bar.is_rest:
            _add_whole_rest(measure, bar_divs)
        else:
            _add_notes(measure, bar.events, bar_divs)

        cur_ts = ts
        cur_bpm = bpm


# ---------------------------------------------------------------------------
# IRGroove path (standalone, played once at 120 BPM in 4/4)
# ---------------------------------------------------------------------------

def _musicxml_from_groove(groove: IRGroove) -> bytes:
    ts = _DEFAULT_TS
    bpm = _DEFAULT_TEMPO
    bar_divs = _bar_total_divs(ts)

    root = _score_root(groove.name)
    root.find("part-list").append(_score_part("P1", "Drumset"))  # type: ignore[union-attr]

    part = SubElement(root, "part", id="P1")

    by_bar: dict[int, list[Event]] = {}
    for ev in groove.events:
        by_bar.setdefault(ev.bar, []).append(ev)

    for bar_num in range(1, groove.bars + 1):
        events = by_bar.get(bar_num, [])
        measure = SubElement(part, "measure", number=str(bar_num))

        if bar_num == 1:
            attrs = SubElement(measure, "attributes")
            SubElement(attrs, "divisions").text = str(_DIVS_PER_BEAT)
            key = SubElement(attrs, "key")
            SubElement(key, "fifths").text = "0"
            _add_time(attrs, ts)
            clef = SubElement(attrs, "clef")
            SubElement(clef, "sign").text = "percussion"
            _add_tempo_direction(measure, bpm)

        _add_notes(measure, events, bar_divs)

    return _serialize(root)


# ---------------------------------------------------------------------------
# Note / rest emission
# ---------------------------------------------------------------------------

def _add_notes(parent: Element, events: list[Event], bar_divs: int) -> None:
    """Append <note> elements covering the full measure duration.

    Slot durations that cannot be expressed by a single MusicXML note type
    are split into a tied chain so that <duration> and <type> always agree
    (e.g. a 60-division gap becomes a half tied to an eighth, not a single
    note with duration=60 and type='half').
    """
    # Skip tied-from-prev events (buzz continuations started in the prior bar)
    active = [ev for ev in events if not ev.tied_from_prev]

    if not active:
        _add_whole_rest(parent, bar_divs)
        return

    # Group events by onset position in divisions
    by_onset: dict[int, list[Event]] = {}
    for ev in active:
        onset = int(ev.beat_position * bar_divs)
        by_onset.setdefault(onset, []).append(ev)

    onsets = sorted(by_onset.keys())
    pos = 0

    for idx, onset in enumerate(onsets):
        # Fill gap before this onset with rests
        if onset > pos:
            for rest_divs in _split_duration(onset - pos):
                _append_rest(parent, rest_divs)

        next_onset = onsets[idx + 1] if idx + 1 < len(onsets) else bar_divs
        slot_dur = max(next_onset - onset, 1)
        parts = _split_duration(slot_dur)
        n_parts = len(parts)
        chord_evs = by_onset[onset]

        # Grace notes (flam/drag) appear once before the chord, on the
        # first split-part only.
        for ev in chord_evs:
            _append_grace_notes(parent, ev)

        for part_idx, part_dur in enumerate(parts):
            is_first_part = part_idx == 0
            is_last_part = part_idx == n_parts - 1
            for chord_idx, ev in enumerate(chord_evs):
                _append_note(
                    parent, ev, part_dur,
                    chord=(chord_idx > 0),
                    split_tie_start=not is_last_part,
                    split_tie_stop=not is_first_part,
                    show_articulation=is_first_part,
                )

        pos = next_onset

    # Final rest to close out the measure
    if pos < bar_divs:
        for rest_divs in _split_duration(bar_divs - pos):
            _append_rest(parent, rest_divs)


def _append_grace_notes(parent: Element, ev: Event) -> None:
    """Emit grace notes for a flam (1) or drag (2) modifier before the chord."""
    disp = _DISPLAY.get(ev.instrument)
    if disp is None:
        return

    if "flam" in ev.modifiers:
        n_graces = 1
    elif "drag" in ev.modifiers:
        n_graces = 2
    else:
        return

    step, octave, notehead, stem_dir = disp
    for _ in range(n_graces):
        g = SubElement(parent, "note")
        SubElement(g, "grace", slash="yes")
        unp = SubElement(g, "unpitched")
        SubElement(unp, "display-step").text = step
        SubElement(unp, "display-octave").text = str(octave)
        SubElement(g, "voice").text = "1"
        SubElement(g, "type").text = "16th"
        SubElement(g, "stem").text = stem_dir
        SubElement(g, "notehead").text = notehead


def _append_note(
    parent: Element,
    ev: Event,
    dur: int,
    *,
    chord: bool,
    split_tie_start: bool = False,
    split_tie_stop: bool = False,
    show_articulation: bool = True,
) -> None:
    """Append a single <note> element for one drum hit."""
    disp = _DISPLAY.get(ev.instrument)
    if disp is None:
        return

    step, octave, notehead, stem_dir = disp
    note = SubElement(parent, "note")

    if chord:
        SubElement(note, "chord")

    unp = SubElement(note, "unpitched")
    SubElement(unp, "display-step").text = step
    SubElement(unp, "display-octave").text = str(octave)

    SubElement(note, "duration").text = str(dur)

    # Tie elements (must come before <type> per MusicXML schema)
    tie_stop = ev.tied_from_prev or split_tie_stop
    tie_start = ev.tied_to_next or split_tie_start
    if tie_stop:
        SubElement(note, "tie", type="stop")
    if tie_start:
        SubElement(note, "tie", type="start")

    type_name, dots, actual, normal = _duration_attrs(dur)
    SubElement(note, "type").text = type_name
    for _ in range(dots):
        SubElement(note, "dot")

    if actual != 1 or normal != 1:
        tm = SubElement(note, "time-modification")
        SubElement(tm, "actual-notes").text = str(actual)
        SubElement(tm, "normal-notes").text = str(normal)

    SubElement(note, "stem").text = stem_dir

    notehead_el = SubElement(note, "notehead")
    notehead_el.text = notehead
    # Ghost notes render as parenthesized noteheads on every tied part of
    # the chain so the visual cue carries across the tie.
    if "ghost" in ev.modifiers:
        notehead_el.set("parentheses", "yes")

    # Notations block (ties, accents). Articulations only attach to the
    # first split-part (the attack); ties attach to every part involved.
    notations: Element | None = None

    def _notations() -> Element:
        nonlocal notations
        if notations is None:
            notations = SubElement(note, "notations")
        return notations

    if tie_stop or tie_start:
        n = _notations()
        if tie_stop:
            SubElement(n, "tied", type="stop")
        if tie_start:
            SubElement(n, "tied", type="start")

    if show_articulation and "accent" in ev.modifiers:
        artic = SubElement(_notations(), "articulations")
        SubElement(artic, "accent")


def _append_rest(parent: Element, dur: int) -> None:
    note = SubElement(parent, "note")
    SubElement(note, "rest")
    SubElement(note, "duration").text = str(dur)
    type_name, dots, actual, normal = _duration_attrs(dur)
    SubElement(note, "type").text = type_name
    for _ in range(dots):
        SubElement(note, "dot")
    if actual != 1 or normal != 1:
        tm = SubElement(note, "time-modification")
        SubElement(tm, "actual-notes").text = str(actual)
        SubElement(tm, "normal-notes").text = str(normal)


def _add_whole_rest(parent: Element, bar_divs: int) -> None:
    note = SubElement(parent, "note")
    rest_el = SubElement(note, "rest")
    rest_el.set("measure", "yes")
    SubElement(note, "duration").text = str(bar_divs)
    SubElement(note, "type").text = "whole"


# ---------------------------------------------------------------------------
# Score structure helpers
# ---------------------------------------------------------------------------

def _score_root(title: str) -> Element:
    root = Element("score-partwise", version="4.0")
    work = SubElement(root, "work")
    SubElement(work, "work-title").text = title
    ident = SubElement(root, "identification")
    encoding = SubElement(ident, "encoding")
    SubElement(encoding, "software").text = "GrooveScript"
    SubElement(encoding, "encoding-date").text = datetime.date.today().isoformat()
    SubElement(root, "part-list")
    return root


def _score_part(part_id: str, name: str) -> Element:
    sp = Element("score-part", id=part_id)
    SubElement(sp, "part-name").text = name
    inst = SubElement(sp, "score-instrument", id=f"{part_id}-I1")
    SubElement(inst, "instrument-name").text = name
    return sp


def _add_time(parent: Element, ts: str) -> None:
    n, d = ts.split("/")
    time_el = SubElement(parent, "time")
    SubElement(time_el, "beats").text = n
    SubElement(time_el, "beat-type").text = d


def _add_tempo_direction(parent: Element, bpm: int) -> None:
    direction = SubElement(parent, "direction", placement="above")
    dt = SubElement(direction, "direction-type")
    metro = SubElement(dt, "metronome", parentheses="no")
    SubElement(metro, "beat-unit").text = "quarter"
    SubElement(metro, "per-minute").text = str(bpm)
    SubElement(direction, "sound", tempo=str(bpm))


def _add_rehearsal(parent: Element, name: str) -> None:
    direction = SubElement(parent, "direction", placement="above")
    dt = SubElement(direction, "direction-type")
    rehearsal = SubElement(dt, "rehearsal")
    rehearsal.set("font-weight", "bold")
    rehearsal.text = name


def _serialize(root: Element) -> bytes:
    ET.indent(root, space="  ")
    buf = io.BytesIO()
    ElementTree(root).write(buf, encoding="UTF-8", xml_declaration=False)
    xml_decl = b'<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype = (
        b'<!DOCTYPE score-partwise PUBLIC\n'
        b'  "-//Recordare//DTD MusicXML 4.0 Partwise//EN"\n'
        b'  "http://www.musicxml.org/dtds/partwise.dtd">\n'
    )
    return xml_decl + doctype + buf.getvalue()
