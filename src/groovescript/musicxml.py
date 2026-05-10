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

# Divisions per quarter note. The value must be divisible by every tuplet
# denominator we want to emit cleanly: lcm(8, 3, 5, 6, 7, 9) = 2520. With
# 2520, a triplet 8th = 840 divs, a sextuplet 16th = 420, a quintuplet 16th =
# 504, a septuplet 16th = 360, a nonuplet 32nd = 280, a 32nd note = 315 —
# every tuplet kind we support has integer divisions.
_DIVS_PER_BEAT = 2520
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
    "RB":  ("F", 5, "diamond",  "up"),
    "CR":  ("A", 5, "x",        "up"),
    # Crash 2 sits on the same line as cowbell (A5) but uses a slash notehead
    # so it remains visually distinct from CR (x), CB (triangle), and ST.
    "CR2": ("A", 5, "slash",    "up"),
    # Splash and china are drawn higher than crash. Both share the B5 ledger
    # space; the diamond / circle-x noteheads keep them apart.
    "SP":  ("B", 5, "diamond",  "up"),
    "CH":  ("C", 6, "circle-x", "up"),
    # Stack: same line as crash 1 but with the slash notehead inverted-arrow
    # variant ("cluster") to flag the short, choked character.
    "ST":  ("A", 5, "cluster",  "up"),
    "CB":  ("A", 5, "triangle", "up"),
    "FT":  ("A", 4, "normal",   "down"),
    "MT":  ("D", 5, "normal",   "down"),
    "HT":  ("E", 5, "normal",   "up"),
}

# Duration table: (divisions, type_name, dots, actual_notes, normal_notes)
# actual/normal != 1/1 signals a tuplet requiring <time-modification>.
# Built programmatically off ``_DIVS_PER_BEAT`` so the table scales when
# we change divisions to accommodate new tuplet ratios. ``_PB`` = divisions
# per beat (per quarter note in 4/4); a power-of-2 note value's duration is
# ``_PB * 4 / N`` (whole=4*_PB, half=2*_PB, quarter=_PB, eighth=_PB/2, …).
_PB = _DIVS_PER_BEAT


