from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from fractions import Fraction
from math import gcd, lcm

from .ast_nodes import (
    BeatHit,
    Cue,
    DynamicSpan,
    Fill,
    FillBar,
    FillPlaceholder,
    Groove,
    InheritSpec,
    InstrumentHit,
    Metadata,
    PatternLine,
    PlayBar,
    PlayGroove,
    PlayRest,
    Section,
    Song,
    StarSpec,
    Variation,
    VariationAction,
)

# Maps a beat-label suffix to its fractional offset within a single beat.
# Used by ``_beat_label_to_fraction`` to compute Fraction positions that work
# regardless of the bar's subdivision — triplet and straight labels can coexist.
_SUFFIX_BEAT_FRACTION: dict[str, Fraction] = {
    "": Fraction(0),
    "e": Fraction(1, 4),   # 16th: first subdivision of a beat
    "&": Fraction(1, 2),   # 8th: halfway through a beat
    "a": Fraction(3, 4),   # 16th: third subdivision of a beat
    "t": Fraction(1, 3),   # triplet: first third of a beat
    "l": Fraction(2, 3),   # triplet: second third of a beat
}


def _beats_per_bar(time_signature: str) -> int:
    """Extract the beats-per-bar from a time signature string like '3/4' or '6/8'."""
    numerator, _ = time_signature.split("/")
    return int(numerator)


def _beat_unit(time_signature: str) -> int:
    """Extract the beat unit (denominator) from a time signature string like '3/4'."""
    _, denominator = time_signature.split("/")
    return int(denominator)


@dataclass
class Event:
    """A single drum hit in the intermediate representation.

    ``duration`` is ``None`` for ordinary point events. Buzz rolls set
    ``duration`` to the span's length as a bar-relative ``Fraction`` (e.g. a
    half-note buzz in 4/4 has ``duration = Fraction(1, 2)``); the emitter then
    renders a single tremolo note over that span and skips the slots it
    consumes.
    """

    bar: int
    beat_position: Fraction
    instrument: str
    modifiers: list[str] = field(default_factory=list)
    duration: Fraction | None = None
    buzz_duration: str | None = None  # original duration string for LilyPond emission (e.g. "4", "2d")
    # True when this buzz event ties into a continuation in the next bar.
    # Set by ``_split_cross_bar_buzz_events`` after arrangement is complete;
    # the LilyPond emitter renders a ``~`` after the buzz token so the
    # tremolo continues across the barline.
    tied_to_next: bool = False
    # True when this buzz event is the tail of a tie started in the
    # previous bar. Used by the LilyPond emitter to keep voice-split
    # decisions consistent across the chain (a tie into a voice split
    # must be preceded by a matching voice split, else LilyPond drops
    # the tie).
    tied_from_prev: bool = False
    # 1-indexed source line of the pattern line or variation action that
    # produced this event, threaded through from the AST for diagnostics.
    source_line: int | None = None


@dataclass
class IRGroove:
    """Compiled IR for a groove definition."""

    name: str
    subdivision: int  # first-bar subdivision (legacy single-grid shim)
    bars: int
    events: list[Event]
    # Per-bar subdivision grid. ``bar_subdivisions[i]`` is the grid for
    # groove bar ``i + 1``. Used so multi-bar grooves can vary their grid
    # across bars (e.g. triplet bar followed by 16th bar).
    bar_subdivisions: list[int] = field(default_factory=list)


@dataclass
class IRSection:
    """Compiled arrangement section."""

    name: str
    start_bar: int
    bars: int
    tempo: int | None = None  # effective tempo for this section (per-section override or global)


@dataclass
class IRBar:
    """One arranged bar of drum events."""

    number: int
    subdivision: int
    events: list[Event]
    section_name: str | None = None
    section_bars: int | None = None
    repeat_times: int | None = None  # if not None, start of a repeat block
    repeat_index: int | None = None  # which iteration of the repeat this is
    cues: list[tuple[Fraction, str]] = field(default_factory=list)  # (beat_position, text)
    fill_placeholders: list[tuple[Fraction, str]] = field(default_factory=list)  # (beat_position, label)
    bar_text: str | None = None  # free-form bar-level text annotation
    tempo: int | None = None  # effective tempo for this bar
    time_signature: str | None = None  # effective time signature for this bar
    is_rest: bool = False  # whole-bar rest (play: rest item)
    # Dynamic hairpin annotations: list of (beat_position, kind) where kind is "cresc" or "decresc"
    dynamic_starts: list[tuple[Fraction, str]] = field(default_factory=list)
    # Hairpin terminators: list of beat_position where a \! should be placed
    dynamic_stops: list[Fraction] = field(default_factory=list)


@dataclass
class IRSong:
    """Compiled song arrangement IR."""

    metadata: Metadata
    bars: list[IRBar]
    sections: list[IRSection]


_FRACTION_SUFFIX_LABEL: dict[Fraction, str] = {
    Fraction(0): "",
    Fraction(1, 4): "e",
    Fraction(1, 2): "&",
    Fraction(3, 4): "a",
    Fraction(1, 3): "t",
    Fraction(2, 3): "l",
}


def _beat_label_for(pos: Fraction, beats_per_bar: int = 4) -> str:
    """Format a bar-relative position back to a beat label for diagnostics.

    Falls back to ``beat=<fraction>`` if the position lands on an uncommon
    subdivision that does not correspond to a known suffix.
    """
    beat_offset = pos * beats_per_bar
    beat_num = int(beat_offset) + 1
    suffix_frac = beat_offset - (beat_num - 1)
    suffix = _FRACTION_SUFFIX_LABEL.get(suffix_frac)
    if suffix is None:
        return f"beat position {beat_offset}"
    return f"beat {beat_num}{suffix}"


def _beat_label_to_fraction(label: str, subdivision: int, beats_per_bar: int = 4) -> Fraction:
    """Convert a beat label like ``"2&"`` or ``"3t"`` to a bar-relative Fraction.

    Position is computed directly from the suffix's fractional offset within a
    beat, so triplet and straight labels can coexist in the same bar regardless
    of the bar's overall subdivision.  The *subdivision* parameter is accepted
    for backward compatibility but is no longer used.
    """
    # Handle verbose triplet suffixes: 1trip, 1let
    if label.endswith("trip"):
        beat_num = int(label[:-4])
        suffix = "t"
    elif label.endswith("let"):
        beat_num = int(label[:-3])
        suffix = "l"
    elif len(label) > 1 and label[-1] in "e&atl":
        beat_num = int(label[:-1])
        suffix = label[-1]
    else:
        beat_num = int(label)
        suffix = ""

    if beat_num < 1 or beat_num > beats_per_bar:
        raise ValueError(
            f"Beat number {beat_num} is out of range for {beats_per_bar} beats per bar"
        )

    suffix_frac = _SUFFIX_BEAT_FRACTION.get(suffix)
    if suffix_frac is None:
        raise ValueError(f"Unknown beat suffix '{suffix}' in label '{label}'")

    return (Fraction(beat_num - 1) + suffix_frac) / beats_per_bar


# Valid buzz-roll note values (denominator of the note). Dotted / double-dotted
# variants are accepted on top of each of these.
_VALID_BUZZ_NOTE_VALUES: frozenset[int] = frozenset({1, 2, 4, 8, 16})

# Instruments that are foot-played — these may overlap a snare buzz roll.
_FOOT_INSTRUMENTS: frozenset[str] = frozenset({"BD", "HF"})

# Instruments that are hand-played — these cannot overlap a snare buzz roll.
_HAND_INSTRUMENTS: frozenset[str] = frozenset({
    "HH", "OH", "RD", "CR", "FT", "HT", "MT", "SCS", "SN",
})

# Instruments that support the flam modifier (grace-note ornament).
_FLAM_INSTRUMENTS: frozenset[str] = frozenset({"SN", "FT", "HT", "MT"})


def _parse_buzz_duration(spec: str) -> tuple[int, int]:
    """Parse a buzz duration like ``"4"``, ``"2d"``, ``"2dd"`` into (note_value, dots).

    Raises ``ValueError`` for invalid specs (unknown note value, too many dots,
    or note value not in the supported whitelist).
    """
    dots = 0
    while spec.endswith("d"):
        dots += 1
        spec = spec[:-1]
    if dots > 2:
        raise ValueError(
            f"buzz duration: too many dots (got {dots}, maximum is 2)"
        )
    if not spec or not spec.isdigit():
        raise ValueError(f"buzz duration: missing or invalid note value {spec!r}")
    note_value = int(spec)
    if note_value not in _VALID_BUZZ_NOTE_VALUES:
        raise ValueError(
            f"buzz duration: note value {note_value} not supported "
            f"(valid values: {sorted(_VALID_BUZZ_NOTE_VALUES)})"
        )
    return note_value, dots


def _buzz_span(
    buzz_duration: str, beats_per_bar: int, beat_unit: int
) -> Fraction:
    """Return the span of a buzz roll as a bar-relative ``Fraction``.

    A ``buzz:N`` occupies ``1/N`` of a whole note, which is
    ``(beat_unit / N) / beats_per_bar`` of a bar. Dotted variants multiply
    by ``(2 - 1/2**dots)``.
    """
    note_value, dots = _parse_buzz_duration(buzz_duration)
    base = Fraction(beat_unit, note_value) / beats_per_bar
    if dots:
        # 1 dot → × 3/2; 2 dots → × 7/4; general: 2 - 1/2^dots.
        multiplier = Fraction(2) - Fraction(1, 2**dots)
        return base * multiplier
    return base


