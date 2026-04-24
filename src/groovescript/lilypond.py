from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from .compiler import IRBar, IRGroove, IRSong

# Instruments that are foot-played (duplicated from compiler to avoid a
# circular dependency on the compiler-internal constant).  Must stay in sync.
_FOOT_INSTRUMENTS_LY: frozenset[str] = frozenset({"BD", "HF"})


def _buzz_duration_to_lily(buzz_duration: str) -> str:
    """Convert a buzz duration spec (e.g. ``"4"``, ``"2d"``, ``"2dd"``) to a
    LilyPond duration string (``"4"``, ``"2."``, ``"2.."``).
    """
    dots = 0
    spec = buzz_duration
    while spec.endswith("d"):
        dots += 1
        spec = spec[:-1]
    return f"{spec}{'.' * dots}"


def _span_to_ly_duration(span: Fraction, beats_per_bar: int, beat_unit: int) -> str:
    """Convert a bar-relative span to a single LilyPond duration string.

    Used for buzz events whose span has been clamped by the cross-bar tie
    splitter — the original ``buzz:N`` no longer matches the actual span,
    so the emitter recomputes from the Fraction.

    Tries plain durations 1/2/4/8/16/32 with optional single or double dot.
    Raises :class:`ValueError` if the span cannot be expressed as one such
    LilyPond duration (cross-bar splits that produce awkward fractions are
    not supported in this MVP).
    """
    for n in (1, 2, 4, 8, 16, 32):
        base = Fraction(beat_unit, n * beats_per_bar)
        if base == span:
            return str(n)
        if base * Fraction(3, 2) == span:
            return f"{n}."
        if base * Fraction(7, 4) == span:
            return f"{n}.."
    raise ValueError(
        f"Cannot express span {span} of bar as a single LilyPond duration "
        f"(beats_per_bar={beats_per_bar}, beat_unit={beat_unit})"
    )

_TEMPLATE_PATH = Path(__file__).parent / "lilypond_template.ly"


def _ly_str(s: str) -> str:
    """Escape a user-supplied string for safe inclusion inside a LilyPond ``"..."``.

    LilyPond strings treat ``\\`` as an escape introducer, so a user string
    ending in ``\\`` would swallow the closing quote and let subsequent
    source bytes (including Scheme ``#(system ...)``) be parsed as code.
    This escapes ``\\`` first, then ``"``, and flattens newlines so content
    can't break out of a single-line header field.
    """
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _parse_time_signature(ts: str) -> tuple[int, int]:
    """Return (beats_per_bar, beat_unit) from a time signature string like '3/4'."""
    num, den = ts.split("/")
    return int(num), int(den)

_DYNAMIC_HAIRPIN: dict[str, str] = {
    "cresc": "\\<",
    "decresc": "\\>",
}

_INSTRUMENT_TO_LY: dict[str, str] = {
    "BD": "bd",
    "SN": "sn",
    "SCS": "ss",    # snare cross-stick / side-stick
    "HH": "hh",
    "OH": "hho",    # open hi-hat (LilyPond alias for openhihat)
    "HF": "hhp",    # hi-hat foot chick (pedal)
    "RD": "cymr",
    "CR": "cymc",
    "FT": "tomfh",
    "HT": "tomh",
    "MT": "tommh",
}


def _is_triplet_only(pos: Fraction, beats_per_bar: int = 4) -> bool:
    """Return True if pos is on the triplet grid (3 per beat) but NOT on the straight 8th grid (2 per beat).

    For 4/4: triplet grid = 12 per bar (1/12), straight = 8 per bar (1/8).
    For 3/4: triplet grid = 9 per bar (1/9), straight = 6 per bar (1/6).
    Beat downbeats land on both grids and return False.
    """
    triplet_grid = beats_per_bar * 3
    straight_grid = beats_per_bar * 2
    return (pos * triplet_grid).denominator == 1 and (pos * straight_grid).denominator != 1


def _is_sixteenth_only(pos: Fraction, beats_per_bar: int = 4) -> bool:
    """Return True if pos is on the 16th grid (4 per beat) but NOT on the 8th grid (2 per beat).

    For 4/4: 16th grid = 16 per bar (1/16), 8th grid = 8 per bar (1/8).
    Positions on the 8th grid (including beat downbeats) return False.
    """
    sixteenth_grid = beats_per_bar * 4
    eighth_grid = beats_per_bar * 2
    return (pos * sixteenth_grid).denominator == 1 and (pos * eighth_grid).denominator != 1


def _format_hits(hits: list[tuple[str, set[str]]], duration: str) -> str:
    """Format a list of (ly_name, modifiers) hits as a LilyPond token with *duration*."""
    if not hits:
        return f"r{duration}"

    grace_prefix = ""
    processed_notes: list[str] = []
    any_accent = False

    for ly_name, mods in hits:
        # Grace notes: flam = one grace note, drag = two grace notes.
        # Use \slashedGrace (slashed, no auto-slur) for flam — \acciaccatura
        # would draw a slur from the grace to the main note, which renders as
        # a tie when the grace pitch matches a pitch in the main chord.
        if not grace_prefix:
            if "flam" in mods:
                grace_prefix = f"\\slashedGrace {ly_name}16 "
            elif "drag" in mods:
                grace_prefix = f"\\grace {{ {ly_name}16 {ly_name}16 }} "

        note = ly_name
        if "ghost" in mods:
            note = f"\\parenthesize {note}"
        if "accent" in mods:
            any_accent = True
        processed_notes.append(note)

    if len(processed_notes) == 1:
        token = f"{processed_notes[0]}{duration}"
    else:
        notes_str = " ".join(processed_notes)
        token = f"<{notes_str}>{duration}"

    if any_accent:
        token = f"{token}->"

    return f"{grace_prefix}{token}"