def _build_duration_table() -> list[tuple[int, str, int, int, int]]:
    rows: list[tuple[int, str, int, int, int]] = []
    base = {
        "whole":   _PB * 4,
        "half":    _PB * 2,
        "quarter": _PB,
        "eighth":  _PB // 2,
        "16th":    _PB // 4,
        "32nd":    _PB // 8,
    }
    for type_name, divs in base.items():
        rows.append((divs, type_name, 0, 1, 1))
        rows.append((divs * 3 // 2, type_name, 1, 1, 1))            # dotted
        rows.append((divs * 2 // 3, type_name, 0, 3, 2))            # triplet (3:2)
    # Tuplet-only entries used by ``_emit_tuplet_beat`` when it picks a
    # type+ratio for tuplets beyond the legacy 3:2.  Sorted by divs at the
    # end so the greedy decomposition still works for non-tuplet content.
    return rows


_DURATION_TABLE: list[tuple[int, str, int, int, int]] = _build_duration_table()
_DUR_BY_SIZE = sorted(_DURATION_TABLE, key=lambda x: x[0], reverse=True)


# Map note-value denominator to MusicXML <type> name. 1 = whole, 2 = half,
# etc. Used by both straight and tuplet emission paths so that tuplets in
# non-quarter beat units (6/8, 12/8, 12/16, …) print the right slot type.
_NOTE_VALUE_TO_TYPE: dict[int, str] = {
    1: "whole",
    2: "half",
    4: "quarter",
    8: "eighth",
    16: "16th",
    32: "32nd",
    64: "64th",
    128: "128th",
    256: "256th",
}


def _tuplet_slot_divs(actual: int, beat_unit: int, half_beat: bool) -> int:
    """Divisions for one slot of an N:M tuplet over a (half-)beat.

    The block span equals one beat (= ``4 * _PB / beat_unit`` divisions)
    or half a beat. Slot divisions = block divisions / N. With _PB = 2520
    every supported (actual, beat_unit, half_beat) combo we need has
    integer divisions.
    """
    block_divs = (4 * _PB) // beat_unit
    if half_beat:
        block_divs //= 2
    return block_divs // actual


def _tuplet_printed_type(normal: int, beat_unit: int, half_beat: bool) -> str:
    """Printed <type> for a tuplet slot.

    M of the slot's printed value fill the block, so the slot's printed
    value is 1/(M * beat_unit) for a whole-beat block and
    1/(2 * M * beat_unit) for a half-beat block.
    """
    factor = 2 if half_beat else 1
    denom = factor * normal * beat_unit
    return _NOTE_VALUE_TO_TYPE[denom]


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

    # Pre-compute the multi-rest span count for each rest bar that *starts*
    # a run of two or more consecutive rest bars. The first bar of the
    # span emits a <measure-style><multiple-rest>N</multiple-rest>; the
    # remaining N-1 bars are plain whole-bar rests with no attribute, as
    # required by the MusicXML spec.
    multirest_starts: dict[int, int] = {}
    i = 0
    while i < len(bars):
        if not bars[i].is_rest:
            i += 1
            continue
        # Walk forward to count the run, breaking on a non-rest bar, a
        # section boundary, or a time-signature change (matches the
        # LilyPond emitter so visual and structural splits agree).
        run = 1
        run_ts = bars[i].time_signature
        while i + run < len(bars):
            nb = bars[i + run]
            if not nb.is_rest:
                break
            if nb.section_name is not None:
                break
            if (nb.time_signature or run_ts) != run_ts:
                break
            run += 1
        if run > 1:
            multirest_starts[i] = run
        i += run

    for i, bar in enumerate(bars):
        ts = bar.time_signature if bar.time_signature is not None else cur_ts
        bpm = bar.tempo if bar.tempo is not None else cur_bpm
        is_first = i == 0
        span = multirest_starts.get(i)

        measure = SubElement(part, "measure", number=str(bar.number))

        needs_attrs = is_first or ts != cur_ts or span is not None
        if needs_attrs:
            attrs = SubElement(measure, "attributes")
            if is_first:
                SubElement(attrs, "divisions").text = str(_DIVS_PER_BEAT)
                key = SubElement(attrs, "key")
                SubElement(key, "fifths").text = "0"
            if is_first or ts != cur_ts:
                _add_time(attrs, ts)
            if is_first:
                clef = SubElement(attrs, "clef")
                SubElement(clef, "sign").text = "percussion"
            # First bar of a multi-rest span carries a
            # <measure-style><multiple-rest>N</multiple-rest></measure-style>
            # attribute so MusicXML readers collapse the run into a
            # single multi-bar rest visual; the remaining N-1 bars stay
            # as ordinary whole-bar rests.
            if span is not None:
                ms = SubElement(attrs, "measure-style")
                SubElement(ms, "multiple-rest").text = str(span)

        if is_first or bpm != cur_bpm:
            _add_tempo_direction(measure, bpm)

        if bar.section_name is not None:
            _add_rehearsal(measure, bar.section_name)

        bar_divs = _bar_total_divs(ts)
        n, d = ts.split("/")
        beats_per_bar = int(n)
        beat_unit = int(d)
        if bar.is_rest:
            _add_whole_rest(measure, bar_divs)
        else:
            _add_notes(
                measure, bar.events, bar_divs,
                beats_per_bar=beats_per_bar,
                beat_unit=beat_unit,
                beat_tuplets=bar.beat_tuplets,
            )

        cur_ts = ts
        cur_bpm = bpm


# ---------------------------------------------------------------------------
# IRGroove path (standalone, played once at 120 BPM in 4/4)
# ---------------------------------------------------------------------------

def _musicxml_from_groove(groove: IRGroove) -> bytes:
    ts = _DEFAULT_TS
    bpm = _DEFAULT_TEMPO
    bar_divs = _bar_total_divs(ts)
    n, d = ts.split("/")
    beats_per_bar = int(n)
    beat_unit = int(d)

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

        bar_tuplets = (
            groove.bar_beat_tuplets[bar_num - 1]
            if bar_num - 1 < len(groove.bar_beat_tuplets)
            else []
        )
        _add_notes(
            measure, events, bar_divs,
            beats_per_bar=beats_per_bar,
            beat_unit=beat_unit,
            beat_tuplets=bar_tuplets,
        )

    return _serialize(root)


# ---------------------------------------------------------------------------
# Note / rest emission
# ---------------------------------------------------------------------------

def _add_notes(
    parent: Element,
    events: list[Event],
    bar_divs: int,
    beats_per_bar: int = 4,
    beat_unit: int = 4,
    beat_tuplets: list | None = None,
) -> None:
    """Append <note> elements covering the full measure duration.

    Slot durations that cannot be expressed by a single MusicXML note type
    are split into a tied chain so that <duration> and <type> always agree
    (e.g. a 60-division gap becomes a half tied to an eighth, not a single
    note with duration=60 and type='half').

    When ``beat_tuplets`` annotates a beat with an ``("full", a, n)`` or
    ``("halves", left, right)`` tuple, that beat is rendered slot-by-slot
    inside a tuplet block (one note per slot, with explicit time-modification),
    rather than going through the straight-grid greedy decomposition.
    """
    # Skip tied-from-prev events (buzz continuations started in the prior bar)
    active = [ev for ev in events if not ev.tied_from_prev]

    if not active and not (beat_tuplets and any(beat_tuplets)):
        _add_whole_rest(parent, bar_divs)
        return

    # Group events by onset position in divisions
    by_onset: dict[int, list[Event]] = {}
    for ev in active:
        onset = int(ev.beat_position * bar_divs)
        by_onset.setdefault(onset, []).append(ev)

    has_tuplets = bool(beat_tuplets) and any(a is not None for a in beat_tuplets)
    if not has_tuplets:
        # Legacy fast path: one greedy pass over the bar.
        _add_notes_straight(parent, by_onset, bar_divs)
        return

    # Tuplet-aware path: walk beat by beat. For straight beats, fall back to
    # straight emission within that beat's range. For tuplet beats, emit
    # slot-by-slot with explicit time-modification.
    pos = 0
    beat_divs = bar_divs // beats_per_bar
    for beat_idx in range(beats_per_bar):
        beat_start = beat_idx * beat_divs
        beat_end = beat_start + beat_divs
        annot = (
            beat_tuplets[beat_idx] if beat_tuplets and beat_idx < len(beat_tuplets) else None
        )
        if annot is None:
            # Straight beat — emit any events landing in this beat using the
            # standard greedy decomposition, capped at the beat boundary.
            beat_onsets = {
                o: evs for o, evs in by_onset.items() if beat_start <= o < beat_end
            }
            pos = _emit_straight_range(
                parent, beat_onsets, beat_start, beat_end, pos
            )
            continue
        if annot[0] == "full":
            _, actual, normal = annot
            pos = _emit_tuplet_block(
                parent, by_onset, beat_start, beat_divs,
                actual, normal,
                slot_divs=_tuplet_slot_divs(actual, beat_unit, half_beat=False),
                printed_type=_tuplet_printed_type(normal, beat_unit, half_beat=False),
                pos=pos,
            )
            continue
        if annot[0] == "halves":
            _, left, right = annot
            half_divs = beat_divs // 2
            half_mid = beat_start + half_divs
            for half_start, ratio in (
                (beat_start, left),
                (half_mid, right),
            ):
                half_end = half_start + half_divs
                if ratio is None:
                    half_onsets = {
                        o: evs for o, evs in by_onset.items()
                        if half_start <= o < half_end
                    }
                    pos = _emit_straight_range(
                        parent, half_onsets, half_start, half_end, pos
                    )
                else:
                    actual, normal = ratio
                    pos = _emit_tuplet_block(
                        parent, by_onset, half_start, half_divs,
                        actual, normal,
                        slot_divs=_tuplet_slot_divs(actual, beat_unit, half_beat=True),
                        printed_type=_tuplet_printed_type(normal, beat_unit, half_beat=True),
                        pos=pos,
                    )
            continue
        # Unknown annotation — skip this beat as straight.
        beat_onsets = {
            o: evs for o, evs in by_onset.items() if beat_start <= o < beat_end
        }
        pos = _emit_straight_range(parent, beat_onsets, beat_start, beat_end, pos)

    if pos < bar_divs:
        for rest_divs in _split_duration(bar_divs - pos):
            _append_rest(parent, rest_divs)


def _add_notes_straight(
    parent: Element,
    by_onset: dict[int, list[Event]],
    bar_divs: int,
) -> None:
    """Original straight-grid emission path — preserved verbatim for the
    common case where no beat in the bar carries a tuplet annotation."""
    onsets = sorted(by_onset.keys())
    pos = 0

    for idx, onset in enumerate(onsets):
        if onset > pos:
            for rest_divs in _split_duration(onset - pos):
                _append_rest(parent, rest_divs)

        next_onset = onsets[idx + 1] if idx + 1 < len(onsets) else bar_divs
        slot_dur = max(next_onset - onset, 1)
        parts = _split_duration(slot_dur)
        n_parts = len(parts)
        chord_evs = by_onset[onset]

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

    if pos < bar_divs:
        for rest_divs in _split_duration(bar_divs - pos):
            _append_rest(parent, rest_divs)


def _emit_straight_range(
    parent: Element,
    by_onset: dict[int, list[Event]],
    start: int,
    end: int,
    pos: int,
) -> int:
    """Emit straight-grid notes/rests covering ``[start, end)``.

    Returns the new ``pos`` cursor (always equal to ``end``).
    """
    if pos < start:
        for rest_divs in _split_duration(start - pos):
            _append_rest(parent, rest_divs)
        pos = start

    onsets = sorted(by_onset.keys())
    for idx, onset in enumerate(onsets):
        if onset > pos:
            for rest_divs in _split_duration(onset - pos):
                _append_rest(parent, rest_divs)
        next_onset = onsets[idx + 1] if idx + 1 < len(onsets) else end
        slot_dur = max(next_onset - onset, 1)
        parts = _split_duration(slot_dur)
        n_parts = len(parts)
        chord_evs = by_onset[onset]
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
    if pos < end:
        for rest_divs in _split_duration(end - pos):
            _append_rest(parent, rest_divs)
        pos = end
    return pos


def _emit_tuplet_block(
    parent: Element,
    by_onset: dict[int, list[Event]],
    block_start: int,
    block_divs: int,
    actual: int,
    normal: int,
    slot_divs: int,
    printed_type: str,
    pos: int,
) -> int:
    """Emit one tuplet block — ``actual`` slots, each printed as
    ``printed_type`` with ``<time-modification>actual/normal</time-modification>``.

    Each slot is one note (or one rest), regardless of whether the next
    slot is empty: this gives a clean, tuplet-bracketed engraving.
    """
    if pos < block_start:
        for rest_divs in _split_duration(block_start - pos):
            _append_rest(parent, rest_divs)
        pos = block_start

    for slot_idx in range(actual):
        slot_onset = block_start + slot_idx * slot_divs
        chord_evs = by_onset.get(slot_onset, [])
        # Bracket markers: "start" on first slot, "stop" on last slot.
        if slot_idx == 0:
            bracket: str | None = "start"
        elif slot_idx == actual - 1:
            bracket = "stop"
        else:
            bracket = None
        if not chord_evs:
            _append_tuplet_rest(
                parent, slot_divs, printed_type, actual, normal, bracket=bracket
            )
            continue
        for ev in chord_evs:
            _append_grace_notes(parent, ev)
        for chord_idx, ev in enumerate(chord_evs):
            _append_tuplet_note(
                parent, ev, slot_divs, printed_type, actual, normal,
                chord=(chord_idx > 0),
                # Only the first chord note carries the bracket marker.
                bracket=bracket if chord_idx == 0 else None,
            )
    return block_start + block_divs


def _append_tuplet_rest(
    parent: Element, dur: int, type_name: str, actual: int, normal: int,
    *, bracket: str | None = None,
) -> None:
    note = SubElement(parent, "note")
    SubElement(note, "rest")
    SubElement(note, "duration").text = str(dur)
    SubElement(note, "type").text = type_name
    tm = SubElement(note, "time-modification")
    SubElement(tm, "actual-notes").text = str(actual)
    SubElement(tm, "normal-notes").text = str(normal)
    if bracket is not None:
        notations = SubElement(note, "notations")
        SubElement(notations, "tuplet", number="1", type=bracket)


def _append_tuplet_note(
    parent: Element,
    ev: Event,
    dur: int,
    type_name: str,
    actual: int,
    normal: int,
    *,
    chord: bool,
    bracket: str | None = None,
) -> None:
    """Append one tuplet-slot note with explicit time-modification."""
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
    SubElement(note, "type").text = type_name
    tm = SubElement(note, "time-modification")
    SubElement(tm, "actual-notes").text = str(actual)
    SubElement(tm, "normal-notes").text = str(normal)
    SubElement(note, "stem").text = stem_dir
    notehead_el = SubElement(note, "notehead")
    notehead_el.text = notehead
    if "ghost" in ev.modifiers:
        notehead_el.set("parentheses", "yes")
    has_articulation = (
        "accent" in ev.modifiers
        or "choke" in ev.modifiers
        or "fermata" in ev.modifiers
    )
    if has_articulation or bracket is not None:
        notations = SubElement(note, "notations")
        if "accent" in ev.modifiers or "choke" in ev.modifiers:
            artic = SubElement(notations, "articulations")
            if "accent" in ev.modifiers:
                SubElement(artic, "accent")
            if "choke" in ev.modifiers:
                SubElement(artic, "stopped")
        if "fermata" in ev.modifiers:
            SubElement(notations, "fermata")
        if bracket is not None:
            SubElement(notations, "tuplet", number="1", type=bracket)


def _append_grace_notes(parent: Element, ev: Event) -> None:
    """Emit grace notes for a flam (1) or drag (2) modifier before the chord.

    With cross-instrument flam/drag (``ev.grace_instrument`` set), the grace
    notes use the named instrument's display info; otherwise they share the
    main hit's notehead/staff position.
    """
    grace_inst = getattr(ev, "grace_instrument", None) or ev.instrument
    disp = _DISPLAY.get(grace_inst)
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

    if show_articulation and (
        "accent" in ev.modifiers or "choke" in ev.modifiers
    ):
        artic = SubElement(_notations(), "articulations")
        if "accent" in ev.modifiers:
            SubElement(artic, "accent")
        if "choke" in ev.modifiers:
            # MusicXML's <stopped/> renders as the "+" symbol — the
            # standard cymbal-choke notation.
            SubElement(artic, "stopped")

    # <fermata/> is a top-level notation (sibling of <articulations>) and
    # only attaches to the first split-part (the attack), like articulations.
    if show_articulation and "fermata" in ev.modifiers:
        SubElement(_notations(), "fermata")


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