def _validate_buzz_modifier_compat(modifiers: list[str], context: str) -> None:
    """Reject buzz combined with incompatible modifiers."""
    if "buzz" not in modifiers:
        return
    for bad in ("flam", "drag", "double", "ghost"):
        if bad in modifiers:
            raise ValueError(
                f"'buzz' modifier is incompatible with {bad!r} in {context}"
            )


def _validate_buzz_event(
    event: Event, beats_per_bar: int, context: str
) -> None:
    """Validate a single buzz event's instrument.

    Position/span validation is intentionally relaxed: a buzz roll may extend
    past the end of its bar and tie across the barline. The cross-bar split
    happens after arrangement (see ``_split_cross_bar_buzz_events``); a buzz
    that runs past the end of the song is rejected there because that is the
    first place we know the song's length.
    """
    if event.duration is None:
        return
    if event.instrument != "SN":
        raise ValueError(
            f"'buzz' modifier is only supported on SN (snare) — got "
            f"{event.instrument!r} in {context}"
        )


def _validate_buzz_overlap(events: list[Event], context: str) -> None:
    """Reject hand-played events that overlap a snare buzz span.

    Foot-played events (BD, HF) may coexist with a buzz — the emitter handles
    these via a voice split when necessary.
    """
    buzz_events = [e for e in events if e.duration is not None and "buzz" in e.modifiers]
    if not buzz_events:
        return
    for buzz in buzz_events:
        start = buzz.beat_position
        end = buzz.beat_position + buzz.duration
        for other in events:
            if other is buzz:
                continue
            if other.bar != buzz.bar:
                continue
            if not (start <= other.beat_position < end):
                continue
            # Allow the buzz's own start-position stacking (e.g. an accent
            # on the same slot on another instrument is fine if that
            # instrument is foot-played).
            if other.instrument in _FOOT_INSTRUMENTS:
                continue
            if other.instrument in _HAND_INSTRUMENTS:
                raise ValueError(
                    f"{other.instrument} event at beat position "
                    f"{other.beat_position} overlaps a snare buzz roll span "
                    f"[{start}, {end}) in {context}"
                )


def _validate_double_modifier(modifiers: list[str], subdivision: int, context: str) -> None:
    """Raise ValueError if the 'double' modifier is used in an invalid context.

    - Only valid at 16th-note subdivision (4 slots per beat).
    - Incompatible with 'flam' or 'drag' (mutually exclusive ornaments).
    """
    if "double" not in modifiers:
        return
    subdivisions_per_beat = subdivision // 4  # assumes beats_per_bar=4; adjusted below if needed
    # We check subdivision directly: must be exactly 16 for 4/4 or the slots-per-beat must be 4.
    # Since subdivision is the total bar slots, we verify slots-per-beat == 4 elsewhere; here we
    # simply require subdivision % 4 == 0 and subdivision // beats_per_bar == 4 (16ths).
    # The caller passes the full bar subdivision; we require slots-per-beat == 4.
    # (beats_per_bar is not available here, but we can check against the known valid values.)
    # We delegate the per-beat check to compile_groove; here we validate incompatible modifiers.
    if "flam" in modifiers:
        raise ValueError(f"'double' modifier is incompatible with 'flam' in {context}")
    if "drag" in modifiers:
        raise ValueError(f"'double' modifier is incompatible with 'drag' in {context}")


def _validate_double_subdivision(subdivision: int, beats_per_bar: int, context: str) -> None:
    """Raise ValueError if 'double' modifier is used at a non-16th subdivision."""
    slots_per_beat = subdivision // beats_per_bar
    if slots_per_beat != 4:
        raise ValueError(
            f"'double' modifier requires 16th-note subdivision "
            f"(4 slots per beat), but got {slots_per_beat} slots per beat "
            f"(subdivision={subdivision}, beats_per_bar={beats_per_bar}) in {context}"
        )


def _validate_flam_instrument(instrument: str, modifiers: list[str], context: str) -> None:
    """Raise ValueError if 'flam' is used on an instrument that doesn't support it."""
    if "flam" not in modifiers:
        return
    if instrument not in _FLAM_INSTRUMENTS:
        raise ValueError(
            f"'flam' modifier is only supported on snare and toms "
            f"(SN, FT, HT, MT) — got {instrument!r} in {context}"
        )


def _star_hits_per_bar(
    star: StarSpec, beats_per_bar: int, beat_unit: int, context: str
) -> int:
    """Return the number of hits a ``*N``/``*Nt`` produces in one bar.

    Raises :class:`ValueError` if the star is incompatible with the time
    signature (e.g. ``*2`` in 6/8 produces a non-integer number of half-notes
    per bar).
    """
    n = star.note_value
    if star.triplet:
        numerator = beats_per_bar * n * 3
        denominator = 2 * beat_unit
    else:
        numerator = beats_per_bar * n
        denominator = beat_unit
    if numerator % denominator != 0:
        raise ValueError(
            f"{star} does not fit {beats_per_bar}/{beat_unit} evenly in {context}"
        )
    return numerator // denominator


def _star_min_slots_per_beat(star: StarSpec, beat_unit: int) -> int:
    """Smallest slots-per-beat that can place every hit of ``star`` on a slot.

    For straight ``*N``: min = N / gcd(N, beat_unit).
    For triplet ``*Nt``: min = 3N / gcd(2*beat_unit, 3N).
    """
    n = star.note_value
    if star.triplet:
        return (3 * n) // gcd(2 * beat_unit, 3 * n)
    return n // gcd(n, beat_unit)


def _label_min_slots_per_beat(label: str) -> int:
    """Smallest slots-per-beat needed to place a beat label on a slot.

    Plain digit → 1, ``&`` → 2, ``e``/``a`` → 4, ``t``/``l`` → 3.
    """
    if not label:
        return 1
    last = label[-1]
    if last == "&":
        return 2
    if last in "ea":
        return 4
    if last in "tl":
        return 3
    return 1


def _infer_subdivision_from_labels(labels: list[str], beats_per_bar: int) -> int:
    """Infer a bar subdivision from a list of beat labels.

    Triplet suffixes (``t``/``l`` or ``trip``/``let``) force a 3-per-beat
    grid, 16th suffixes (``e``/``a``) force a 4-per-beat grid, otherwise the
    grid is 2 per beat.  When triplet and straight content coexist the grid
    is the LCM of their requirements (e.g. 12 per beat for triplet + 16th).
    """
    has_triplet = False
    has_sixteenth = False
    has_eighth = False
    for label in labels:
        if not label:
            continue
        if label[-1] in "tl" or label.endswith(("trip", "let")):
            has_triplet = True
        elif label[-1] in "ea":
            has_sixteenth = True
        elif label[-1] == "&":
            has_eighth = True
    if has_triplet:
        straight_needed = 4 if has_sixteenth else (2 if has_eighth else 1)
        if straight_needed > 1:
            return lcm(3, straight_needed) * beats_per_bar
        return beats_per_bar * 3
    if has_sixteenth:
        return beats_per_bar * 4
    return beats_per_bar * 2


def _buzz_min_slots_per_beat(
    buzz_duration: str, beats_per_bar: int, beat_unit: int
) -> int:
    """Smallest slots-per-beat needed so a buzz event lands on a slot boundary.

    A buzz's span is a Fraction; its start already contributes a label
    constraint, and its end position must also line up with a slot so the
    emitter can skip consumed slots cleanly.
    """
    span = _buzz_span(buzz_duration, beats_per_bar, beat_unit)
    # Span per beat = span * beats_per_bar (bar-relative span → fraction of a beat).
    # The end-position alignment requirement is that (span * beats_per_bar)
    # times slots_per_beat is an integer; i.e. slots_per_beat must be a
    # multiple of the span's denominator (when reduced as a fraction of a beat).
    per_beat = span * beats_per_bar
    return per_beat.denominator


def _infer_bar_subdivision(
    lines: list[PatternLine],
    beats_per_bar: int,
    beat_unit: int,
    context: str,
) -> int:
    """Infer the slot grid for a bar of pattern lines.

    Picks a single ``slots_per_beat`` from the set ``{1, 2, 3, 4}`` that
    accommodates every explicit label and every ``*N``/``*Nt`` star in the
    bar. Raises :class:`ValueError` if no grid fits — e.g. when triplet
    labels/stars coexist with 16th labels/stars in the same bar, or when a
    ``*N`` produces a non-integer number of hits in the time signature.
    """
    straight_needed = 1  # plain beats
    has_triplet_content = False
    has_straight_content = False  # any straight label or *N

    for line in lines:
        if isinstance(line.beats, StarSpec):
            star = line.beats
            # Validate hit count up-front so we get a clean error instead
            # of a cryptic slot-math failure later.
            _star_hits_per_bar(star, beats_per_bar, beat_unit, context)
            if star.triplet:
                has_triplet_content = True
            else:
                has_straight_content = True
                straight_needed = max(
                    straight_needed, _star_min_slots_per_beat(star, beat_unit)
                )
            continue
        for beat in line.beats:
            label = str(beat)
            need = _label_min_slots_per_beat(label)
            if need == 3:
                has_triplet_content = True
            else:
                has_straight_content = True
                straight_needed = max(straight_needed, need)
            # Account for a buzz event's span end position.
            buzz_dur = getattr(beat, "buzz_duration", None)
            if buzz_dur is not None:
                buzz_need = _buzz_min_slots_per_beat(buzz_dur, beats_per_bar, beat_unit)
                if buzz_need > 0:
                    has_straight_content = True
                    straight_needed = max(straight_needed, buzz_need)

    if has_triplet_content and has_straight_content and straight_needed > 1:
        # Mixed bar: triplet + straight labels coexist.  Use the LCM of the
        # two grids so that every label maps to an integer slot.
        slots_per_beat = lcm(3, straight_needed)
    elif has_triplet_content:
        slots_per_beat = 3
    else:
        # Minimum usable grid is 2 per beat (so ``&`` suffixes have a slot).
        slots_per_beat = max(2, straight_needed)

    # Final sanity check for *Nt triplets that need slots_per_beat > 3
    # (e.g. *16t on a beat_unit=4 needs 6 slots/beat — not supported).
    for line in lines:
        if isinstance(line.beats, StarSpec):
            need = _star_min_slots_per_beat(line.beats, beat_unit)
            if need > slots_per_beat:
                raise ValueError(
                    f"{line.beats} requires {need} slots per beat, which is "
                    f"not supported (max supported is 4 straight / 3 triplet) "
                    f"in {context}"
                )

    return slots_per_beat * beats_per_bar