def _format_doubled_hits(hits: list[tuple[str, set[str]]]) -> str:
    """Format a 'double' (double-stroke) slot as two 32nd-note LilyPond tokens.

    The 'double' modifier means the slot is played as two equal 32nd notes
    (a double stroke). Rules:
    - Only the instruments that carry 'double' are doubled; others play once
      on the first 32nd, contributing to a chord on the first stroke.
    - 'ghost' applies to both strokes (both notes are parenthesised).
    - 'accent' applies to the first stroke only.
    - 'flam'/'drag' are rejected at compile time and will not appear here.

    Returns a string of two LilyPond tokens (e.g. ``"hh32 hh32"`` or
    ``"<hh32 sn32>-> hh32"`` when BD is not doubled but HH is).
    """
    # Split hits into doubled and non-doubled.
    doubled = [(ly, mods) for ly, mods in hits if "double" in mods]
    not_doubled = [(ly, mods) for ly, mods in hits if "double" not in mods]

    # --- First stroke: all notes (doubled + non-doubled) ---
    first_notes: list[str] = []
    any_accent_first = False
    for ly_name, mods in not_doubled + doubled:
        note = ly_name
        if "ghost" in mods:
            note = f"\\parenthesize {note}"
        if "accent" in mods:
            any_accent_first = True
        first_notes.append(note)

    if len(first_notes) == 1:
        first_token = f"{first_notes[0]}32"
    else:
        first_token = f"<{' '.join(first_notes)}>32"
    if any_accent_first:
        first_token = f"{first_token}->"

    # --- Second stroke: only doubled notes ---
    second_notes: list[str] = []
    for ly_name, mods in doubled:
        note = ly_name
        if "ghost" in mods:
            note = f"\\parenthesize {note}"
        second_notes.append(note)

    if len(second_notes) == 1:
        second_token = f"{second_notes[0]}32"
    else:
        second_token = f"<{' '.join(second_notes)}>32"

    return f"{first_token} {second_token}"