def _expand_pattern_line(
    line: PatternLine,
    subdivision: int,
    bar: int,
    beats_per_bar: int = 4,
    beat_unit: int = 4,
) -> list[Event]:
    if isinstance(line.beats, StarSpec):
        star = line.beats
        hits = _star_hits_per_bar(star, beats_per_bar, beat_unit, f"instrument {line.instrument!r}")
        if subdivision % hits != 0:
            raise ValueError(
                f"{star} on instrument {line.instrument!r}: bar subdivision "
                f"{subdivision} is not a multiple of {hits} hits"
            )
        step = subdivision // hits
        # Compute positions to exclude (from the ``except`` clause).
        except_positions: set[Fraction] = set()
        if star.except_beats:
            for label in star.except_beats:
                except_positions.add(
                    _beat_label_to_fraction(label, subdivision, beats_per_bar)
                )
        return [
            Event(
                bar=bar,
                beat_position=Fraction(i * step, subdivision),
                instrument=line.instrument,
                source_line=line.line,
            )
            for i in range(hits)
            if Fraction(i * step, subdivision) not in except_positions
        ]
    events = []
    for b in line.beats:
        position = _beat_label_to_fraction(str(b), subdivision, beats_per_bar)
        mods = getattr(b, "modifiers", [])
        buzz_dur_str = getattr(b, "buzz_duration", None)
        if mods:
            _validate_double_modifier(mods, subdivision, f"instrument {line.instrument!r} at beat {b!r}")
            _validate_buzz_modifier_compat(mods, f"instrument {line.instrument!r} at beat {b!r}")
            _validate_flam_instrument(line.instrument, mods, f"instrument {line.instrument!r} at beat {b!r}")
        duration: Fraction | None = None
        if "buzz" in (mods or []):
            duration = _buzz_span(buzz_dur_str or "4", beats_per_bar, beat_unit)
        events.append(
            Event(
                bar=bar,
                beat_position=position,
                instrument=line.instrument,
                modifiers=list(mods),
                duration=duration,
                buzz_duration=buzz_dur_str if duration is not None else None,
                source_line=line.line,
            )
        )
    return events


def _expand_groove_count_notes(
    count_str: str,
    notes_str: str,
    beats_per_bar: int,
) -> tuple[int, list[PatternLine]]:
    """Expand a groove's count+notes body into (subdivision, pattern lines).

    Uses the same count/notes tokenisers as fills and groups the resulting
    hits by instrument so they can be stored as ``PatternLine`` objects.
    """
    # Deferred import to avoid a circular dependency (compiler ↔ parser).
    from .parser import (
        _format_count_notes_mismatch,
        _parse_count_tokens,
        _parse_notes_tokens,
    )

    beat_labels = _parse_count_tokens(count_str)
    note_groups = _parse_notes_tokens(notes_str)
    if len(beat_labels) != len(note_groups):
        raise ValueError(
            _format_count_notes_mismatch("groove body", count_str, notes_str)
        )

    subdivision = _infer_subdivision_from_labels(beat_labels, beats_per_bar)

    # Group by instrument, preserving first-appearance order.
    order: list[str] = []
    by_instrument: dict[str, list[BeatHit]] = defaultdict(list)
    for label, hits in zip(beat_labels, note_groups):
        for hit in hits:
            instrument = str(hit)
            if instrument not in by_instrument:
                order.append(instrument)
            mods = getattr(hit, "modifiers", []) or []
            by_instrument[instrument].append(BeatHit(label, list(mods) if mods else None))
    lines = [PatternLine(instrument=inst, beats=by_instrument[inst]) for inst in order]
    return subdivision, lines


def compile_groove(
    groove: Groove,
    beats_per_bar: int = 4,
    beat_unit: int = 4,
) -> IRGroove:
    """Compile a Groove AST node into a flat event list across its bars.

    Subdivisions are inferred from the content of each bar (beat labels and
    ``*N`` / ``*Nt`` stars), independently per bar. The returned
    :class:`IRGroove` carries the subdivision of its **first** bar; the
    compiler only reads that for code paths that still assume a single
    groove-level grid. Per-bar event positions use the bar's own subdivision,
    which is stamped onto the :class:`IRBar` downstream.
    """
    if groove.count_notes is not None:
        count_str, notes_str = groove.count_notes
        subdivision, lines = _expand_groove_count_notes(count_str, notes_str, beats_per_bar)
        bars = [lines]
        per_bar_subdivisions = [subdivision]
    else:
        bars = groove.bars
        per_bar_subdivisions = [
            _infer_bar_subdivision(
                lines, beats_per_bar, beat_unit,
                f"groove {groove.name!r} bar {bar_idx + 1}",
            )
            for bar_idx, lines in enumerate(bars)
        ]

    events: list[Event] = []
    for bar_number, (lines, subdivision) in enumerate(
        zip(bars, per_bar_subdivisions), start=1
    ):
        for line in lines:
            events.extend(
                _expand_pattern_line(line, subdivision, bar_number, beats_per_bar, beat_unit)
            )

    # Validate subdivision-level constraint for 'double' after all events are built.
    if any("double" in e.modifiers for e in events):
        # Every 'double' event must be at 16ths (slots_per_beat=4) in its own bar.
        for bar_number, subdivision in enumerate(per_bar_subdivisions, start=1):
            if any(
                "double" in e.modifiers and e.bar == bar_number for e in events
            ):
                _validate_double_subdivision(
                    subdivision, beats_per_bar,
                    f"groove {groove.name!r} bar {bar_number}",
                )

    # Validate buzz events (instrument, in-bar fit, hand-played overlap).
    for event in events:
        _validate_buzz_event(event, beats_per_bar, f"groove {groove.name!r}")
    for bar_number in range(1, len(bars) + 1):
        bar_events = [e for e in events if e.bar == bar_number]
        _validate_buzz_overlap(bar_events, f"groove {groove.name!r} bar {bar_number}")

    events.sort(key=lambda e: (e.bar, e.beat_position))

    # IRGroove carries the first bar's subdivision; per-bar subdivision lives
    # on IRBar downstream.
    first_subdivision = per_bar_subdivisions[0] if per_bar_subdivisions else beats_per_bar * 2
    return IRGroove(
        name=groove.name,
        subdivision=first_subdivision,
        bars=len(bars),
        events=events,
        bar_subdivisions=list(per_bar_subdivisions),
    )


@dataclass
class IRFillBar:
    """One bar of fill events ready to overlay onto groove events."""

    events: list[Event]
    subdivision: int


def _resolve_placeholder_position(placeholder: FillPlaceholder, subdivision: int, beats_per_bar: int) -> Fraction:
    """Return the beat position (as a Fraction) for a FillPlaceholder."""
    if placeholder.beat is not None:
        return _beat_label_to_fraction(placeholder.beat, subdivision, beats_per_bar)
    return Fraction(0)


def _infer_fill_subdivision(fill_bar: FillBar, beats_per_bar: int = 4, beat_unit: int = 4) -> int:
    """Infer total bar subdivision from beat labels, star specs, and beats_per_bar.

    - Triplet suffix 't'/'l' or 'trip'/'let' → 3 subdivisions per beat
    - 16th suffix 'e'/'a'                    → 4 subdivisions per beat
    - Star specs (*8, *16, *8t, etc.)        → derived from note value
    - Mixed triplet + straight               → LCM-based grid
    - Otherwise                              → 2 subdivisions per beat
    """
    has_triplet = False
    has_sixteenth = False
    has_eighth = False
    straight_needed = 1
    for line in fill_bar.lines:
        if line.beat and (line.beat[-1] in "tl" or line.beat.endswith(("trip", "let"))):
            has_triplet = True
        if line.beat and line.beat[-1] in "ea":
            has_sixteenth = True
        if line.beat and line.beat[-1] == "&":
            has_eighth = True
        # Buzz span end positions also contribute a grid-alignment constraint.
        for inst_hit in line.instruments:
            buzz_dur = getattr(inst_hit, "buzz_duration", None)
            if buzz_dur is not None:
                straight_needed = max(
                    straight_needed,
                    _buzz_min_slots_per_beat(buzz_dur, beats_per_bar, beat_unit),
                )
    # Also consider star specs from pattern_lines.
    for pline in fill_bar.pattern_lines:
        if isinstance(pline.beats, StarSpec):
            star = pline.beats
            if star.triplet:
                has_triplet = True
            else:
                straight_needed = max(straight_needed, _star_min_slots_per_beat(star, beat_unit))
            # Also account for except-beat labels.
            for label in star.except_beats:
                need = _label_min_slots_per_beat(label)
                if need == 3:
                    has_triplet = True
                else:
                    straight_needed = max(straight_needed, need)
    if has_sixteenth:
        straight_needed = max(straight_needed, 4)
    elif has_eighth:
        straight_needed = max(straight_needed, 2)
    if has_triplet:
        if straight_needed > 1:
            return lcm(3, straight_needed) * beats_per_bar
        return beats_per_bar * 3
    if straight_needed > 1:
        return max(2, straight_needed) * beats_per_bar
    return beats_per_bar * 2


def compile_fill_bar(fill_bar: FillBar, beats_per_bar: int = 4, beat_unit: int = 4) -> IRFillBar:
    """Compile a FillBar into a flat list of events at bar=1 (relative positions)."""
    subdivision = _infer_fill_subdivision(fill_bar, beats_per_bar, beat_unit)
    events: list[Event] = []
    for line in fill_bar.lines:
        position = _beat_label_to_fraction(line.beat, subdivision, beats_per_bar)
        for inst_hit in line.instruments:
            mods = getattr(inst_hit, "modifiers", [])
            buzz_dur_str = getattr(inst_hit, "buzz_duration", None)
            if mods:
                _validate_double_modifier(mods, subdivision, f"fill at beat {line.beat!r}")
                _validate_buzz_modifier_compat(mods, f"fill at beat {line.beat!r}")
                _validate_flam_instrument(str(inst_hit), mods, f"fill at beat {line.beat!r}")
            duration: Fraction | None = None
            if "buzz" in (mods or []):
                duration = _buzz_span(buzz_dur_str or "4", beats_per_bar, beat_unit)
            events.append(
                Event(
                    bar=1,
                    beat_position=position,
                    instrument=str(inst_hit),
                    modifiers=list(mods),
                    duration=duration,
                    buzz_duration=buzz_dur_str if duration is not None else None,
                )
            )
    # Expand star-spec pattern lines (e.g. BD: *8 except 4&).
    for pline in fill_bar.pattern_lines:
        events.extend(_expand_pattern_line(pline, subdivision, 1, beats_per_bar, beat_unit))
    if any("double" in e.modifiers for e in events):
        _validate_double_subdivision(subdivision, beats_per_bar, f"fill bar {fill_bar.label!r}")
    # Validate buzz event positions and hand-played overlap.
    for event in events:
        _validate_buzz_event(event, beats_per_bar, f"fill bar {fill_bar.label!r}")
    _validate_buzz_overlap(events, f"fill bar {fill_bar.label!r}")
    events.sort(key=lambda e: e.beat_position)
    return IRFillBar(events=events, subdivision=subdivision)


def _apply_fill_overlay(
    groove_events: list[Event],
    fill_bar: IRFillBar,
    start_position: Fraction,
    absolute_bar: int,
) -> list[Event]:
    """Overlay fill events onto groove events starting at start_position.

    Fill events replace all groove events at or after start_position.
    Groove events before start_position are preserved unchanged.
    """
    kept_groove = [e for e in groove_events if e.beat_position < start_position]
    fill_events = [
        Event(
            bar=absolute_bar,
            beat_position=fe.beat_position,
            instrument=fe.instrument,
            modifiers=list(fe.modifiers),
            duration=fe.duration,
            buzz_duration=fe.buzz_duration,
            source_line=fe.source_line,
        )
        for fe in fill_bar.events
    ]
    merged = kept_groove + fill_events
    merged.sort(key=lambda e: e.beat_position)
    return merged


def _infer_variation_subdivision(actions: list[VariationAction], beats_per_bar: int = 4) -> int:
    """Infer the finest subdivision needed by the variation's beat labels.

    When triplet and straight content coexist the result is the LCM-based
    grid that accommodates both.
    """
    has_triplet = False
    straight_needed = 1  # plain beats only

    for action in actions:
        if action.action == "substitute" and action.count_notes is not None:
            from .parser import _parse_count_tokens

            sub = _infer_subdivision_from_labels(
                _parse_count_tokens(action.count_notes[0]), beats_per_bar
            )
            # _infer_subdivision_from_labels already computes the LCM-based
            # grid for mixed labels, so extract the slots_per_beat component.
            spb = sub // beats_per_bar
            if spb in (3, 6, 12):
                has_triplet = True
            # Extract the straight component from a potentially mixed grid.
            if spb in (6,):
                straight_needed = max(straight_needed, 2)
            elif spb in (4, 12):
                straight_needed = max(straight_needed, 4)
            elif spb == 2:
                straight_needed = max(straight_needed, 2)
            continue
        if action.beats == "*":
            continue
        for beat in action.beats:
            need = _label_min_slots_per_beat(beat)
            if need == 3:
                has_triplet = True
            else:
                straight_needed = max(straight_needed, need)

    if has_triplet and straight_needed > 1:
        return lcm(3, straight_needed) * beats_per_bar
    if has_triplet:
        return beats_per_bar * 3
    return max(2, straight_needed) * beats_per_bar


def _apply_variation_actions(
    events: list[Event],
    actions: list[VariationAction],
    subdivision: int,
    absolute_bar: int,
    beats_per_bar: int = 4,
    beat_unit: int = 4,
) -> list[Event]:
    """Apply variation add/remove/replace/substitute actions to a list of events."""
    result = list(events)

    for action in actions:
        if action.action == "substitute":
            if action.count_notes is None:
                raise ValueError("substitute action missing count_notes body")
            from .parser import (
                _format_count_notes_mismatch,
                _parse_count_tokens,
                _parse_notes_tokens,
            )

            count_str, notes_str = action.count_notes
            beat_labels = _parse_count_tokens(count_str)
            note_groups = _parse_notes_tokens(notes_str)
            if len(beat_labels) != len(note_groups):
                raise ValueError(
                    _format_count_notes_mismatch(
                        "variation substitute", count_str, notes_str
                    )
                )
            # Substitute wipes everything in the bar, then places the new events.
            result = []
            for label, hits in zip(beat_labels, note_groups):
                position = _beat_label_to_fraction(label, subdivision, beats_per_bar)
                for hit in hits:
                    mods = getattr(hit, "modifiers", []) or []
                    result.append(
                        Event(
                            bar=absolute_bar,
                            beat_position=position,
                            instrument=str(hit),
                            modifiers=list(mods),
                            source_line=action.line,
                        )
                    )
            continue

        if action.beats == "*":
            positions = set(Fraction(i, subdivision) for i in range(subdivision))
        else:
            positions = set(
                _beat_label_to_fraction(b, subdivision, beats_per_bar) for b in action.beats
            )

        if action.action == "remove":
            result = [
                e for e in result
                if not (e.instrument == action.instrument and e.beat_position in positions)
            ]
        elif action.action == "add":
            if action.modifiers:
                _validate_double_modifier(action.modifiers, subdivision, f"variation add {action.instrument!r}")
                _validate_buzz_modifier_compat(action.modifiers, f"variation add {action.instrument!r}")
                _validate_flam_instrument(action.instrument, action.modifiers, f"variation add {action.instrument!r}")
                if "double" in action.modifiers:
                    _validate_double_subdivision(subdivision, beats_per_bar, f"variation add {action.instrument!r}")
            duration: Fraction | None = None
            if "buzz" in action.modifiers:
                duration = _buzz_span(action.buzz_duration or "4", beats_per_bar, beat_unit)
            occupied = {e.beat_position for e in result if e.instrument == action.instrument}
            for pos in sorted(positions):
                if pos in occupied:
                    raise ValueError(
                        f"variation add {action.instrument!r} at {_beat_label_for(pos, beats_per_bar)} "
                        f"(bar {absolute_bar}): a {action.instrument!r} note is already present "
                        f"at that position — adding would stack two notes on top of each other"
                    )
                occupied.add(pos)
                result.append(
                    Event(
                        bar=absolute_bar,
                        beat_position=pos,
                        instrument=action.instrument,
                        modifiers=list(action.modifiers),
                        duration=duration,
                        buzz_duration=action.buzz_duration if duration is not None else None,
                        source_line=action.line,
                    )
                )
        elif action.action == "replace":
            if action.modifiers:
                _validate_double_modifier(action.modifiers, subdivision, f"variation replace → {action.target_instrument!r}")
                _validate_buzz_modifier_compat(action.modifiers, f"variation replace → {action.target_instrument!r}")
                _validate_flam_instrument(action.target_instrument, action.modifiers, f"variation replace → {action.target_instrument!r}")
                if "double" in action.modifiers:
                    _validate_double_subdivision(subdivision, beats_per_bar, f"variation replace → {action.target_instrument!r}")
            result = [
                e for e in result
                if not (e.instrument == action.instrument and e.beat_position in positions)
            ]
            duration = None
            if "buzz" in action.modifiers:
                duration = _buzz_span(action.buzz_duration or "4", beats_per_bar, beat_unit)
            occupied = {e.beat_position for e in result if e.instrument == action.target_instrument}
            for pos in sorted(positions):
                if pos in occupied:
                    raise ValueError(
                        f"variation replace {action.instrument!r} with {action.target_instrument!r} "
                        f"at {_beat_label_for(pos, beats_per_bar)} (bar {absolute_bar}): a "
                        f"{action.target_instrument!r} note is already present at that position — "
                        f"replace would stack two notes on top of each other"
                    )
                occupied.add(pos)
                result.append(
                    Event(
                        bar=absolute_bar,
                        beat_position=pos,
                        instrument=action.target_instrument,
                        modifiers=list(action.modifiers),
                        duration=duration,
                        buzz_duration=action.buzz_duration if duration is not None else None,
                        source_line=action.line,
                    )
                )
        elif action.action == "modify_add":
            # Add each modifier to the named instrument's events at the target
            # positions, skipping modifiers the event already carries.
            for event in result:
                if event.beat_position not in positions:
                    continue
                if event.instrument != action.instrument:
                    continue
                _validate_flam_instrument(event.instrument, action.modifiers, f"variation modify add at beat {event.beat_position}")
                added_any = False
                for mod in action.modifiers:
                    if mod not in event.modifiers:
                        event.modifiers.append(mod)
                        added_any = True
                if "buzz" in action.modifiers and action.buzz_duration is not None:
                    event.buzz_duration = action.buzz_duration
                    event.duration = _buzz_span(action.buzz_duration, beats_per_bar, beat_unit)
                # When a modifier was actually added, point diagnostics at the
                # variation line rather than the original pattern line: the
                # newly-stamped modifier is what can create notation conflicts.
                if added_any and action.line is not None:
                    event.source_line = action.line
        elif action.action == "modify_remove":
            # Drop each listed modifier from the named instrument's events at
            # the target positions. Silently tolerates modifiers that aren't
            # present so sweeping removals (e.g. "modify remove accent from
            # snare at *") are painless.
            for event in result:
                if event.beat_position not in positions:
                    continue
                if event.instrument != action.instrument:
                    continue
                for mod in action.modifiers:
                    if mod in event.modifiers:
                        event.modifiers.remove(mod)
                    if mod == "buzz":
                        event.buzz_duration = None
                        event.duration = None

    result.sort(key=lambda e: e.beat_position)
    return result