def _slot_run_to_lily_durations(run_slots: int, subdivision: int, beats_per_bar: int, beat_unit: int) -> list[str]:
    """Convert a run length (in bar slots) to one or more LilyPond durations.

    Splits into the largest power-of-two slot chunks that can each be
    represented by a single LilyPond duration integer. A chunk of ``n`` slots
    corresponds to LilyPond duration
    ``beat_unit * subdivision / (n * beats_per_bar)`` — only valid when the
    denominator divides the numerator evenly.
    """
    durations: list[str] = []
    remaining = run_slots
    while remaining > 0:
        # Pick the largest chunk ≤ remaining whose LilyPond duration is
        # a valid integer (power of 2 only to keep durations clean).
        chunk = 1
        while chunk * 2 <= remaining and (
            (beat_unit * subdivision) % ((chunk * 2) * beats_per_bar) == 0
        ):
            chunk *= 2
        durations.append(str(beat_unit * subdivision // (chunk * beats_per_bar)))
        remaining -= chunk
    return durations


def _emit_foot_voice_for_buzz(
    foot_events: list,
    start_slot: int,
    end_slot: int,
    subdivision: int,
    beats_per_bar: int,
    beat_unit: int,
) -> str:
    """Emit the second-voice body for a buzz-span voice split.

    Renders foot-played events (BD / HF) across the buzz span. Events are
    placed at their slot, with rests filling any gaps; each note's duration
    runs until the next event (or the end of the buzz span). Stems go down
    because LilyPond treats the second voice inside ``<< \\\\ >>`` as voice 2.
    """
    pos_map: dict[int, list[tuple[str, set[str]]]] = defaultdict(list)
    for event in foot_events:
        slot = int(event.beat_position * subdivision)
        ly_name = _INSTRUMENT_TO_LY.get(event.instrument, event.instrument.lower())
        pos_map[slot].append((ly_name, set(event.modifiers)))

    event_slots = sorted(pos_map.keys())
    tokens: list[str] = []
    cursor = start_slot
    for slot in event_slots:
        if slot > cursor:
            # Rest from cursor to slot.
            for dur in _slot_run_to_lily_durations(slot - cursor, subdivision, beats_per_bar, beat_unit):
                tokens.append(f"r{dur}")
        next_slot = min(
            (s for s in event_slots if s > slot), default=end_slot
        )
        note_run = next_slot - slot
        durations = _slot_run_to_lily_durations(note_run, subdivision, beats_per_bar, beat_unit)
        hits = pos_map[slot]
        # First chunk carries the notes; subsequent chunks tie-extend via a
        # simple repeat (no explicit tie — for foot events this is visually
        # indistinguishable from a repeated kick, and buzz rolls are short).
        tokens.append(_format_hits(hits, durations[0]))
        for dur in durations[1:]:
            tokens.append(_format_hits(hits, dur))
        cursor = next_slot
    if cursor < end_slot:
        for dur in _slot_run_to_lily_durations(end_slot - cursor, subdivision, beats_per_bar, beat_unit):
            tokens.append(f"r{dur}")
    return " ".join(tokens)


def _attach_position_markup(
    token: str,
    pos: Fraction,
    cue_map: dict | None,
    placeholder_map: dict | None,
    dynamic_start_map: dict | None,
    dynamic_stop_set: set | None,
) -> str:
    """Append cue/placeholder markup and dynamic hairpin commands at ``pos``.

    Used by both the straight-grid and mixed-grid bar emitters to keep
    markup-placement rules consistent.
    """
    if cue_map and pos in cue_map:
        escaped = _ly_str(cue_map[pos])
        token = f'{token}^\\markup {{ \\italic \\fontsize #-1 "{escaped}" }}'
    if placeholder_map and pos in placeholder_map:
        escaped = _ly_str(placeholder_map[pos])
        token = f'{token}^\\markup {{ \\bold \\box \\fontsize #-1 "{escaped}" }}'
    if dynamic_stop_set and pos in dynamic_stop_set:
        token = f'{token}\\!'
    if dynamic_start_map and pos in dynamic_start_map:
        hairpin = _DYNAMIC_HAIRPIN[dynamic_start_map[pos]]
        token = f'{token}{hairpin}'
    return token


def _drum_measure_straight(
    events,
    subdivision: int,
    beats_per_bar: int = 4,
    beat_unit: int = 4,
    cue_map: dict | None = None,
    placeholder_map: dict | None = None,
    dynamic_start_map: dict | None = None,
    dynamic_stop_set: set | None = None,
    forced_voice_split_ids: set | None = None,
) -> str:
    """Emit LilyPond for a bar with only straight (non-triplet) content."""
    # Identify buzz-roll spans before building the point-event position map
    # so we can exclude the buzz hits from ordinary slot processing.
    buzz_spans: list[tuple[int, int, object]] = []  # (start_slot, end_slot, event)
    buzz_event_ids: set[int] = set()
    for event in events:
        if event.duration is not None and "buzz" in event.modifiers:
            start_slot = int(event.beat_position * subdivision)
            end_slot = int((event.beat_position + event.duration) * subdivision)
            buzz_spans.append((start_slot, end_slot, event))
            buzz_event_ids.add(id(event))
    buzz_spans.sort(key=lambda x: x[0])
    buzz_span_slots: set[int] = set()
    for start_slot, end_slot, _ in buzz_spans:
        for s in range(start_slot, end_slot):
            buzz_span_slots.add(s)
    buzz_start_map: dict[int, tuple[int, object]] = {
        start_slot: (end_slot, event) for start_slot, end_slot, event in buzz_spans
    }

    pos_map: dict[Fraction, list[tuple[str, set[str]]]] = defaultdict(list)
    # Foot events that overlap a buzz span are rendered in the second voice of
    # the voice-split; keep them out of the normal pos_map so they don't get
    # emitted twice.
    foot_overlap_events: dict[int, list[object]] = defaultdict(list)  # buzz_start_slot → events
    for event in events:
        if id(event) in buzz_event_ids:
            continue
        slot = int(event.beat_position * subdivision)
        in_buzz_span = slot in buzz_span_slots
        if in_buzz_span and event.instrument in _FOOT_INSTRUMENTS_LY:
            # Find which buzz span this event belongs to and stash it.
            for start_slot, end_slot, _ in buzz_spans:
                if start_slot <= slot < end_slot:
                    foot_overlap_events[start_slot].append(event)
                    break
            continue
        ly_name = _INSTRUMENT_TO_LY.get(event.instrument, event.instrument.lower())
        pos_map[event.beat_position].append((ly_name, set(event.modifiers)))

    # Pre-compute which bar-slot indices contain a 'double' hit so consolidation
    # can be skipped for those slots (and their neighbours that would be merged).
    doubled_slots: set[int] = set()
    for event in events:
        if "double" in event.modifiers:
            slot_idx = int(event.beat_position * subdivision)
            doubled_slots.add(slot_idx)

    # Slots that fill a quarter note (LilyPond "4") and eighth note (LilyPond "8").
    # LilyPond duration = beat_unit*subdivision//(consolidated*beats_per_bar).
    slots_in_quarter = max(1, subdivision // beats_per_bar)
    slots_in_eighth = max(1, subdivision // (beats_per_bar * 2))

    tokens: list[str] = []
    i = 0
    while i < subdivision:
        pos = Fraction(i, subdivision)
        hits = pos_map.get(pos, [])

        # Buzz span: emit the buzz token (and optional voice split for
        # overlapping foot events) and skip the slots it consumes.
        if i in buzz_start_map:
            end_slot, buzz_event = buzz_start_map[i]
            # Cross-bar tie continuations carry no buzz_duration string;
            # compute the LilyPond duration from the actual span. Likewise
            # for split heads whose original duration string no longer
            # matches the clamped span.
            if buzz_event.buzz_duration is not None and not getattr(
                buzz_event, "tied_to_next", False
            ):
                ly_dur = _buzz_duration_to_lily(buzz_event.buzz_duration)
            else:
                ly_dur = _span_to_ly_duration(
                    buzz_event.duration, beats_per_bar, beat_unit
                )
            buzz_ly_name = _INSTRUMENT_TO_LY.get(
                buzz_event.instrument, buzz_event.instrument.lower()
            )
            buzz_token = f"{buzz_ly_name}{ly_dur}:32"
            if "accent" in buzz_event.modifiers:
                buzz_token = f"{buzz_token}->"
            if getattr(buzz_event, "tied_to_next", False):
                buzz_token = f"{buzz_token}~"

            foot_events = foot_overlap_events.get(i, [])
            force_split = (
                forced_voice_split_ids is not None
                and id(buzz_event) in forced_voice_split_ids
            )
            if foot_events:
                foot_tokens = _emit_foot_voice_for_buzz(
                    foot_events, i, end_slot, subdivision, beats_per_bar, beat_unit
                )
                token = f"<< {{ {buzz_token} }} \\\\ {{ {foot_tokens} }} >>"
            elif force_split:
                # Emit a voice-split with an empty second voice (rests only)
                # so a tied buzz whose partner bar uses a voice split keeps
                # the tie inside a single voice context — otherwise LilyPond
                # warns "unterminated tie" and drops the visual tie arc.
                rest_tokens = " ".join(
                    f"r{d}"
                    for d in _slot_run_to_lily_durations(
                        end_slot - i, subdivision, beats_per_bar, beat_unit
                    )
                )
                token = f"<< {{ {buzz_token} }} \\\\ {{ {rest_tokens} }} >>"
            else:
                token = buzz_token

            token = _attach_position_markup(token, pos, cue_map, placeholder_map, dynamic_start_map, dynamic_stop_set)
            tokens.append(token)
            i = end_slot
            continue

        # If this slot has a 'double' hit, emit two 32nd notes and skip consolidation.
        is_doubled_slot = i in doubled_slots
        if is_doubled_slot:
            token = _format_doubled_hits(hits)
            if cue_map and pos in cue_map:
                escaped = _ly_str(cue_map[pos])
                # Attach markup to the first of the two tokens.
                first, second = token.split(" ", 1)
                token = f'{first}^\\markup {{ \\italic \\fontsize #-1 "{escaped}" }} {second}'
            if placeholder_map and pos in placeholder_map:
                escaped = _ly_str(placeholder_map[pos])
                first, second = token.split(" ", 1)
                token = f'{first}^\\markup {{ \\bold \\box \\fontsize #-1 "{escaped}" }} {second}'
            # Dynamic hairpin commands (attach to first of doubled pair)
            if dynamic_stop_set and pos in dynamic_stop_set:
                first, second = token.split(" ", 1)
                token = f'{first}\\! {second}'
            if dynamic_start_map and pos in dynamic_start_map:
                hairpin = _DYNAMIC_HAIRPIN[dynamic_start_map[pos]]
                first, second = token.split(" ", 1)
                token = f'{first}{hairpin} {second}'
            tokens.append(token)
            i += 1
            continue

        consolidated = 1
        # Do not consolidate across a doubled slot or a buzz-span slot.
        if i % slots_in_quarter == 0 and i + slots_in_quarter <= subdivision:
            blocked = any(
                (i + j in doubled_slots) or (i + j in buzz_span_slots) or (i + j in buzz_start_map)
                for j in range(1, slots_in_quarter)
            )
            if not blocked:
                match = True
                for j in range(1, slots_in_quarter):
                    if pos_map.get(Fraction(i + j, subdivision)):
                        match = False
                        break
                if match:
                    consolidated = slots_in_quarter

        if consolidated == 1 and i % slots_in_eighth == 0 and i + slots_in_eighth <= subdivision:
            blocked = any(
                (i + j in doubled_slots) or (i + j in buzz_span_slots) or (i + j in buzz_start_map)
                for j in range(1, slots_in_eighth)
            )
            if not blocked:
                match = True
                for j in range(1, slots_in_eighth):
                    if pos_map.get(Fraction(i + j, subdivision)):
                        match = False
                        break
                if match:
                    consolidated = slots_in_eighth

        duration = str(beat_unit * subdivision // (consolidated * beats_per_bar))
        token = _format_hits(hits, duration)
        token = _attach_position_markup(token, pos, cue_map, placeholder_map, dynamic_start_map, dynamic_stop_set)
        tokens.append(token)
        i += consolidated

    return " ".join(tokens)


def _drum_measure_mixed(
    events,
    beats_per_bar: int = 4,
    cue_map: dict | None = None,
    placeholder_map: dict | None = None,
    dynamic_start_map: dict | None = None,
    dynamic_stop_set: set | None = None,
) -> str:
    """Emit LilyPond for a bar that contains a mix of straight and triplet events.

    Works beat-by-beat.  A beat is "triplet" if any event in that beat falls on
    a triplet-only (1/12-grid) position; otherwise the beat is treated as
    straight (up to two 8th-note slots).
    """
    pos_map: dict[Fraction, list[tuple[str, set[str]]]] = defaultdict(list)
    for event in events:
        ly_name = _INSTRUMENT_TO_LY.get(event.instrument, event.instrument.lower())
        pos_map[event.beat_position].append((ly_name, set(event.modifiers)))

    def _attach_markup(token: str, pos: Fraction) -> str:
        return _attach_position_markup(
            token, pos, cue_map, placeholder_map, dynamic_start_map, dynamic_stop_set
        )

    tokens: list[str] = []
    for beat_idx in range(beats_per_bar):
        beat_start = Fraction(beat_idx, beats_per_bar)
        beat_end = Fraction(beat_idx + 1, beats_per_bar)

        beat_positions = [p for p in pos_map if beat_start <= p < beat_end]
        is_triplet_beat = any(_is_triplet_only(p, beats_per_bar) for p in beat_positions)

        if is_triplet_beat:
            # Three equal triplet-8th slots wrapped in \tuplet 3/2 { ... }
            triplet_grid = beats_per_bar * 3
            tuplet_tokens: list[str] = []
            for slot_idx in range(3):
                slot_pos = beat_start + Fraction(slot_idx, triplet_grid)
                hits = pos_map.get(slot_pos, [])
                t = _format_hits(hits, "8")
                t = _attach_markup(t, slot_pos)
                tuplet_tokens.append(t)
            tokens.append(f"\\tuplet 3/2 {{ {' '.join(tuplet_tokens)} }}")
        else:
            # Straight beat: check whether 16th-note positions are used
            has_sixteenths = any(
                _is_sixteenth_only(p, beats_per_bar)
                for p in beat_positions
            )

            if has_sixteenths:
                # Emit four 16th notes
                sixteenth_grid = beats_per_bar * 4
                for slot_idx in range(4):
                    slot_pos = beat_start + Fraction(slot_idx, sixteenth_grid)
                    hits = pos_map.get(slot_pos, [])
                    t = _format_hits(hits, "16")
                    t = _attach_markup(t, slot_pos)
                    tokens.append(t)
            else:
                # Quarter or two 8th notes
                hits_on_beat = pos_map.get(beat_start, [])
                hits_on_and = pos_map.get(beat_start + Fraction(1, beats_per_bar * 2), [])

                if hits_on_beat and not hits_on_and:
                    t = _format_hits(hits_on_beat, "4")
                    t = _attach_markup(t, beat_start)
                    tokens.append(t)
                elif not hits_on_beat and not hits_on_and:
                    t = _attach_markup("r4", beat_start)
                    tokens.append(t)
                else:
                    t = _format_hits(hits_on_beat, "8")
                    t = _attach_markup(t, beat_start)
                    tokens.append(t)
                    and_pos = beat_start + Fraction(1, beats_per_bar * 2)
                    t = _format_hits(hits_on_and, "8")
                    t = _attach_markup(t, and_pos)
                    tokens.append(t)

    return " ".join(tokens)


def _drum_measure(
    events,
    subdivision: int,
    beats_per_bar: int = 4,
    beat_unit: int = 4,
    cue_map: dict | None = None,
    placeholder_map: dict | None = None,
    dynamic_start_map: dict | None = None,
    dynamic_stop_set: set | None = None,
    forced_voice_split_ids: set | None = None,
) -> str:
    """Emit LilyPond notation for one bar.

    Dispatches to ``_drum_measure_mixed`` when any event sits on a triplet-only
    position; otherwise uses the straight slot-based approach.
    """
    if any(_is_triplet_only(e.beat_position, beats_per_bar) for e in events):
        return _drum_measure_mixed(events, beats_per_bar, cue_map, placeholder_map, dynamic_start_map, dynamic_stop_set)
    return _drum_measure_straight(
        events, subdivision, beats_per_bar, beat_unit,
        cue_map, placeholder_map, dynamic_start_map, dynamic_stop_set,
        forced_voice_split_ids,
    )


def _collect_tied_buzz_voice_split_ids(bars: list[IRBar]) -> set[int]:
    """Return the Event ids that must render inside a voice-split.

    A tied buzz chain is the head (``tied_to_next=True``) plus each
    continuation (``tied_from_prev=True``) in subsequent bars. If any
    piece of the chain has foot-played overlap during its buzz span,
    LilyPond's tie would span different voice contexts and get dropped;
    to prevent that, every piece of the chain is wrapped in a matching
    voice-split (with rests in the second voice where there's no foot
    overlap).
    """
    # Map bar.number → list of Event objects for quick lookup.
    by_bar: dict[int, list] = {bar.number: list(bar.events) for bar in bars}

    def _has_foot_overlap(event) -> bool:
        start = event.beat_position
        end = start + event.duration
        for other in by_bar.get(event.bar, []):
            if other is event:
                continue
            if other.instrument not in _FOOT_INSTRUMENTS_LY:
                continue
            if start <= other.beat_position < end:
                return True
        return False

    forced: set[int] = set()
    seen: set[int] = set()
    for bar in bars:
        for event in bar.events:
            if id(event) in seen:
                continue
            if event.duration is None or "buzz" not in event.modifiers:
                continue
            if not getattr(event, "tied_to_next", False) and not getattr(
                event, "tied_from_prev", False
            ):
                continue
            # Walk backward to the head of the chain.
            # (Always process from the head, so skip non-heads on first pass.)
            if getattr(event, "tied_from_prev", False):
                continue
            # Build the chain forward from this head.
            chain: list = [event]
            cursor = event
            bar_index = next(i for i, b in enumerate(bars) if b.number == cursor.bar)
            while getattr(cursor, "tied_to_next", False) and bar_index + 1 < len(bars):
                next_bar = bars[bar_index + 1]
                nxt = None
                for e in next_bar.events:
                    if (
                        e.duration is not None
                        and "buzz" in e.modifiers
                        and getattr(e, "tied_from_prev", False)
                        and e.beat_position == Fraction(0)
                    ):
                        nxt = e
                        break
                if nxt is None:
                    break
                chain.append(nxt)
                cursor = nxt
                bar_index += 1
            seen.update(id(e) for e in chain)
            if any(_has_foot_overlap(e) for e in chain):
                forced.update(id(e) for e in chain)
    return forced


def _header_block(title: str | None) -> str:
    # Suppress LilyPond's default tagline (which renders only on the last
    # page). The "Made with groovescript" footer is emitted on every page
    # via oddFooterMarkup / evenFooterMarkup in the paper block instead.
    if title is None:
        return "\\header {\n  tagline = ##f\n}\n\n"
    return (
        "\\header {\n"
        f'  title = "{_ly_str(title)}"\n'
        "  tagline = ##f\n"
        "}\n\n"
    )


def _score_header_block(tempo: int | None, time_signature: str) -> str:
    if tempo is None:
        subtitle = f"Time Signature: {time_signature}"
    else:
        subtitle = f"Tempo: {tempo}    Time Signature: {time_signature}"
    return (
        "\\header {\n"
        f'  subtitle = "{_ly_str(subtitle)}"\n'
        "}\n"
    )




def _score_prelude(tempo: int | None, time_signature: str, suppress_metronome_mark: bool = False) -> str:
    _, beat_unit = _parse_time_signature(time_signature)
    if tempo is not None:
        # Suppress the MetronomeMark grob — tempo is displayed in the first
        # section header instead (to the right of the rehearsal mark box).
        tempo_line = (
            f"      \\omit Score.MetronomeMark\n"
            f"      \\tempo {beat_unit} = {tempo}\n"
        )
    elif suppress_metronome_mark:
        # No global tempo, but per-section \tempo commands will be emitted;
        # suppress the automatic metronome mark so they don't render visually.
        tempo_line = "      \\omit Score.MetronomeMark\n"
    else:
        tempo_line = ""
    return (
        "    \\drummode {\n"
        "      \\numericTimeSignature\n"
        f"      \\time {time_signature}\n"
        f"{tempo_line}"
    )


def _section_mark(
    bar: IRBar,
    override_repeat_times: int | None = None,
    tempo_str: str | None = None,
    bar_text: str | None = None,
) -> str:
    repeat_times = override_repeat_times if override_repeat_times is not None else bar.repeat_times

    has_section = bar.section_name is not None
    has_repeat = repeat_times is not None and repeat_times > 1

    if not has_section and not has_repeat:
        return ""

    section_box = (
        f'\\override #\'(box-padding . 0.5) \\box \\bold \\fontsize #-1'
        f' {{ "{_ly_str(bar.section_name.upper())}: {bar.section_bars}" }}'
    ) if has_section else None

    play_markup = f'\\italic \\fontsize #-1 "Play {repeat_times}x"' if has_repeat else None

    # Optional bar_text annotation — merged into the column so we emit a
    # single \mark and avoid LilyPond's "conflicting ad-hoc-mark-event" warning.
    bar_text_markup: str | None = None
    if bar_text:
        escaped = _ly_str(bar_text)
        bar_text_markup = f'\\italic \\fontsize #-1 "{escaped}"'

    # Collect all markup fragments and decide layout.
    # When multiple elements are present they are stacked in a \column.
    parts: list[str] = []
    if tempo_str:
        parts.append(f"\\fontsize #-1 \\concat {{ {tempo_str} }}")
    if section_box:
        parts.append(section_box)
    if bar_text_markup:
        parts.append(bar_text_markup)
    if play_markup:
        parts.append(play_markup)

    if len(parts) == 1:
        markup_content = parts[0]
    else:
        markup_content = "\\column { " + " \\vspace #0.3 ".join(parts) + " }"

    if has_section and has_repeat:
        break_align = "#'(staff-bar)"
    elif has_section:
        break_align = "#'(left-edge)"
    else:
        break_align = "#'(staff-bar)"

    # Play-only marks (no section label) sit closer to the staff than section
    # boxes so that when both occur on adjacent bars LilyPond's outside-staff
    # stacker keeps the section header visually above the "Play Nx" indicator.
    priority_line = ""
    if has_repeat and not has_section:
        priority_line = "      \\once \\override Score.RehearsalMark.outside-staff-priority = #1000\n"

    return (
        "      \\once \\override Score.RehearsalMark.self-alignment-X = #LEFT\n"
        f"      \\once \\override Score.RehearsalMark.break-align-symbols = {break_align}\n"
        "      \\once \\override Score.RehearsalMark.padding = #2\n"
        f"{priority_line}"
        f"      \\mark \\markup {markup_content}\n"
    )


def _whole_bar_skip(beats_per_bar: int, beat_unit: int) -> str:
    """Return the LilyPond token for a whole-bar invisible skip (``s``).

    A skip occupies the same time as a rest but renders no glyph — used for
    placeholder groove bars in minimal charts, where the section has a bar
    count but no groove yet. The staff lines remain visible; the measure is
    otherwise empty.
    """
    from fractions import Fraction as _Frac
    bar_dur = _Frac(beats_per_bar, beat_unit)
    _DUR_MAP = {
        _Frac(1, 1): "1",
        _Frac(3, 4): "2.",
        _Frac(1, 2): "2",
        _Frac(1, 4): "4",
    }
    dur_str = _DUR_MAP.get(bar_dur)
    if dur_str is not None:
        return f"s{dur_str}"
    return f"s{beat_unit}*{beats_per_bar}"


def _whole_bar_rest(beats_per_bar: int, beat_unit: int) -> str:
    """Return the LilyPond token for a whole-bar rest.

    Uses LilyPond's full-bar rest notation: R followed by the duration that
    fills a complete bar.  For 4/4 that is R1; for 3/4 or 6/8 that is R2.;
    for compound/odd meters like 12/8 or 10/8 we fall back to the generic
    scaled form ``R{beat_unit}*{beats_per_bar}`` (e.g. ``R8*12``) which
    LilyPond accepts as a full-bar rest.
    """
    # Duration of a whole bar in LilyPond units: (beats_per_bar / beat_unit) as a fraction.
    # LilyPond duration integer is the denominator of the note value (1 = whole, 2 = half, …).
    # beats_per_bar/beat_unit == 1   → R1
    # beats_per_bar/beat_unit == 3/4 → R2. (dotted half)
    # beats_per_bar/beat_unit == 1/2 → R2
    from fractions import Fraction as _Frac
    bar_dur = _Frac(beats_per_bar, beat_unit)
    # Common mappings — preserved verbatim so existing fixtures diff-match.
    _DUR_MAP = {
        _Frac(1, 1): "1",
        _Frac(3, 4): "2.",
        _Frac(1, 2): "2",
        _Frac(1, 4): "4",
    }
    dur_str = _DUR_MAP.get(bar_dur)
    if dur_str is not None:
        return f"R{dur_str}"
    # Generic fallback: one rest per beat-unit note, scaled by beats_per_bar.
    # For 12/8 this emits R8*12; for 10/8 → R8*10; for 7/16 → R16*7.
    return f"R{beat_unit}*{beats_per_bar}"


def _bar_text_markup(text: str) -> str:
    """Emit a LilyPond markup string for a bar-level text annotation (placed at bar start)."""
    escaped = _ly_str(text)
    return (
        "\\once \\override Score.RehearsalMark.self-alignment-X = #LEFT\n"
        "      \\once \\override Score.RehearsalMark.break-align-symbols = #'(left-edge)\n"
        f'      \\mark \\markup {{ \\fontsize #-1 "{escaped}" }}'
    )


class _BarGroupState:
    """Running state for ``_group_bars``: tempo display, tempo command, and meter.

    Callers invoke ``compute_time_signature_change`` and ``compute_tempo_info``
    per bar; both mutate state to reflect what has been emitted so far.
    """

    def __init__(
        self,
        is_top_level: bool,
        beats_per_bar: int,
        beat_unit: int,
        global_tempo: int | None,
        global_time_signature: str,
    ) -> None:
        self.is_top_level = is_top_level
        # Track the last tempo shown in a section mark (to avoid duplicate display).
        self.last_shown_tempo: int | None = None
        # Track the last tempo emitted via \tempo command (global_tempo was set by _score_prelude).
        self.last_emitted_tempo: int | None = global_tempo
        # Track the currently-active time signature (global_time_signature was
        # set in the score prelude; per-section overrides cause mid-staff changes).
        self.current_ts: str = global_time_signature
        self.current_bpb: int = beats_per_bar
        self.current_beat_unit: int = beat_unit

    def compute_tempo_info(self, bar: IRBar) -> tuple[str | None, str]:
        """Return (tempo_str_for_mark, tempo_change_cmd) for a bar.

        tempo_str_for_mark is non-None when the bar's effective tempo differs
        from what was last shown in a section mark.
        tempo_change_cmd is a non-empty \\tempo command string when the bar's
        effective tempo differs from the last \\tempo emitted in the stream.
        """
        effective = bar.tempo
        if not self.is_top_level or effective is None:
            return None, ""

        tempo_str: str | None = None
        if effective != self.last_shown_tempo:
            tempo_str = f'\\note {{ {self.current_beat_unit} }} #1 " = {effective}"'
            self.last_shown_tempo = effective

        tempo_change_cmd = ""
        if effective != self.last_emitted_tempo:
            tempo_change_cmd = f"      \\tempo {self.current_beat_unit} = {effective}\n"
            self.last_emitted_tempo = effective

        return tempo_str, tempo_change_cmd

    def compute_time_signature_change(self, bar: IRBar) -> str:
        """Return a ``\\time N/M`` command when the bar's effective time
        signature differs from the currently-active one, otherwise an empty
        string. Updates ``current_ts`` / ``current_bpb`` / ``current_beat_unit``
        as a side effect so later code sees the new meter.
        """
        bar_ts = bar.time_signature or self.current_ts
        if bar_ts == self.current_ts:
            return ""
        self.current_ts = bar_ts
        self.current_bpb, self.current_beat_unit = _parse_time_signature(bar_ts)
        return f"      \\time {bar_ts}\n"


def _group_bars(
    bars: list[IRBar],
    is_top_level: bool = True,
    beats_per_bar: int = 4,
    beat_unit: int = 4,
    global_tempo: int | None = None,
    global_time_signature: str = "4/4",
    forced_voice_split_ids: set | None = None,
    compact: bool = False,
) -> list[str]:
    measures: list[str] = []
    i = 0
    state = _BarGroupState(
        is_top_level=is_top_level,
        beats_per_bar=beats_per_bar,
        beat_unit=beat_unit,
        global_tempo=global_tempo,
        global_time_signature=global_time_signature,
    )

    while i < len(bars):
        bar = bars[i]

        # 1. Handle explicit phrase repeats
        if is_top_level and bar.repeat_times is not None and bar.repeat_times > 1:
            num_repeats = bar.repeat_times
            phrase_end = i + 1
            while phrase_end < len(bars):
                if bars[phrase_end].repeat_index == 2:
                    break
                phrase_end += 1
            phrase_length = phrase_end - i
            pattern_bars = bars[i : i + phrase_length]

            ts_change_cmd = state.compute_time_signature_change(bar)
            cur_tempo_str, tempo_change_cmd = state.compute_tempo_info(bar)
            mark = _section_mark(bar, tempo_str=cur_tempo_str, bar_text=bar.bar_text)
            forced_bar = "      \\bar \".|:\"\n" if i == 0 else ""
            inner_measures = _group_bars(
                pattern_bars,
                is_top_level=False,
                beats_per_bar=state.current_bpb,
                beat_unit=state.current_beat_unit,
                global_time_signature=state.current_ts,
                forced_voice_split_ids=forced_voice_split_ids,
            )
            inner_body = "\n".join(inner_measures)
            measures.append(f"{ts_change_cmd}{tempo_change_cmd}{mark}{forced_bar}      \\repeat volta {num_repeats} {{\n{inner_body}\n      }}")
            i += num_repeats * phrase_length
            continue

        # 2a. Placeholder groove bars (section has bars: but no groove:).
        # Each bar renders as an invisible skip so the measure shows empty
        # staff lines with no notes or rests; the first bar carries a boxed
        # "Section groove" label, plus any user-declared fill placeholders
        # for that bar (stacked above the skip).
        if is_top_level and bar.is_placeholder_groove:
            ts_change_cmd = state.compute_time_signature_change(bar)
            cur_tempo_str, tempo_change_cmd = state.compute_tempo_info(bar)
            skip_token = _whole_bar_skip(state.current_bpb, state.current_beat_unit)
            for _, label in bar.fill_placeholders:
                escaped = _ly_str(label)
                skip_token = (
                    f'{skip_token}^\\markup {{ \\bold \\box '
                    f'\\fontsize #-1 "{escaped}" }}'
                )
            mark = _section_mark(bar, tempo_str=cur_tempo_str, bar_text=bar.bar_text)
            measures.append(
                f"{ts_change_cmd}{tempo_change_cmd}{mark}      {skip_token} |"
            )
            i += 1
            continue

        # 2. Whole-bar rest bars (play: rest items)
        if is_top_level and bar.is_rest:
            ts_change_cmd = state.compute_time_signature_change(bar)
            cur_tempo_str, tempo_change_cmd = state.compute_tempo_info(bar)
            rest_token = _whole_bar_rest(state.current_bpb, state.current_beat_unit)
            # Count consecutive rest bars to collapse into a multi-measure rest block
            num_rests = 1
            while i + num_rests < len(bars):
                nb = bars[i + num_rests]
                if not nb.is_rest:
                    break
                if is_top_level and nb.section_name is not None:
                    break
                # Time signature change ends the rest run so we can emit a
                # new \time command before the next block.
                if (nb.time_signature or state.current_ts) != state.current_ts:
                    break
                num_rests += 1
            mark = _section_mark(bar, override_repeat_times=num_rests if num_rests > 1 else None, tempo_str=cur_tempo_str, bar_text=bar.bar_text) if is_top_level else ""
            if num_rests > 1:
                forced_bar = "      \\bar \".|:\"\n" if i == 0 else ""
                measures.append(f"{ts_change_cmd}{tempo_change_cmd}{mark}{forced_bar}      \\repeat volta {num_rests} {{\n        {rest_token} |\n      }}")
            else:
                measures.append(f"{ts_change_cmd}{tempo_change_cmd}{mark}      {rest_token} |")
            i += num_rests
            continue

        # Compute any pending \time change before we start consolidating
        # identical bars so the emitted \time command sits just before this
        # bar's measure. This also updates current_bpb/current_beat_unit.
        ts_change_cmd = state.compute_time_signature_change(bar)

        # 3. Implicit/Post-hoc grouping — only group identical bars with no cues/bar_text
        current_bar_num = bars[i].number
        if compact:
            # In compact mode ignore phrase-boundary chunking so a long run of
            # identical bars collapses into a single repeat block. All other
            # boundaries (section, rest, subdivision, time signature, cues,
            # fills, bar text, dynamics, event diffs) are still honoured by
            # the per-step checks in the lookahead loop below.
            max_lookahead = len(bars) - i
        else:
            remaining_in_phrase = state.current_bpb - ((current_bar_num - 1) % state.current_bpb)
            max_lookahead = min(len(bars) - i, remaining_in_phrase)

        # Bars with cues, fill_placeholders, bar_text, or dynamic annotations cannot be implicitly merged into repeats
        has_annotations = bool(bar.cues or bar.fill_placeholders or bar.bar_text or bar.dynamic_starts or bar.dynamic_stops)
        # Build cue_map and placeholder_map for beat-accurate markup placement (pos → text)
        cue_map: dict[Fraction, str] | None = dict(bar.cues) if bar.cues else None
        placeholder_map: dict[Fraction, str] | None = dict(bar.fill_placeholders) if bar.fill_placeholders else None

        # Build dynamic maps for hairpin placement
        dynamic_start_map: dict[Fraction, str] | None = None
        dynamic_stop_set: set[Fraction] | None = None
        if bar.dynamic_starts:
            dynamic_start_map = {pos: kind for pos, kind in bar.dynamic_starts}
        if bar.dynamic_stops:
            # Resolve Fraction(-1) sentinel ("end of bar") to the position of
            # the last event in the bar, so the terminator attaches to a real note.
            resolved_stops: set[Fraction] = set()
            for stop_pos in bar.dynamic_stops:
                if stop_pos == Fraction(-1):
                    if bar.events:
                        resolved_stops.add(max(e.beat_position for e in bar.events))
                    else:
                        resolved_stops.add(Fraction(state.current_bpb - 1, state.current_bpb))
                else:
                    resolved_stops.add(stop_pos)
            dynamic_stop_set = resolved_stops

        num_identical = 1
        bar_measure = _drum_measure(bar.events, bar.subdivision, state.current_bpb, state.current_beat_unit, cue_map, placeholder_map, dynamic_start_map, dynamic_stop_set, forced_voice_split_ids)
        if not has_annotations:
            for k in range(1, max_lookahead):
                next_bar = bars[i + k]
                if is_top_level and next_bar.section_name is not None:
                    break
                if next_bar.is_rest:
                    break
                if next_bar.subdivision != bar.subdivision:
                    break
                # Don't merge across a time-signature change.
                if (next_bar.time_signature or state.current_ts) != state.current_ts:
                    break
                if next_bar.cues or next_bar.fill_placeholders or next_bar.bar_text:
                    break
                if next_bar.dynamic_starts or next_bar.dynamic_stops:
                    break
                if _drum_measure(next_bar.events, next_bar.subdivision, state.current_bpb, state.current_beat_unit, forced_voice_split_ids=forced_voice_split_ids) != bar_measure:
                    break
                num_identical += 1

        cur_tempo_str, tempo_change_cmd = state.compute_tempo_info(bar)
        mark = _section_mark(bar, override_repeat_times=num_identical if num_identical > 1 else None, tempo_str=cur_tempo_str, bar_text=bar.bar_text) if is_top_level else ""

        # Emit bar_text annotation if present — but only as a standalone \mark
        # when there is no section mark to absorb it (bar_text is merged into
        # the section mark's \column to avoid duplicate \mark warnings).
        bar_text_line = f"      {_bar_text_markup(bar.bar_text)}\n" if bar.bar_text and not mark else ""

        if num_identical > 1:
            forced_bar = "      \\bar \".|:\"\n" if i == 0 and is_top_level else ""
            measures.append(f"{ts_change_cmd}{tempo_change_cmd}{mark}{forced_bar}      \\repeat volta {num_identical} {{\n        {bar_measure} |\n      }}")
            i += num_identical
        else:
            measures.append(f"{ts_change_cmd}{tempo_change_cmd}{mark}{bar_text_line}      {bar_measure} |")
            i += 1

    return measures


def emit_lilypond(ir: IRGroove | IRSong, *, compact: bool = False) -> str:
    """Emit LilyPond source for either a groove or an arranged song.

    When ``compact`` is true, runs of identical bars collapse into one repeat
    block even across implicit 4-bar phrase boundaries. Explicit section-level
    ``repeat: N`` blocks, section boundaries, fills, variations, cues, bar
    text, dynamic spans, and time-signature changes are still respected.
    """
    if isinstance(ir, IRGroove):
        bars = [
            IRBar(
                number=bar_number,
                subdivision=ir.subdivision,
                events=[event for event in ir.events if event.bar == bar_number],
                repeat_index=1,
            )
            for bar_number in range(1, ir.bars + 1)
        ]
        title = None
        tempo = None
        time_signature = "4/4"
    else:
        bars = ir.bars
        title = ir.metadata.title
        tempo = ir.metadata.tempo
        time_signature = ir.metadata.time_signature

    beats_per_bar, beat_unit = _parse_time_signature(time_signature)

    # Determine whether any bar carries a tempo (global or per-section).
    # This is used to suppress LilyPond's automatic MetronomeMark grob when
    # per-section \tempo commands will be emitted but no global tempo is set.
    has_any_tempo = tempo is not None or any(b.tempo is not None for b in bars)

    forced_voice_split_ids = _collect_tied_buzz_voice_split_ids(bars)

    measures = _group_bars(
        bars,
        beats_per_bar=beats_per_bar,
        beat_unit=beat_unit,
        global_tempo=tempo,
        global_time_signature=time_signature,
        forced_voice_split_ids=forced_voice_split_ids,
        compact=compact,
    )
    body = "\n".join(measures)

    template = _TEMPLATE_PATH.read_text()
    return (
        template
        .replace("{{HEADER}}", _header_block(title))
        .replace("{{SCORE_HEADER}}", _score_header_block(tempo, time_signature))
        .replace("{{SCORE_PRELUDE}}", _score_prelude(tempo, time_signature, suppress_metronome_mark=has_any_tempo))
        .replace("{{BODY}}", body)
    )