# Tiebreak order when multiple instruments share the highest hit count in
# bar 1 of a ``crash in`` section. Cymbals/rides come first in the order
# drummers conventionally swap to crash at a section start.
_CRASH_IN_TIEBREAK_PRIORITY: tuple[str, ...] = ("RD", "HH", "OH", "CR", "HF")


def _apply_crash_in(events: list[Event], absolute_bar: int) -> list[Event]:
    """Ensure this (first) bar starts with a crash backed by a kick.

    Algorithm:
      1. The "riding" instrument is the one with the most hits in the bar.
         Ties among cymbals/hats are broken by :data:`_CRASH_IN_TIEBREAK_PRIORITY`;
         a tie with no cymbal leaves the rider undefined and we fall through
         to the beat-1 fallback below.
      2. If the rider has a hit on beat 1, replace it with a ``CR`` at the
         same position (preserving modifiers other than ``ghost``).
         Otherwise, add a fresh ``CR`` hit on beat 1.
      3. Ensure beat 1 also carries a ``BD`` hit — add one if it's missing.
         This matches the drummer convention of crashing together with a
         kick. If a ``BD`` is already there, it's left alone.
      4. If beat 1 already carries a ``CR`` hit, the crash step is a no-op;
         the ``BD`` step still runs so a crash-in always guarantees the
         crash-plus-kick pairing.
    """
    result = list(events)
    has_cr_on_one = any(
        e.instrument == "CR" and e.beat_position == Fraction(0) for e in result
    )

    if not has_cr_on_one:
        counts: dict[str, int] = {}
        for event in result:
            counts[event.instrument] = counts.get(event.instrument, 0) + 1

        rider: str | None = None
        if counts:
            max_count = max(counts.values())
            candidates = [inst for inst, c in counts.items() if c == max_count]
            if len(candidates) == 1:
                rider = candidates[0]
            else:
                for preferred in _CRASH_IN_TIEBREAK_PRIORITY:
                    if preferred in candidates:
                        rider = preferred
                        break

        replaced = False
        if rider is not None and rider != "CR":
            for i, event in enumerate(result):
                if event.instrument == rider and event.beat_position == Fraction(0):
                    kept_modifiers = [m for m in event.modifiers if m != "ghost"]
                    result[i] = Event(
                        bar=event.bar,
                        beat_position=Fraction(0),
                        instrument="CR",
                        modifiers=kept_modifiers,
                        duration=event.duration,
                        buzz_duration=event.buzz_duration,
                    )
                    replaced = True
                    break

        if not replaced:
            result.append(
                Event(
                    bar=absolute_bar,
                    beat_position=Fraction(0),
                    instrument="CR",
                    modifiers=[],
                )
            )

    has_bd_on_one = any(
        e.instrument == "BD" and e.beat_position == Fraction(0) for e in result
    )
    if not has_bd_on_one:
        result.append(
            Event(
                bar=absolute_bar,
                beat_position=Fraction(0),
                instrument="BD",
                modifiers=[],
            )
        )

    result.sort(key=lambda e: e.beat_position)
    return result


def _resolve_inheritance(sections: list[Section]) -> list[Section]:
    """Resolve ``like`` references by merging the inherited section with the
    inheriting section's own declarations.

    The bare form ``like "parent"`` inherits the parent's structural fields
    (scalars + inline grooves + section-level dynamic spans). The ``with``
    clause opts the child into additional categories:

    - ``with fills``       — fills, fill_placeholders, inline_fills
    - ``with variations``  — variation blocks
    - ``with cues``        — cue annotations

    Uses recursive resolution with cycle detection so that chained ``like``
    references (C likes B, B likes A) work correctly — the target section is
    always fully resolved before being used as a merge source.

    Merge rules:
    - Scalar fields (``bars``, ``groove``, ``repeat``, ``tempo``,
      ``time_signature``, ``play``) use the inheriting section's value when
      it set one, otherwise fall back to the original.
    - Inherited list fields concatenate with the inherited entries first
      and the inheriting section's additions last. The compiler's per-bar
      coverage dicts iterate these lists in order and let later entries
      win, so an addition that targets the same bar as an inherited entry
      effectively overrides it.
    """
    section_map = {s.name: s for s in sections}
    resolved_map: dict[str, Section] = {}
    resolving: set[str] = set()

    def _resolve(name: str) -> None:
        if name in resolved_map:
            return
        section = section_map.get(name)
        if section is None:
            return
        if section.inherit is None:
            resolved_map[name] = section
            return
        if name in resolving:
            raise ValueError(
                f"Circular like reference involving section {name!r}"
            )
        resolving.add(name)

        target_name = section.inherit.parent
        if target_name not in section_map:
            raise ValueError(
                f"Section {name!r} references unknown section {target_name!r}"
            )
        # Ensure the target is fully resolved first.
        _resolve(target_name)
        original = resolved_map[target_name]
        spec = section.inherit

        # Scalars: inheriting section's explicit values override the inherited ones.
        merged_bars = section.bars if section.bars is not None else original.bars
        merged_groove = section.groove if section.groove is not None else original.groove
        merged_repeat = section.repeat if section.repeat is not None else original.repeat
        merged_tempo = section.tempo if section.tempo is not None else original.tempo
        merged_time_signature = (
            section.time_signature if section.time_signature is not None else original.time_signature
        )
        if section.play is not None:
            merged_play = list(section.play)
        elif original.play is not None:
            merged_play = list(original.play)
        else:
            merged_play = None
        # crash_in is a boolean flag: inherit if either side sets it.
        merged_crash_in = section.crash_in or original.crash_in

        inherits_fills = spec.inherits("fills")
        inherits_variations = spec.inherits("variations")
        inherits_cues = spec.inherits("cues")

        merged_fills = (
            list(original.fills) + list(section.fills)
            if inherits_fills else list(section.fills)
        )
        merged_fill_placeholders = (
            list(original.fill_placeholders) + list(section.fill_placeholders)
            if inherits_fills else list(section.fill_placeholders)
        )
        merged_inline_fills = (
            list(original.inline_fills) + list(section.inline_fills)
            if inherits_fills else list(section.inline_fills)
        )
        merged_variations = (
            list(original.variations) + list(section.variations)
            if inherits_variations else list(section.variations)
        )
        merged_cues = (
            list(original.cues) + list(section.cues)
            if inherits_cues else list(section.cues)
        )

        resolved_map[name] = Section(
            name=section.name,
            bars=merged_bars,
            groove=merged_groove,
            repeat=merged_repeat,
            fills=merged_fills,
            fill_placeholders=merged_fill_placeholders,
            inline_fills=merged_inline_fills,
            inline_grooves=list(original.inline_grooves) + list(section.inline_grooves),
            variations=merged_variations,
            inherit=None,
            cues=merged_cues,
            dynamic_spans=list(original.dynamic_spans) + list(section.dynamic_spans),
            tempo=merged_tempo,
            time_signature=merged_time_signature,
            play=merged_play,
            crash_in=merged_crash_in,
        )
        resolving.discard(name)

    for section in sections:
        _resolve(section.name)

    return [resolved_map[s.name] for s in sections]


def _compile_play_bar_events(
    pattern: list[PatternLine],
    beats_per_bar: int,
    beat_unit: int,
    context: str,
) -> tuple[list[Event], int]:
    """Compile a one-off play bar's pattern lines into (events, subdivision).

    Infers the bar's subdivision from its pattern lines and returns both
    the event list (positions bar=1-relative) and the resolved subdivision.
    """
    subdivision = _infer_bar_subdivision(pattern, beats_per_bar, beat_unit, context)
    events: list[Event] = []
    for line in pattern:
        events.extend(
            _expand_pattern_line(line, subdivision, bar=1, beats_per_bar=beats_per_bar, beat_unit=beat_unit)
        )
    events.sort(key=lambda e: e.beat_position)
    return events, subdivision


def _whole_bar_rest_subdivision(beats_per_bar: int) -> int:
    """Default subdivision for a rest bar: 8th-note grid (2 per beat)."""
    return beats_per_bar * 2


def _shift_span(span: DynamicSpan, offset: int) -> DynamicSpan:
    """Return a copy of ``span`` with its bar numbers shifted by ``offset`` bars.

    Used to translate groove-internal and fill-internal spans (bar numbers
    1-indexed within the groove/fill) into section-bar coordinates.
    """
    return replace(
        span,
        from_bar=span.from_bar + offset,
        to_bar=span.to_bar + offset,
    )


def _collect_section_dynamic_spans(
    section: Section,
    groove_ast: Groove | None,
    fill_map: dict[str, Fill],
    total_bars: int,
) -> list[DynamicSpan]:
    """Collect all dynamic spans that apply to a section.

    Combines three sources, translated into section-bar coordinates:
    - Section-level spans (already in section coords).
    - Groove-internal spans, repeated once per groove cycle across
      ``total_bars``. ``groove_ast`` is the source Groove used for the
      classic (non-play) code path; pass ``None`` for play-list sections.
    - Fill-internal spans, translated to start at the bar where the fill
      is placed.
    """
    collected: list[DynamicSpan] = list(section.dynamic_spans)

    if groove_ast is not None and groove_ast.dynamic_spans:
        groove_bars = len(groove_ast.bars) if groove_ast.bars else 1
        if groove_bars > 0:
            cycles = total_bars // groove_bars
            for cycle_idx in range(cycles):
                base = cycle_idx * groove_bars
                for span in groove_ast.dynamic_spans:
                    collected.append(_shift_span(span, base))

    for fp in section.fills:
        fill = fill_map.get(fp.fill_name)
        if fill is None or not fill.dynamic_spans:
            continue
        offset = fp.bar - 1
        for span in fill.dynamic_spans:
            collected.append(_shift_span(span, offset))

    return collected


def _resolve_dynamic_spans(
    spans: list[DynamicSpan],
    total_bars: int,
    bpb: int,
) -> tuple[dict[int, list[tuple[Fraction, str]]], dict[int, list[Fraction]]]:
    """Resolve DynamicSpan AST nodes into per-bar start/stop annotations.

    Returns two dicts keyed by section_bar_offset (0-indexed):
    - starts: {offset: [(beat_position, kind), ...]}
    - stops:  {offset: [beat_position, ...]}
    """
    starts: dict[int, list[tuple[Fraction, str]]] = defaultdict(list)
    stops: dict[int, list[Fraction]] = defaultdict(list)

    for span in spans:
        from_offset = span.from_bar - 1
        to_offset = span.to_bar - 1

        # Resolve start position
        if span.from_beat is not None:
            # Use a generous subdivision (16ths) to resolve the label
            subdiv = bpb * 4
            start_pos = _beat_label_to_fraction(span.from_beat, subdiv, bpb)
        else:
            start_pos = Fraction(0)

        # Resolve end position
        if span.to_beat is not None:
            subdiv = bpb * 4
            stop_pos = _beat_label_to_fraction(span.to_beat, subdiv, bpb)
        else:
            # End of bar = position 0 of the *next* bar, but we represent
            # it as the last slot of the target bar. For the hairpin
            # terminator, we need to place \! on the last event's position
            # in the target bar. We use a sentinel Fraction(-1) meaning
            # "end of bar" and resolve it in the emitter to the last event.
            stop_pos = Fraction(-1)

        starts[from_offset].append((start_pos, span.kind))
        stops[to_offset].append(stop_pos)

    return dict(starts), dict(stops)


def _resolve_groove_extends(
    groove_defs: dict[str, Groove],
    groove_bar_texts_map: dict[str, dict[int, str]],
) -> None:
    """Resolve ``extend:`` references in-place.

    For each groove that declares ``extend: "base"``, the base groove's
    pattern lines are used as a starting point; the extending groove's
    lines override instruments that appear in both, and add instruments
    that are new. The result replaces the groove's ``bars`` list.
    """
    # Track resolved state to detect cycles.
    resolved: set[str] = set()
    resolving: set[str] = set()

    def _resolve(name: str) -> None:
        if name in resolved:
            return
        groove = groove_defs.get(name)
        if groove is None or groove.extend is None:
            resolved.add(name)
            return
        if name in resolving:
            raise ValueError(f"Circular extend: reference involving groove {name!r}")
        resolving.add(name)

        base_name = groove.extend
        if base_name not in groove_defs:
            raise ValueError(
                f"Groove {name!r} extends unknown groove {base_name!r}"
            )
        # Ensure the base is resolved first.
        _resolve(base_name)

        base = groove_defs[base_name]
        # Merge bars: if the extending groove has no bars (extend-only, no
        # overrides), use the base bars unchanged. If the extending
        # groove has a single-bar pattern, apply those overrides to every
        # bar of the base (broadcast). If it has a multi-bar pattern, merge
        # bar-by-bar (same instrument = override, new instrument = add).
        if not groove.bars:
            merged_bars = [list(bar) for bar in base.bars]
        elif len(groove.bars) == 1 and len(base.bars) > 1:
            # Broadcast: apply the single bar of overrides to every base bar.
            ext_lines = groove.bars[0]
            merged_bars = []
            for base_bar in base.bars:
                merged: dict[str, PatternLine] = {pl.instrument: pl for pl in base_bar}
                for pl in ext_lines:
                    merged[pl.instrument] = pl
                merged_bars.append(list(merged.values()))
        else:
            merged_bars = []
            for i in range(max(len(base.bars), len(groove.bars))):
                base_lines = base.bars[i] if i < len(base.bars) else []
                ext_lines = groove.bars[i] if i < len(groove.bars) else []
                merged = {pl.instrument: pl for pl in base_lines}
                for pl in ext_lines:
                    merged[pl.instrument] = pl
                merged_bars.append(list(merged.values()))

        # Merge bar_texts: base first, then overlay extending groove's texts.
        merged_texts = dict(base.bar_texts)
        merged_texts.update(groove.bar_texts)

        groove_defs[name] = Groove(
            name=name,
            bars=merged_bars,
            bar_texts=merged_texts,
            extend=None,  # mark as resolved
        )
        groove_bar_texts_map[name] = merged_texts

        resolving.discard(name)
        resolved.add(name)

    for gname in list(groove_defs):
        _resolve(gname)


def _build_coverage_maps(
    section: Section,
    fill_map: dict[str, Fill],
    total_bars: int,
    bpb: int,
    beat_unit: int,
) -> tuple[dict[int, tuple["IRFillBar", Fraction]], dict[int, Variation]]:
    """Build per-bar fill and variation coverage maps for a section.

    Returns ``(fill_coverage, variation_coverage)`` keyed by
    section-bar offset (0-indexed). ``total_bars`` bounds fill coverage
    so multi-bar fills that extend past the section are truncated.
    """
    fill_coverage: dict[int, tuple[IRFillBar, Fraction]] = {}
    for placement in section.fills:
        fill_def = fill_map.get(placement.fill_name)
        if fill_def is None:
            raise ValueError(
                f"Section {section.name!r} references unknown fill {placement.fill_name!r}"
            )
        bar_offset = placement.bar - 1
        for fill_bar_index, fill_bar in enumerate(fill_def.bars):
            offset = bar_offset + fill_bar_index
            if offset < total_bars:
                compiled_bar = compile_fill_bar(fill_bar, bpb, beat_unit)
                if fill_bar_index == 0 and placement.beat is not None:
                    start_pos = _beat_label_to_fraction(placement.beat, compiled_bar.subdivision, bpb)
                else:
                    start_pos = Fraction(0)
                fill_coverage[offset] = (compiled_bar, start_pos)

    variation_coverage: dict[int, Variation] = {}
    for variation in section.variations:
        for vbar in variation.bars:
            variation_coverage[vbar - 1] = variation

    return fill_coverage, variation_coverage


def compile_song(song: Song) -> IRSong:
    """Compile a Song AST into arranged bar-by-bar IR."""
    global_ts = song.metadata.time_signature
    global_bpb = _beats_per_bar(global_ts)

    # Collect source Groove definitions (user + inline + library) so we can
    # compile each one on demand against whichever beats_per_bar the
    # referencing section uses. Per-section time signature overrides require
    # us to re-compile a groove at the section's bpb; we cache by (name, bpb).
    groove_defs: dict[str, Groove] = {groove.name: groove for groove in song.grooves}
    groove_bar_texts_map: dict[str, dict[int, str]] = {
        groove.name: groove.bar_texts for groove in song.grooves
    }

    # Register inline (unnamed) grooves defined inside sections before we
    # resolve like: inheritance — `like:` copies the groove reference by
    # synthetic name, so the target section's inline grooves must already
    # live in the groove_defs by the time the inheriting section compiles.
    for section in song.sections:
        for inline_groove in section.inline_grooves:
            groove_defs[inline_groove.name] = inline_groove
            groove_bar_texts_map[inline_groove.name] = inline_groove.bar_texts

    # Apply metadata defaults (default_groove, default_bars) to sections
    # that omit these fields.  Done before like: resolution so inherited
    # sections also see the defaults.
    default_groove = song.metadata.default_groove
    default_bars = song.metadata.default_bars
    patched_sections: list[Section] = []
    for section in song.sections:
        if section.play is not None or section.inherit is not None:
            patched_sections.append(section)
            continue
        s_groove = section.groove if section.groove is not None else default_groove
        s_bars = section.bars if section.bars is not None else default_bars
        if s_groove is None or s_bars is None:
            missing = []
            if s_groove is None:
                missing.append("groove")
            if s_bars is None:
                missing.append("bars")
            raise ValueError(
                f"Section {section.name!r} must define {' and '.join(missing)} "
                f"(or set default_groove / default_bars in metadata, or use like)"
            )
        if s_groove != section.groove or s_bars != section.bars:
            section = replace(section, groove=s_groove, bars=s_bars)
        patched_sections.append(section)

    sections = _resolve_inheritance(patched_sections)

    # Collect all referenced groove names so we can pull missing ones from
    # the built-in library. This includes grooves referenced by sections
    # and grooves referenced by extend: declarations.
    referenced_grooves = set()
    for section in sections:
        if section.play is not None:
            for item in section.play:
                if isinstance(item, PlayGroove):
                    referenced_grooves.add(item.groove_name)
        elif section.groove is not None:
            referenced_grooves.add(section.groove)
    for groove in groove_defs.values():
        if groove.extend is not None:
            referenced_grooves.add(groove.extend)

    from .library import get_library_grooves
    library = get_library_grooves()
    for name in referenced_grooves:
        if name not in groove_defs and name in library:
            groove_defs[name] = library[name]
            groove_bar_texts_map[name] = library[name].bar_texts

    # Resolve groove extend: references. Each groove with ``extend:``
    # inherits the base groove's pattern lines and merges its own on top.
    _resolve_groove_extends(groove_defs, groove_bar_texts_map)

    # Per-(name, bpb) cache of compiled grooves — a section that overrides
    # the time signature recompiles its grooves against the new bpb so beat
    # positions and subdivisions resolve against the right bar length.
    groove_cache: dict[tuple[str, int, int], IRGroove] = {}

    def _get_groove(name: str, bpb: int, beat_unit: int) -> IRGroove:
        key = (name, bpb, beat_unit)
        cached = groove_cache.get(key)
        if cached is not None:
            return cached
        source = groove_defs.get(name)
        if source is None:
            raise KeyError(name)
        compiled = compile_groove(source, bpb, beat_unit)
        groove_cache[key] = compiled
        return compiled

    fill_map = {fill.name: fill for fill in song.fills}
    # Merge per-section inline fills into the shared fill map. Inline fills
    # use synthetic, unique names so there is no collision risk.
    for section in sections:
        for inline_fill in section.inline_fills:
            fill_map[inline_fill.name] = inline_fill

    # Count occurrences of base section names
    name_counts = Counter(s.name.lower() for s in sections)
    current_counts = Counter()

    bars: list[IRBar] = []
    sections_ir: list[IRSection] = []
    current_bar_number = 1

    def _collect_bar_cues(section: Section, section_bar_offset: int, bar_subdivision: int, bpb: int) -> list[tuple[Fraction, str]]:
        out: list[tuple[Fraction, str]] = []
        for cue in section.cues:
            if cue.bar - 1 == section_bar_offset:
                if cue.beat is not None:
                    cue_pos = _beat_label_to_fraction(cue.beat, max(8, bar_subdivision), bpb)
                else:
                    cue_pos = Fraction(0)
                out.append((cue_pos, cue.text))
        out.sort(key=lambda x: x[0])
        return out

    def _collect_bar_placeholders(section: Section, section_bar_offset: int, bar_subdivision: int, bpb: int) -> list[tuple[Fraction, str]]:
        out: list[tuple[Fraction, str]] = []
        for ph in section.fill_placeholders:
            if ph.bar - 1 == section_bar_offset:
                ph_pos = _resolve_placeholder_position(ph, max(8, bar_subdivision), bpb)
                out.append((ph_pos, ph.label))
        out.sort(key=lambda x: x[0])
        return out

    def _process_play_section(section, bpb, beat_unit, effective_ts, effective_tempo, full_section_name, start_bar_number) -> tuple[list[IRBar], IRSection]:
        expanded = _expand_play_block(section.play, _get_groove, bpb, beat_unit, section.name)
        total_bars = len(expanded)
        if total_bars == 0:
            raise ValueError(f"Section {section.name!r}: play: block expanded to zero bars")

        ir_section = IRSection(name=section.name, start_bar=start_bar_number, bars=total_bars, tempo=effective_tempo)
        fill_coverage, variation_coverage = _build_coverage_maps(section, fill_map, total_bars, bpb, beat_unit)
        all_spans = _collect_section_dynamic_spans(section, None, fill_map, total_bars)
        dyn_starts, dyn_stops = _resolve_dynamic_spans(all_spans, total_bars, bpb)

        new_bars: list[IRBar] = []
        for section_bar_offset, (template_events, base_subdivision, is_rest) in enumerate(expanded):
            absolute_bar = start_bar_number + section_bar_offset
            # Re-stamp bar numbers on the template events for this absolute bar
            arranged_events = [
                Event(
                    bar=absolute_bar,
                    beat_position=event.beat_position,
                    instrument=event.instrument,
                    modifiers=list(event.modifiers),
                    duration=event.duration,
                    buzz_duration=event.buzz_duration,
                    source_line=event.source_line,
                )
                for event in template_events
            ]
            bar_subdivision = base_subdivision

            if section_bar_offset in fill_coverage:
                fill_bar, start_pos = fill_coverage[section_bar_offset]
                arranged_events = _apply_fill_overlay(arranged_events, fill_bar, start_pos, absolute_bar)
                bar_subdivision = max(bar_subdivision, fill_bar.subdivision)
                is_rest = False  # fill replaces a rest bar entirely

            if section_bar_offset in variation_coverage:
                variation = variation_coverage[section_bar_offset]
                var_subdivision = _infer_variation_subdivision(variation.actions, bpb)
                bar_subdivision = max(bar_subdivision, var_subdivision)
                arranged_events = _apply_variation_actions(
                    arranged_events, variation.actions, bar_subdivision, absolute_bar, bpb, beat_unit
                )

            if section.crash_in and section_bar_offset == 0:
                arranged_events = _apply_crash_in(arranged_events, absolute_bar)
                is_rest = False

            bar_cues = _collect_bar_cues(section, section_bar_offset, bar_subdivision, bpb)
            bar_placeholders = _collect_bar_placeholders(section, section_bar_offset, bar_subdivision, bpb)

            # Post-arrangement buzz validation: buzz may have arrived via
            # a fill overlay or variation add/replace; re-check overlap
            # against the final event list for this bar.
            context = f"section {section.name!r} bar {section_bar_offset + 1}"
            for event in arranged_events:
                _validate_buzz_event(event, bpb, context)
            _validate_buzz_overlap(arranged_events, context)

            new_bars.append(
                IRBar(
                    number=absolute_bar,
                    subdivision=bar_subdivision,
                    events=arranged_events,
                    section_name=full_section_name if section_bar_offset == 0 else None,
                    section_bars=total_bars if section_bar_offset == 0 else None,
                    cues=bar_cues,
                    fill_placeholders=bar_placeholders,
                    tempo=effective_tempo,
                    time_signature=effective_ts,
                    is_rest=is_rest,
                    dynamic_starts=dyn_starts.get(section_bar_offset, []),
                    dynamic_stops=dyn_stops.get(section_bar_offset, []),
                )
            )
        return new_bars, ir_section

    def _process_groove_section(section, bpb, beat_unit, effective_ts, effective_tempo, full_section_name, start_bar_number) -> tuple[list[IRBar], IRSection]:
        try:
            groove = _get_groove(section.groove, bpb, beat_unit)
        except KeyError:
            raise ValueError(
                f"Section {section.name!r} references unknown groove {section.groove!r}"
            )

        ir_section = IRSection(name=section.name, start_bar=start_bar_number, bars=section.bars, tempo=effective_tempo)

        repeat_times = section.repeat
        phrase_length = (section.bars // repeat_times) if repeat_times else None

        fill_coverage, variation_coverage = _build_coverage_maps(section, fill_map, section.bars, bpb, beat_unit)

        # Pre-bucket groove events by their groove-bar number. The tiling
        # loop below re-visits each groove bar ``section.bars / groove.bars``
        # times, so caching avoids repeatedly rescanning ``groove.events``.
        groove_events_by_bar: dict[int, list[Event]] = {
            bar_number: [event for event in groove.events if event.bar == bar_number]
            for bar_number in range(1, groove.bars + 1)
        }

        groove_ast = groove_defs.get(section.groove)
        all_spans = _collect_section_dynamic_spans(section, groove_ast, fill_map, section.bars)
        dyn_starts, dyn_stops = _resolve_dynamic_spans(all_spans, section.bars, bpb)
        groove_bar_texts = groove_bar_texts_map.get(section.groove, {})

        new_bars: list[IRBar] = []
        for section_bar_offset in range(section.bars):
            absolute_bar = start_bar_number + section_bar_offset
            groove_bar_number = (section_bar_offset % groove.bars) + 1
            template_events = groove_events_by_bar[groove_bar_number]
            groove_bar_subdivision = groove.bar_subdivisions[groove_bar_number - 1]
            arranged_events = [
                Event(
                    bar=absolute_bar,
                    beat_position=event.beat_position,
                    instrument=event.instrument,
                    modifiers=list(event.modifiers),
                    duration=event.duration,
                    buzz_duration=event.buzz_duration,
                    source_line=event.source_line,
                )
                for event in template_events
            ]

            if section_bar_offset in fill_coverage:
                fill_bar, start_pos = fill_coverage[section_bar_offset]
                arranged_events = _apply_fill_overlay(arranged_events, fill_bar, start_pos, absolute_bar)
                bar_subdivision = max(groove_bar_subdivision, fill_bar.subdivision)
            else:
                bar_subdivision = groove_bar_subdivision

            if section_bar_offset in variation_coverage:
                variation = variation_coverage[section_bar_offset]
                var_subdivision = _infer_variation_subdivision(variation.actions, bpb)
                bar_subdivision = max(bar_subdivision, var_subdivision)
                arranged_events = _apply_variation_actions(
                    arranged_events, variation.actions, bar_subdivision, absolute_bar, bpb, beat_unit
                )

            if section.crash_in and section_bar_offset == 0:
                arranged_events = _apply_crash_in(arranged_events, absolute_bar)

            bar_cues = _collect_bar_cues(section, section_bar_offset, bar_subdivision, bpb)
            bar_placeholders = _collect_bar_placeholders(section, section_bar_offset, bar_subdivision, bpb)

            # Bar-level text annotation from groove definition (loops with groove)
            bar_text = groove_bar_texts.get(groove_bar_number)

            # A repeat block starts every phrase_length bars if repeat_times is set.
            is_repeat_start = (repeat_times and (section_bar_offset % phrase_length == 0))
            current_repeat_index = (section_bar_offset // phrase_length + 1) if repeat_times else None

            context = f"section {section.name!r} bar {section_bar_offset + 1}"
            for event in arranged_events:
                _validate_buzz_event(event, bpb, context)
            _validate_buzz_overlap(arranged_events, context)

            new_bars.append(
                IRBar(
                    number=absolute_bar,
                    subdivision=bar_subdivision,
                    events=arranged_events,
                    section_name=full_section_name if section_bar_offset == 0 else None,
                    section_bars=section.bars if section_bar_offset == 0 else None,
                    repeat_times=repeat_times if is_repeat_start else None,
                    repeat_index=current_repeat_index,
                    cues=bar_cues,
                    fill_placeholders=bar_placeholders,
                    bar_text=bar_text,
                    tempo=effective_tempo,
                    time_signature=effective_ts,
                    dynamic_starts=dyn_starts.get(section_bar_offset, []),
                    dynamic_stops=dyn_stops.get(section_bar_offset, []),
                )
            )
        return new_bars, ir_section

    for section in sections:
        # Effective tempo: section override takes precedence over global metadata tempo
        effective_tempo = section.tempo if section.tempo is not None else song.metadata.tempo

        # Effective time signature: section override takes precedence over the
        # global metadata value. This also fixes beats_per_bar for everything
        # that happens inside this section (groove compilation, fill math,
        # variation math, beat-label resolution).
        effective_ts = section.time_signature if section.time_signature is not None else global_ts
        bpb = _beats_per_bar(effective_ts)
        beat_unit = _beat_unit(effective_ts)

        # Apply automatic numbering: "VERSE 1" instead of "VERSE" if "VERSE 2" exists
        base_name = section.name.lower()
        if name_counts[base_name] > 1:
            current_counts[base_name] += 1
            full_section_name = f"{section.name} {current_counts[base_name]}"
        else:
            full_section_name = section.name

        if section.play is not None:
            new_bars, ir_section = _process_play_section(
                section, bpb, beat_unit, effective_ts, effective_tempo, full_section_name, current_bar_number
            )
        else:
            new_bars, ir_section = _process_groove_section(
                section, bpb, beat_unit, effective_ts, effective_tempo, full_section_name, current_bar_number
            )

        sections_ir.append(ir_section)
        bars.extend(new_bars)
        current_bar_number += len(new_bars)

    _split_cross_bar_buzz_events(bars, global_bpb)

    return IRSong(metadata=song.metadata, bars=bars, sections=sections_ir)


def _split_cross_bar_buzz_events(
    bars: list[IRBar], default_bpb: int
) -> None:
    """Split buzz events whose span crosses a barline into tied per-bar pieces.

    Walks bars in order. For each buzz event whose end exceeds the bar
    (``beat_position + duration > 1``):

    - The original event's duration is clamped to ``1 - beat_position`` and
      its ``tied_to_next`` flag is set so the LilyPond emitter renders a
      ``~`` after the buzz token.
    - The remainder spills into the next bar as a continuation event at
      ``beat_position = 0`` with the leftover duration (and ``tied_to_next``
      set if it too overflows).

    Raises :class:`ValueError` if a buzz extends past the end of the song
    (no next bar to tie into) or if a continuation collides with a
    hand-played event in the receiving bar.
    """
    # Process bar by bar. Continuations may be added to subsequent bars,
    # which themselves may need re-splitting if they overflow further.
    bar_index = 0
    while bar_index < len(bars):
        bar = bars[bar_index]
        # Find the buzz events that overflow this bar.
        for event in list(bar.events):
            if event.duration is None or "buzz" not in event.modifiers:
                continue
            end = event.beat_position + event.duration
            if end <= 1:
                continue
            remainder = end - 1
            event.duration = Fraction(1) - event.beat_position
            event.tied_to_next = True
            if bar_index + 1 >= len(bars):
                raise ValueError(
                    f"buzz roll in bar {bar.number} ties past the end of the "
                    f"song (need {remainder} more of a bar)"
                )
            next_bar = bars[bar_index + 1]
            continuation = Event(
                bar=next_bar.number,
                beat_position=Fraction(0),
                instrument=event.instrument,
                modifiers=list(event.modifiers),
                duration=remainder,
                buzz_duration=None,
                tied_from_prev=True,
                source_line=event.source_line,
            )
            next_bar.events.append(continuation)
            next_bar.events.sort(key=lambda e: e.beat_position)
            # Re-validate hand-played overlap on the receiving bar; foot
            # overlap with the buzz continuation is allowed and rendered
            # via voice split, same as in-bar buzzes.
            bpb = (
                _beats_per_bar(next_bar.time_signature)
                if next_bar.time_signature is not None
                else default_bpb
            )
            _validate_buzz_overlap(
                next_bar.events,
                f"bar {next_bar.number} (buzz tie continuation)",
            )
            # Boost the receiving bar's subdivision so the continuation
            # lands cleanly on a slot boundary if its span denominator is
            # finer than the bar's existing grid.
            cont_per_beat = (remainder * bpb).denominator
            needed_subdiv = cont_per_beat * bpb
            if needed_subdiv > next_bar.subdivision and next_bar.subdivision % bpb == 0:
                next_bar.subdivision = lcm(next_bar.subdivision, needed_subdiv)
        bar_index += 1


def _expand_play_block(
    play_items: list,
    get_groove,
    bpb: int,
    beat_unit: int,
    section_name: str,
) -> list[tuple[list[Event], int, bool]]:
    """Expand a play: block into a flat list of (events, subdivision, is_rest) per bar.

    events are bar=1-relative (caller re-stamps to absolute bar numbers).
    subdivision is the grid for that bar.
    is_rest is True for whole-bar rest bars.

    ``get_groove`` is a callable ``(name, bpb, beat_unit) -> IRGroove`` so
    the caller controls how grooves are compiled/cached (needed because
    per-section time signature overrides recompile grooves at a different
    bpb/beat_unit).
    """
    result: list[tuple[list[Event], int, bool]] = []
    named_bars: dict[str, tuple[list[Event], int]] = {}  # name → (events, subdivision)
    last_groove_subdivision: int | None = None

    for item in play_items:
        if isinstance(item, PlayGroove):
            try:
                groove = get_groove(item.groove_name, bpb, beat_unit)
            except KeyError:
                raise ValueError(f"play: references unknown groove {item.groove_name!r}")
            # Use the groove's last bar's subdivision for subsequent rest/
            # inline-bar inheritance (closest match to what the user most
            # recently looked at).
            last_groove_subdivision = groove.bar_subdivisions[-1] if groove.bar_subdivisions else groove.subdivision
            groove_events_by_bar: dict[int, list[Event]] = {
                bn: [e for e in groove.events if e.bar == bn]
                for bn in range(1, groove.bars + 1)
            }
            for _ in range(item.repeat):
                for bar_num in range(1, groove.bars + 1):
                    bar_sub = groove.bar_subdivisions[bar_num - 1]
                    result.append((groove_events_by_bar[bar_num], bar_sub, False))

        elif isinstance(item, PlayBar):
            if item.pattern is not None:
                # Inline definition
                if item.name in named_bars:
                    raise ValueError(
                        f"play: duplicate bar name {item.name!r} in section"
                    )
                events, subdiv = _compile_play_bar_events(
                    item.pattern,
                    bpb,
                    beat_unit,
                    f"section {section_name!r} play bar {item.name!r}",
                )
                named_bars[item.name] = (events, subdiv)
            else:
                # Reference — must already be defined
                if item.name not in named_bars:
                    raise ValueError(
                        f"play: bar {item.name!r} referenced before it was defined"
                    )
                events, subdiv = named_bars[item.name]

            for _ in range(item.repeat):
                result.append((events, subdiv, False))

        elif isinstance(item, PlayRest):
            subdiv = last_groove_subdivision if last_groove_subdivision is not None else _whole_bar_rest_subdivision(bpb)
            for _ in range(item.repeat):
                result.append(([], subdiv, True))

    return result
