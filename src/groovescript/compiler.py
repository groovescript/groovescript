from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from fractions import Fraction
from math import gcd, lcm

from .ast_nodes import (
    BeatHit,
    BreakSpec,
    CrashInSpec,
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
    TupletGroup,
    TupletSlot,
    Variation,
    VariationAction,
    VariationDef,
)
from .errors import GrooveScriptError

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
    # Grace-stroke instrument for ``flam`` / ``drag`` modifiers. ``None``
    # means same-instrument flam/drag — the grace plays on
    # ``self.instrument``. When set, the grace plays on the named
    # instrument while the main hit lands on ``self.instrument``.
    grace_instrument: str | None = None
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
    # Per-bar tuplet annotations matching IRBar.beat_tuplets shape; empty
    # when the bar has no tuplet groups. ``bar_beat_tuplets[i]`` maps to
    # groove bar ``i + 1``.
    bar_beat_tuplets: list[list[object]] = field(default_factory=list)


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
    # Placeholder groove bar: no notes, no rests — just the empty bar with a
    # "Section groove" label on the first bar of a section that declares
    # ``bars:`` without a ``groove:``.  Used for minimal/skeleton charts.
    is_placeholder_groove: bool = False
    # Dynamic hairpin annotations: list of (beat_position, kind) where kind is "cresc" or "decresc"
    dynamic_starts: list[tuple[Fraction, str]] = field(default_factory=list)
    # Hairpin terminators: list of beat_position where a \! should be placed
    dynamic_stops: list[Fraction] = field(default_factory=list)
    # Natural-phrase metadata for the lilypond emitter's multi-bar repeat
    # detector. ``phrase_length`` is the length of the source groove (2 for a
    # two-bar groove, 1 for a one-bar groove); ``phrase_position`` is this
    # bar's 1-based offset within that phrase. The emitter uses these to
    # collapse e.g. an A-B-A-B-A-B run into ``\repeat volta 3 { A B }`` while
    # respecting phrase alignment so it never emits a B-A rotation.
    phrase_position: int | None = None
    phrase_length: int | None = None
    # Per-beat tuplet annotations. ``beat_tuplets[beat_idx]`` (0-indexed) is
    # one of:
    #   - ``None``                        → straight beat (no tuplet wrapping)
    #   - ``("full", actual, normal)``    → whole-beat tuplet (ratio actual/normal)
    #   - ``("halves", left, right)``     → half-beat split; each side is
    #                                       ``None`` (straight) or
    #                                       ``(actual, normal)`` for that half
    # Empty list means "no tuplet content in this bar" — equivalent to all
    # ``None`` entries — and lets the emitter fall back to the legacy path.
    beat_tuplets: list[object] = field(default_factory=list)


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

    Synthetic ``~T<anchor>_<slot>_<actual>_<normal>`` labels (emitted by the
    count-string parser for inline tuplet groups) are decoded by computing
    the slot's evenly-spaced position within the beat anchored at <anchor>.
    """
    # Synthetic tuplet-slot label produced by ``_parse_count_tokens``.
    if label.startswith("~T"):
        from .parser_notation import _decode_tuplet_slot_label
        decoded = _decode_tuplet_slot_label(label)
        if decoded is None:
            raise ValueError(f"Malformed tuplet-slot label: {label!r}")
        anchor, slot, actual, _normal = decoded
        anchor_pos = _beat_label_to_fraction(anchor, subdivision, beats_per_bar)
        # Whole-beat span only at this layer.
        span_in_bar = Fraction(1, beats_per_bar)
        return anchor_pos + Fraction(slot - 1, actual) * span_in_bar
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
    "HH", "OH", "RD", "CR", "RB", "CB", "FT", "HT", "MT", "SCS", "SN",
    "SP", "CH", "CR2", "ST",
})

# Instruments that support the flam modifier (grace-note ornament).
_FLAM_INSTRUMENTS: frozenset[str] = frozenset({"SN", "FT", "HT", "MT"})

# Instrument pairs that cannot sound simultaneously on the same beat position
# because they're physically the same instrument with different articulations.
# A drummer can't strike the closed and open hat at the same instant
# (articulation is an either/or property of the same cymbal); likewise the
# bow and bell of the ride share one cymbal, and a snare struck normally vs
# with a cross-stick is one drum with two articulations. Each frozenset is
# the set of instrument abbreviations that are mutually exclusive at one beat.
_INSTRUMENT_MUTEX_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"HH", "OH"}),
    frozenset({"RD", "RB"}),
    frozenset({"SN", "SCS"}),
)

# Instruments that accept the ``choke`` modifier (cymbal chokes — grabbing
# the cymbal mid-ring to silence it). Hi-hats, cowbell, stack, and the foot
# chick are excluded: hi-hats already model open/closed via HH/OH, cowbells
# don't sustain enough to choke meaningfully, and stacks are physically
# pre-muted (two cymbals pressed together) so their attack already dies on
# its own.
_CHOKE_INSTRUMENTS: frozenset[str] = frozenset({"CR", "RD", "RB", "SP", "CH", "CR2"})


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


def _validate_buzz_modifier_compat(
    modifiers: list[str], context: str, source_line: int | None = None
) -> None:
    """Reject buzz combined with incompatible modifiers."""
    if "buzz" not in modifiers:
        return
    for bad in ("flam", "drag", "double", "ghost"):
        if bad in modifiers:
            raise GrooveScriptError(
                message=f"'buzz' modifier is incompatible with {bad!r} in {context}",
                line=source_line,
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
        raise GrooveScriptError(
            message=(
                f"'buzz' modifier is only supported on SN (snare) — got "
                f"{event.instrument!r} in {context}"
            ),
            line=event.source_line,
        )


def _validate_grace_uniqueness(events: list[Event], context: str) -> None:
    """Reject more than one ``flam``/``drag`` event sharing a beat position.

    A flam or drag is a two-handed event (grace stroke on one hand, main on
    the other). Two such ornaments at the same beat position would require a
    third hand. The check is per (bar, beat_position): foot-played and
    non-ornament events at the same position are unaffected.
    """
    by_position: dict[Fraction, list[Event]] = defaultdict(list)
    for ev in events:
        if "flam" in ev.modifiers or "drag" in ev.modifiers:
            by_position[ev.beat_position].append(ev)
    for pos, group in by_position.items():
        if len(group) <= 1:
            continue
        instruments = ", ".join(sorted(e.instrument for e in group))
        ornament = "flam" if any("flam" in e.modifiers for e in group) else "drag"
        # Pin diagnostics to the second offending event so the source line
        # points at the addition that introduced the conflict.
        culprit = next((e for e in group if e.source_line is not None), group[0])
        raise GrooveScriptError(
            message=(
                f"more than one {ornament}/drag at beat position {pos} in "
                f"{context} ({instruments}): a flam or drag uses both hands, "
                f"so only one may sound at a given beat — use {ornament}:<inst> "
                f"to consolidate the grace if you meant a single ornament"
            ),
            line=culprit.source_line,
        )


def _validate_instrument_mutex(events: list[Event], context: str) -> None:
    """Reject mutually-exclusive instruments sounding at the same beat position.

    See :data:`_INSTRUMENT_MUTEX_GROUPS`. Pin the diagnostic to the second
    offending event so the source line points at the addition that
    introduced the conflict.
    """
    by_position: dict[Fraction, list[Event]] = defaultdict(list)
    for ev in events:
        by_position[ev.beat_position].append(ev)
    for pos, group in by_position.items():
        if len(group) < 2:
            continue
        instruments_at_pos = {ev.instrument for ev in group}
        for mutex in _INSTRUMENT_MUTEX_GROUPS:
            collision = instruments_at_pos & mutex
            if len(collision) < 2:
                continue
            colliding = sorted(collision)
            culprits = [
                e for e in group if e.instrument in collision
            ]
            culprit = next(
                (e for e in culprits[1:] if e.source_line is not None),
                next((e for e in culprits if e.source_line is not None), culprits[0]),
            )
            raise GrooveScriptError(
                message=(
                    f"{' and '.join(colliding)} cannot sound at the same beat "
                    f"position {pos} in {context}: they're the same physical "
                    f"instrument with different articulations and only one "
                    f"may sound at a time"
                ),
                line=culprit.source_line,
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
                raise GrooveScriptError(
                    message=(
                        f"{other.instrument} event at beat position "
                        f"{other.beat_position} overlaps a snare buzz roll span "
                        f"[{start}, {end}) in {context}"
                    ),
                    line=other.source_line,
                )


def _validate_double_modifier(
    modifiers: list[str],
    subdivision: int,
    context: str,
    source_line: int | None = None,
) -> None:
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
        raise GrooveScriptError(
            message=f"'double' modifier is incompatible with 'flam' in {context}",
            line=source_line,
        )
    if "drag" in modifiers:
        raise GrooveScriptError(
            message=f"'double' modifier is incompatible with 'drag' in {context}",
            line=source_line,
        )


def _validate_double_subdivision(
    subdivision: int,
    beats_per_bar: int,
    context: str,
    source_line: int | None = None,
) -> None:
    """Raise ValueError if 'double' modifier is used at a non-16th subdivision."""
    slots_per_beat = subdivision // beats_per_bar
    if slots_per_beat != 4:
        raise GrooveScriptError(
            message=(
                f"'double' modifier requires 16th-note subdivision "
                f"(4 slots per beat), but got {slots_per_beat} slots per beat "
                f"(subdivision={subdivision}, beats_per_bar={beats_per_bar}) in {context}"
            ),
            line=source_line,
        )


def _validate_choke_instrument(
    instrument: str,
    modifiers: list[str],
    context: str,
    source_line: int | None = None,
) -> None:
    """Reject ``choke`` on instruments that aren't cymbals.

    The ``choke`` modifier represents the drummer grabbing a sustaining
    cymbal mid-ring to silence it. It only makes sense on cymbals that
    actually ring out — crash (CR / CR2), ride (RD / RB), splash (SP),
    and china (CH). Hi-hats already model closed/open via ``HH``/``OH``
    (the closed hat is a continuous choke of the open one), and cowbell,
    stack, and drums don't sustain enough to choke meaningfully.
    """
    if "choke" not in modifiers:
        return
    if instrument not in _CHOKE_INSTRUMENTS:
        raise GrooveScriptError(
            message=(
                f"'choke' modifier is only supported on cymbals "
                f"(CR, CR2, RD, RB, SP, CH) — got {instrument!r} in {context}"
            ),
            line=source_line,
        )


def _validate_flam_instrument(
    instrument: str,
    modifiers: list[str],
    context: str,
    source_line: int | None = None,
    grace_instrument: str | None = None,
) -> None:
    """Validate flam/drag instrument constraints.

    A ``flam``/``drag`` modifier requires a grace-capable instrument to carry
    the grace stroke(s). With same-instrument flam/drag (``grace_instrument is
    None``), the main hit's instrument must be in ``_FLAM_INSTRUMENTS``. With
    cross-instrument flam/drag, the grace instrument must be in
    ``_FLAM_INSTRUMENTS`` and the main hit's instrument is unrestricted.
    """
    if "flam" not in modifiers and "drag" not in modifiers:
        return
    ornament = "flam" if "flam" in modifiers else "drag"
    if grace_instrument is not None:
        if grace_instrument not in _FLAM_INSTRUMENTS:
            raise GrooveScriptError(
                message=(
                    f"{ornament!r} grace instrument must be a snare or tom "
                    f"(SN, FT, HT, MT) — got {grace_instrument!r} in {context}"
                ),
                line=source_line,
            )
        return
    if instrument not in _FLAM_INSTRUMENTS:
        raise GrooveScriptError(
            message=(
                f"{ornament!r} modifier is only supported on snare and toms "
                f"(SN, FT, HT, MT) — got {instrument!r} in {context}; use "
                f"{ornament}:<inst> to set the grace instrument explicitly"
            ),
            line=source_line,
        )


def _star_hits_per_bar(
    star: StarSpec, beats_per_bar: int, beat_unit: int, context: str
) -> int:
    """Return the number of hits a ``*N``/``*Nt``/``*<kind>`` produces in one bar.

    Raises :class:`ValueError` if the star is incompatible with the time
    signature (e.g. ``*2`` in 6/8 produces a non-integer number of half-notes
    per bar).
    """
    if star.tuplet_kind is not None:
        actual, _ = _tuplet_ratio_for_kind(star.tuplet_kind)
        # Each beat carries one tuplet of ``actual`` slots when span = 1
        # beat; two when span = 1/2; four when span = 1/4. Total hits =
        # beats_per_bar * actual / span_in_beats.
        span_in_beats = star.tuplet_span
        if span_in_beats <= 0 or beats_per_bar % 1 != 0:
            raise ValueError(
                f"{star}: invalid span {star.tuplet_span} in {context}"
            )
        # tuplets per bar = beats_per_bar / span_in_beats; this must be an integer
        per_bar = Fraction(beats_per_bar) / span_in_beats
        if per_bar.denominator != 1:
            raise ValueError(
                f"{star} does not divide {beats_per_bar}/{beat_unit} evenly in {context}"
            )
        return int(per_bar) * actual
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


def _tuplet_ratio_for_kind(kind: str) -> tuple[int, int]:
    """Look up the (actual, normal) ratio for a named tuplet kind."""
    from .ast_nodes import _TUPLET_RATIOS
    if kind not in _TUPLET_RATIOS:
        raise ValueError(f"unknown tuplet kind: {kind!r}")
    return _TUPLET_RATIOS[kind]


def _star_min_slots_per_beat(star: StarSpec, beat_unit: int) -> int:
    """Smallest slots-per-beat that can place every hit of ``star`` on a slot.

    For straight ``*N``: min = N / gcd(N, beat_unit).
    For triplet ``*Nt``: min = 3N / gcd(2*beat_unit, 3N).
    For named-tuplet ``*<kind>``: actual slots over the span. Whole-beat
    tuplet → ``actual``; half-beat tuplet → ``2*actual``.
    """
    if star.tuplet_kind is not None:
        actual, _ = _tuplet_ratio_for_kind(star.tuplet_kind)
        if star.tuplet_span == Fraction(1):
            return actual
        if star.tuplet_span == Fraction(1, 2):
            return actual * 2
        if star.tuplet_span == Fraction(1, 4):
            return actual * 4
        raise ValueError(
            f"{star}: unsupported span {star.tuplet_span}"
        )
    n = star.note_value
    if star.triplet:
        return (3 * n) // gcd(2 * beat_unit, 3 * n)
    return n // gcd(n, beat_unit)


def _label_min_slots_per_beat(label: str) -> int:
    """Smallest slots-per-beat needed to place a beat label on a slot.

    Plain digit → 1, ``&`` → 2, ``e``/``a`` → 4, ``t``/``l`` → 3. Synthetic
    tuplet-slot labels (``~T…``) contribute the tuplet's ``actual`` slots
    per beat.
    """
    if not label:
        return 1
    if label.startswith("~T"):
        from .parser_notation import _decode_tuplet_slot_label
        decoded = _decode_tuplet_slot_label(label)
        if decoded is not None:
            _anchor, _slot, actual, _normal = decoded
            return actual
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


def _tuplet_anchor_offset(anchor: str, beats_per_bar: int) -> Fraction:
    """Convert a tuplet group's anchor label to a bar-relative ``Fraction``.

    Reuses :func:`_beat_label_to_fraction`, which already handles every
    suffix variant (``2&``, ``3a``, ``1t``, …). The ``subdivision`` argument
    is ignored by that function.
    """
    return _beat_label_to_fraction(anchor, subdivision=0, beats_per_bar=beats_per_bar)


def _tuplet_slot_offset(
    group: TupletGroup,
    slot_index: int,
    beats_per_bar: int,
) -> Fraction:
    """Bar-relative position of a TupletGroup slot, as a ``Fraction``.

    A tuplet's slots are evenly spaced over its ``span`` (in beats), starting
    at the anchor label. Slot index is 1-based.
    """
    anchor = _tuplet_anchor_offset(group.anchor, beats_per_bar)
    actual, _ = group.ratio
    # span is in beats; convert to bar-relative by dividing by beats_per_bar.
    span_in_bar = group.span / beats_per_bar
    return anchor + Fraction(slot_index - 1, actual) * span_in_bar


def _collect_tuplet_groups(
    lines: list[PatternLine],
    beats_per_bar: int,
) -> list[TupletGroup]:
    """Pull every TupletGroup that appears in the bar's pattern lines.

    Also synthesises TupletGroups from any ``*<kind>[/N]`` StarSpec, so
    downstream tuplet validation/annotation runs over a uniform set of
    groups regardless of whether the author wrote them inline or via the
    star shorthand.
    """
    out: list[TupletGroup] = []
    for line in lines:
        if isinstance(line.beats, StarSpec):
            star = line.beats
            if star.tuplet_kind is None:
                continue
            actual, normal = _tuplet_ratio_for_kind(star.tuplet_kind)
            span = star.tuplet_span
            # Walk every (beat, half) anchor that the star covers and emit a
            # synthetic TupletGroup at each. Slots are 1..actual.
            tuplets_per_beat = int(Fraction(1) / span)
            for beat_idx in range(beats_per_bar):
                for sub_idx in range(tuplets_per_beat):
                    anchor_beat = beat_idx + 1
                    if span == Fraction(1):
                        anchor = str(anchor_beat)
                    elif span == Fraction(1, 2):
                        anchor = f"{anchor_beat}&" if sub_idx == 1 else str(anchor_beat)
                    else:
                        # /16 span — unusual, label by 16th-grid suffix.
                        suffix_for_idx = ["", "e", "&", "a"]
                        anchor = f"{anchor_beat}{suffix_for_idx[sub_idx]}"
                    out.append(
                        TupletGroup(
                            kind=star.tuplet_kind,
                            ratio=(actual, normal),
                            span=span,
                            anchor=anchor,
                            slots=[],  # slots aren't needed for classification
                            line=line.line,
                        )
                    )
            continue
        for item in line.beats:
            if isinstance(item, TupletGroup):
                out.append(item)
    return out


def _classify_bar_tuplets(
    lines: list[PatternLine],
    beats_per_bar: int,
    context: str,
) -> list[object]:
    """Build the per-beat tuplet annotation for ``IRBar.beat_tuplets``.

    Walks every TupletGroup in the bar, slots it into the right beat
    (and half-beat for ``/8`` qualifier), and rejects any conflict where
    two groups would land on the same slot with different ratios.

    Returns a list of length ``beats_per_bar`` whose entries are either
    ``None`` (straight beat), a ``("full", actual, normal)`` tuple, or a
    ``("halves", left, right)`` tuple. Returns an empty list if the bar
    contains no tuplet groups.
    """
    groups = _collect_tuplet_groups(lines, beats_per_bar)
    if not groups:
        return []

    # beat_idx (0-based) -> "full" tuplet ratio
    full: dict[int, tuple[int, int]] = {}
    # (beat_idx, "left"|"right") -> half-beat tuplet ratio
    halves: dict[tuple[int, str], tuple[int, int]] = {}

    for group in groups:
        anchor_pos = _tuplet_anchor_offset(group.anchor, beats_per_bar)  # bar-relative
        beat_offset = anchor_pos * beats_per_bar  # in beats
        beat_idx_frac = beat_offset
        beat_idx = int(beat_idx_frac)
        within_beat = beat_idx_frac - beat_idx
        if group.span == Fraction(1):
            if within_beat != 0:
                raise GrooveScriptError(
                    message=(
                        f"whole-beat {group.kind} group must anchor on a beat "
                        f"downbeat (got anchor {group.anchor!r}) in {context}; "
                        f"use ``/8`` for a half-beat tuplet"
                    ),
                    line=group.line,
                )
            if (beat_idx, "left") in halves or (beat_idx, "right") in halves:
                raise GrooveScriptError(
                    message=(
                        f"beat {beat_idx + 1}: cannot mix a whole-beat tuplet "
                        f"with a half-beat tuplet on the same beat in {context}"
                    ),
                    line=group.line,
                )
            existing = full.get(beat_idx)
            if existing is not None and existing != group.ratio:
                raise GrooveScriptError(
                    message=(
                        f"beat {beat_idx + 1}: declared as both {existing[0]}:"
                        f"{existing[1]} and {group.ratio[0]}:{group.ratio[1]} "
                        f"by different lines in {context} (only one tuplet "
                        f"kind per beat is supported)"
                    ),
                    line=group.line,
                )
            full[beat_idx] = group.ratio
        elif group.span == Fraction(1, 2):
            if within_beat == 0:
                half = "left"
            elif within_beat == Fraction(1, 2):
                half = "right"
            else:
                raise GrooveScriptError(
                    message=(
                        f"half-beat {group.kind} group must anchor on a "
                        f"downbeat or its 8th-note offbeat (got anchor "
                        f"{group.anchor!r}) in {context}"
                    ),
                    line=group.line,
                )
            if beat_idx in full:
                raise GrooveScriptError(
                    message=(
                        f"beat {beat_idx + 1}: cannot mix a whole-beat tuplet "
                        f"with a half-beat tuplet on the same beat in {context}"
                    ),
                    line=group.line,
                )
            existing = halves.get((beat_idx, half))
            if existing is not None and existing != group.ratio:
                raise GrooveScriptError(
                    message=(
                        f"beat {beat_idx + 1} {half} half: declared as both "
                        f"{existing[0]}:{existing[1]} and {group.ratio[0]}:"
                        f"{group.ratio[1]} by different lines in {context}"
                    ),
                    line=group.line,
                )
            halves[(beat_idx, half)] = group.ratio
        else:
            # /16 = quarter-beat span, etc. Not supported in this iteration.
            raise GrooveScriptError(
                message=(
                    f"{group.kind} with span {group.span} beats is not "
                    f"supported (currently /4 = whole beat and /8 = half beat) "
                    f"in {context}"
                ),
                line=group.line,
            )

    annotations: list[object] = []
    for beat_idx in range(beats_per_bar):
        if beat_idx in full:
            actual, normal = full[beat_idx]
            annotations.append(("full", actual, normal))
        elif (beat_idx, "left") in halves or (beat_idx, "right") in halves:
            left = halves.get((beat_idx, "left"))
            right = halves.get((beat_idx, "right"))
            annotations.append(("halves", left, right))
        else:
            annotations.append(None)
    return annotations


def _tuplet_slot_positions(
    annot, beat_idx: int, beats_per_bar: int
) -> set[Fraction]:
    """Bar-relative positions where events are allowed inside a beat with
    annotation ``annot``.

    For ``("full", actual, normal)``: the ``actual`` evenly-spaced slot
    positions across the beat. For ``("halves", left, right)``: each half's
    slot positions (or the half-start and half-mid for a non-tuplet half).
    """
    beat_start = Fraction(beat_idx, beats_per_bar)
    beat_span = Fraction(1, beats_per_bar)
    out: set[Fraction] = set()
    if annot is None:
        return out
    if isinstance(annot, tuple) and annot and annot[0] == "full":
        _, actual, _ = annot
        for k in range(actual):
            out.add(beat_start + Fraction(k, actual) * beat_span)
        return out
    if isinstance(annot, tuple) and annot and annot[0] == "halves":
        _, left, right = annot
        half_span = beat_span / 2
        for half_start, ratio in (
            (beat_start, left),
            (beat_start + half_span, right),
        ):
            if ratio is None:
                # Non-tuplet half — allow the half-start and the 16th-of-beat
                # midpoint of the half (matching the engraver's two-event
                # straight-half handling).
                out.add(half_start)
                out.add(half_start + half_span / 2)
            else:
                actual, _ = ratio
                for k in range(actual):
                    out.add(half_start + Fraction(k, actual) * half_span)
        return out
    return out


def _validate_tuplet_grid_alignment(
    events,
    beat_tuplets: list,
    beats_per_bar: int,
    context: str,
) -> None:
    """Reject events that fall inside a tuplet beat at a non-slot position.

    Without this check, the LilyPond and MusicXML emitters would silently
    drop the off-tuplet hit because they walk only the slot positions.
    """
    if not beat_tuplets or not any(beat_tuplets):
        return
    for event in events:
        beat_idx_frac = event.beat_position * beats_per_bar
        beat_idx = int(beat_idx_frac)
        if beat_idx < 0 or beat_idx >= len(beat_tuplets):
            continue
        annot = beat_tuplets[beat_idx]
        if annot is None:
            continue
        allowed = _tuplet_slot_positions(annot, beat_idx, beats_per_bar)
        if event.beat_position in allowed:
            continue
        # Build a friendly diagnostic naming the tuplet kind on the beat.
        if isinstance(annot, tuple) and annot[0] == "full":
            _, actual, normal = annot
            kind_desc = f"{actual}:{normal} tuplet"
        elif isinstance(annot, tuple) and annot[0] == "halves":
            kind_desc = "half-beat tuplet"
        else:
            kind_desc = "tuplet"
        raise GrooveScriptError(
            message=(
                f"{event.instrument} hit at beat position {event.beat_position} "
                f"falls inside a {kind_desc} on beat {beat_idx + 1} but is not "
                f"on one of its slot positions ({context}); place the hit on "
                f"a tuplet slot or remove the tuplet annotation"
            ),
            line=getattr(event, "source_line", None),
        )


def _validate_fill_not_inside_tuplet(
    bar_beat_tuplets: list,
    start_position: Fraction,
    beats_per_bar: int,
    context: str,
) -> None:
    """Reject a fill whose start position falls inside an existing tuplet
    beat at a non-slot position.

    The merge logic that overlays a fill on a groove bar can't represent
    "first half of a tuplet beat from the groove + fill content from the
    middle of the same tuplet beat onward". Either move the fill to a
    beat boundary, or remove the tuplet on that beat.
    """
    if not bar_beat_tuplets:
        return
    beat_idx_frac = start_position * beats_per_bar
    beat_idx = int(beat_idx_frac)
    within_beat = beat_idx_frac - beat_idx
    if within_beat == 0:
        return  # fill starts at a beat boundary — clean replacement
    if beat_idx < 0 or beat_idx >= len(bar_beat_tuplets):
        return
    annot = bar_beat_tuplets[beat_idx]
    if annot is None:
        return
    allowed = _tuplet_slot_positions(annot, beat_idx, beats_per_bar)
    if start_position in allowed:
        return
    raise GrooveScriptError(
        message=(
            f"fill placement at beat-position {start_position} falls inside "
            f"a tuplet on beat {beat_idx + 1} ({context}); place the fill "
            f"on a beat boundary or on a tuplet slot"
        ),
    )


def _infer_bar_subdivision(
    lines: list[PatternLine],
    beats_per_bar: int,
    beat_unit: int,
    context: str,
) -> int:
    """Infer the slot grid for a bar of pattern lines.

    Picks a single ``slots_per_beat`` that accommodates every explicit
    label, every ``*N``/``*Nt`` star, and every TupletGroup in the bar.
    Raises :class:`ValueError` if no grid fits — e.g. when a ``*N`` produces
    a non-integer number of hits in the time signature.
    """
    straight_needed = 1  # plain beats
    has_triplet_content = False
    has_straight_content = False  # any straight label or *N
    tuplet_actuals: list[int] = []  # additional tuplet ratios to LCM in

    for line in lines:
        if isinstance(line.beats, StarSpec):
            star = line.beats
            # Validate hit count up-front so we get a clean error instead
            # of a cryptic slot-math failure later.
            try:
                _star_hits_per_bar(star, beats_per_bar, beat_unit, context)
            except ValueError as exc:
                raise GrooveScriptError(message=str(exc), line=line.line) from None
            if star.triplet:
                has_triplet_content = True
            else:
                has_straight_content = True
                straight_needed = max(
                    straight_needed, _star_min_slots_per_beat(star, beat_unit)
                )
            continue
        for beat in line.beats:
            if isinstance(beat, TupletGroup):
                actual, _ = beat.ratio
                # Half-beat tuplets need actual*2 slots per beat; whole-beat
                # tuplets need actual slots per beat. /16 would need actual*4
                # but isn't reached here (rejected upstream).
                slots_for_group = (
                    actual if beat.span == Fraction(1) else actual * 2
                )
                tuplet_actuals.append(slots_for_group)
                continue
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

    # Fold in any TupletGroup ratios. ``lcm(*[])`` is 1, so a bar without
    # tuplets keeps the legacy grid exactly.
    if tuplet_actuals:
        slots_per_beat = lcm(slots_per_beat, *tuplet_actuals)

    # Final sanity check for *Nt triplets that need more slots than the
    # tuplet-extended grid can provide.
    for line in lines:
        if isinstance(line.beats, StarSpec):
            need = _star_min_slots_per_beat(line.beats, beat_unit)
            if need > slots_per_beat and slots_per_beat % need != 0:
                raise GrooveScriptError(
                    message=(
                        f"{line.beats} requires {need} slots per beat, which is "
                        f"not supported (max supported is 4 straight / 3 triplet) "
                        f"in {context}"
                    ),
                    line=line.line,
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
        # Compute positions to exclude (from the ``except`` clause).
        except_positions: set[Fraction] = set()
        if star.except_beats:
            for label in star.except_beats:
                except_positions.add(
                    _beat_label_to_fraction(label, subdivision, beats_per_bar)
                )
        if star.tuplet_kind is not None:
            actual, _ = _tuplet_ratio_for_kind(star.tuplet_kind)
            span = star.tuplet_span
            tuplets_per_beat = int(Fraction(1) / span)
            events: list[Event] = []
            for beat_idx in range(beats_per_bar):
                for sub_idx in range(tuplets_per_beat):
                    anchor_pos = (
                        Fraction(beat_idx, beats_per_bar)
                        + Fraction(sub_idx) * (span / beats_per_bar)
                    )
                    span_in_bar = span / beats_per_bar
                    for slot in range(actual):
                        pos = anchor_pos + Fraction(slot, actual) * span_in_bar
                        if pos in except_positions:
                            continue
                        events.append(
                            Event(
                                bar=bar,
                                beat_position=pos,
                                instrument=line.instrument,
                                source_line=line.line,
                            )
                        )
            return events
        try:
            hits = _star_hits_per_bar(star, beats_per_bar, beat_unit, f"instrument {line.instrument!r}")
        except ValueError as exc:
            raise GrooveScriptError(message=str(exc), line=line.line) from None
        if subdivision % hits != 0:
            raise GrooveScriptError(
                message=(
                    f"{star} on instrument {line.instrument!r}: bar subdivision "
                    f"{subdivision} is not a multiple of {hits} hits"
                ),
                line=line.line,
            )
        step = subdivision // hits
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
        if isinstance(b, TupletGroup):
            # Each slot expands to one Event at its evenly-spaced position
            # within the tuplet's span, with the slot's own modifiers.
            for slot in b.slots:
                pos = _tuplet_slot_offset(b, slot.index, beats_per_bar)
                mods = list(slot.modifiers)
                ctx = (
                    f"instrument {line.instrument!r} at "
                    f"{b.kind} slot {slot.index} (anchor {b.anchor!r})"
                )
                if mods:
                    _validate_buzz_modifier_compat(mods, ctx, source_line=line.line)
                    _validate_flam_instrument(
                        line.instrument, mods, ctx,
                        source_line=line.line,
                        grace_instrument=slot.grace_instrument,
                    )
                    _validate_choke_instrument(
                        line.instrument, mods, ctx, source_line=line.line
                    )
                    if "double" in mods:
                        # 'double' is defined as a slot's worth = two 32nds;
                        # inside a tuplet this stops being meaningful.
                        raise GrooveScriptError(
                            message=(
                                f"'double' modifier is not allowed inside a "
                                f"tuplet group ({ctx})"
                            ),
                            line=line.line,
                        )
                    if "buzz" in mods:
                        # The tuplet emitter renders one note per slot and has
                        # no path for the buzz tremolo decoration; previously
                        # the buzz was silently downgraded to a plain hit.
                        raise GrooveScriptError(
                            message=(
                                f"'buzz' modifier is not allowed inside a "
                                f"tuplet group ({ctx}); the tremolo would not "
                                f"be rendered"
                            ),
                            line=line.line,
                        )
                events.append(
                    Event(
                        bar=bar,
                        beat_position=pos,
                        instrument=line.instrument,
                        modifiers=mods,
                        grace_instrument=slot.grace_instrument,
                        source_line=line.line,
                    )
                )
            continue
        position = _beat_label_to_fraction(str(b), subdivision, beats_per_bar)
        mods = getattr(b, "modifiers", [])
        buzz_dur_str = getattr(b, "buzz_duration", None)
        grace_inst = getattr(b, "grace_instrument", None)
        if mods:
            _validate_double_modifier(mods, subdivision, f"instrument {line.instrument!r} at beat {b!r}", source_line=line.line)
            _validate_buzz_modifier_compat(mods, f"instrument {line.instrument!r} at beat {b!r}", source_line=line.line)
            _validate_flam_instrument(line.instrument, mods, f"instrument {line.instrument!r} at beat {b!r}", source_line=line.line, grace_instrument=grace_inst)
            _validate_choke_instrument(line.instrument, mods, f"instrument {line.instrument!r} at beat {b!r}", source_line=line.line)
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
                grace_instrument=grace_inst,
                source_line=line.line,
            )
        )
    return events


def _expand_groove_count_notes(
    count_str: str,
    notes_str: str,
    beats_per_bar: int,
) -> tuple[int, list[PatternLine], list[object]]:
    """Expand a groove's count+notes body into (subdivision, pattern lines,
    beat tuplets).

    Uses the same count/notes tokenisers as fills and groups the resulting
    hits by instrument so they can be stored as ``PatternLine`` objects.
    Inline ``{kind …}`` tuplet groups in ``count_str`` produce per-beat
    tuplet annotations that the LilyPond / MusicXML emitters use to
    bracket the slots correctly.
    """
    # Deferred import to avoid a circular dependency (compiler ↔ parser).
    from .parser import (
        _format_count_notes_mismatch,
        _parse_count_tokens,
        _parse_notes_tokens,
    )
    from .parser_notation import _extract_count_tuplet_groups

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

    # Build per-beat tuplet annotations from the count string itself.
    beat_tuplets = _build_beat_tuplets_from_count(count_str, beats_per_bar)
    return subdivision, lines, beat_tuplets


def _build_beat_tuplets_from_count(
    count_str: str, beats_per_bar: int
) -> list[object]:
    """Produce a per-beat tuplet annotation list from the inline ``{kind …}``
    groups in a count string. Empty list if the count string has no tuplet
    groups; otherwise length ``beats_per_bar`` with ``None`` for non-tuplet
    beats and ``("full", actual, normal)`` for tuplet beats.
    """
    from .parser_notation import _extract_count_tuplet_groups

    groups = _extract_count_tuplet_groups(count_str)
    if not groups:
        return []
    annotations: list[object] = [None] * beats_per_bar
    for anchor, _kind, actual, normal, _slots in groups:
        try:
            anchor_pos = _beat_label_to_fraction(anchor, 0, beats_per_bar)
        except ValueError as exc:
            raise GrooveScriptError(message=str(exc)) from None
        beat_offset = anchor_pos * beats_per_bar
        beat_idx = int(beat_offset)
        if beat_offset != beat_idx:
            raise GrooveScriptError(
                message=(
                    f"count tuplet group anchored at {anchor!r} must start on "
                    f"a beat downbeat (use the inline pattern-line form for "
                    f"sub-beat tuplets)"
                )
            )
        existing = annotations[beat_idx]
        new = ("full", actual, normal)
        if existing is not None and existing != new:
            raise GrooveScriptError(
                message=(
                    f"beat {beat_idx + 1}: declared as both {existing[1]}:"
                    f"{existing[2]} and {actual}:{normal} by different count "
                    f"groups"
                )
            )
        annotations[beat_idx] = new
    return annotations


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
        subdivision, lines, count_beat_tuplets = _expand_groove_count_notes(
            count_str, notes_str, beats_per_bar
        )
        # When ``groove.bars`` is also populated, the groove was produced by
        # ``_resolve_groove_extends`` extending a count+notes base. The
        # extending groove's pattern lines live in ``bars`` and need to be
        # merged on top of the count+notes expansion so newly-added
        # instruments survive while the base pattern (and its tuplet
        # annotations) is preserved.
        if groove.bars:
            overlay_lines = groove.bars[0]
            merged: dict[str, PatternLine] = {pl.instrument: pl for pl in lines}
            for pl in overlay_lines:
                merged[pl.instrument] = pl
            lines = list(merged.values())
            # Re-infer subdivision so a 16th-note overlay on an 8th-note
            # count+notes base bumps the grid (and vice versa).
            overlay_subdivision = _infer_bar_subdivision(
                lines, beats_per_bar, beat_unit,
                f"groove {groove.name!r} bar 1",
            )
            subdivision = max(subdivision, overlay_subdivision)
        bars = [lines]
        per_bar_subdivisions = [subdivision]
        per_bar_beat_tuplets: list[list[object]] = [count_beat_tuplets]
    else:
        bars = groove.bars
        per_bar_subdivisions = [
            _infer_bar_subdivision(
                lines, beats_per_bar, beat_unit,
                f"groove {groove.name!r} bar {bar_idx + 1}",
            )
            for bar_idx, lines in enumerate(bars)
        ]
        per_bar_beat_tuplets = [
            _classify_bar_tuplets(
                lines, beats_per_bar,
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

    # Apply any variation actions declared via ``extend:`` one bar at a time.
    # Actions with ``bars=None`` target every bar; otherwise only the listed
    # bars are affected. This runs before 'double' / buzz validation so that
    # events introduced by the actions go through the same checks as the
    # pattern-line events.
    if groove.extend_variations:
        events_by_bar: dict[int, list[Event]] = {}
        for event in events:
            events_by_bar.setdefault(event.bar, []).append(event)
        # Ensure every declared bar exists in the map so actions targeting
        # an empty bar (e.g. ``add CR at 1`` on a bar that has no events
        # yet) still run.
        for bar_number in range(1, len(bars) + 1):
            events_by_bar.setdefault(bar_number, [])

        for bar_number in sorted(events_by_bar):
            subdivision = per_bar_subdivisions[bar_number - 1]
            bar_events = events_by_bar[bar_number]
            for ev in groove.extend_variations:
                if ev.bars is not None and bar_number not in ev.bars:
                    continue
                bar_events = _apply_variation_actions(
                    bar_events,
                    ev.actions,
                    subdivision,
                    bar_number,
                    beats_per_bar,
                    beat_unit,
                )
            events_by_bar[bar_number] = bar_events

        events = []
        for bar_number in sorted(events_by_bar):
            events.extend(events_by_bar[bar_number])

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
        bar_ctx = f"groove {groove.name!r} bar {bar_number}"
        _validate_buzz_overlap(bar_events, bar_ctx)
        _validate_grace_uniqueness(bar_events, bar_ctx)
        _validate_instrument_mutex(bar_events, bar_ctx)
        _validate_tuplet_grid_alignment(
            bar_events, per_bar_beat_tuplets[bar_number - 1], beats_per_bar, bar_ctx
        )

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
        bar_beat_tuplets=list(per_bar_beat_tuplets),
    )


@dataclass
class IRFillBar:
    """One bar of fill events ready to overlay onto groove events."""

    events: list[Event]
    subdivision: int
    # Per-beat tuplet annotations (same shape as IRBar.beat_tuplets). Empty
    # when the fill has no tuplet groups; passed through to IRBar via
    # ``_apply_fill_overlay`` so the emitter brackets the fill correctly.
    beat_tuplets: list[object] = field(default_factory=list)


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
            grace_inst = getattr(inst_hit, "grace_instrument", None)
            if mods:
                _validate_double_modifier(mods, subdivision, f"fill at beat {line.beat!r}")
                _validate_buzz_modifier_compat(mods, f"fill at beat {line.beat!r}")
                _validate_flam_instrument(str(inst_hit), mods, f"fill at beat {line.beat!r}", grace_instrument=grace_inst)
                _validate_choke_instrument(str(inst_hit), mods, f"fill at beat {line.beat!r}")
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
                    grace_instrument=grace_inst,
                )
            )
    # Expand star-spec pattern lines (e.g. BD: *8 except 4&).
    for pline in fill_bar.pattern_lines:
        events.extend(_expand_pattern_line(pline, subdivision, 1, beats_per_bar, beat_unit))
    fill_bar_desc = f"fill bar {fill_bar.label!r}" if fill_bar.label else "fill bar"
    if any("double" in e.modifiers for e in events):
        _validate_double_subdivision(subdivision, beats_per_bar, fill_bar_desc)
    # Validate buzz event positions and hand-played overlap.
    for event in events:
        _validate_buzz_event(event, beats_per_bar, fill_bar_desc)
    _validate_buzz_overlap(events, fill_bar_desc)
    _validate_instrument_mutex(events, fill_bar_desc)
    events.sort(key=lambda e: e.beat_position)
    # Build the per-beat tuplet annotation from the pattern_lines (the only
    # place TupletGroups can appear in a fill body).
    beat_tuplets = _classify_bar_tuplets(
        fill_bar.pattern_lines, beats_per_bar,
        f"fill {fill_bar.label!r}" if fill_bar.label else "fill",
    )
    _validate_tuplet_grid_alignment(events, beat_tuplets, beats_per_bar, fill_bar_desc)
    return IRFillBar(events=events, subdivision=subdivision, beat_tuplets=beat_tuplets)


def _merge_fill_beat_tuplets(
    groove_tuplets: list,
    fill_tuplets: list,
    start_position: Fraction,
    beats_per_bar: int,
) -> list:
    """Merge a fill's per-beat tuplet annotations into the groove's, taking
    effect from ``start_position`` (a bar-relative ``Fraction``) onward.

    The fill's annotation for a given beat overrides the groove's; beats
    before ``start_position`` keep the groove's annotation. When neither
    side annotates a tuplet for a particular beat the result is None.
    """
    if not fill_tuplets and not groove_tuplets:
        return []
    base = list(groove_tuplets) if groove_tuplets else [None] * beats_per_bar
    # Pad both lists out to beats_per_bar so indexing is uniform.
    while len(base) < beats_per_bar:
        base.append(None)
    fill_padded = list(fill_tuplets) if fill_tuplets else [None] * beats_per_bar
    while len(fill_padded) < beats_per_bar:
        fill_padded.append(None)
    start_beat = int(start_position * beats_per_bar)
    merged: list = []
    for beat_idx in range(beats_per_bar):
        if beat_idx < start_beat:
            merged.append(base[beat_idx])
        else:
            merged.append(fill_padded[beat_idx])
    return merged


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
            grace_instrument=fe.grace_instrument,
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
                raise GrooveScriptError(
                    message="substitute action missing count_notes body",
                    line=action.line,
                )
            from .parser import (
                _format_count_notes_mismatch,
                _parse_count_tokens,
                _parse_notes_tokens,
            )

            count_str, notes_str = action.count_notes
            beat_labels = _parse_count_tokens(count_str)
            note_groups = _parse_notes_tokens(notes_str)
            if len(beat_labels) != len(note_groups):
                raise GrooveScriptError(
                    message=_format_count_notes_mismatch(
                        "variation substitute", count_str, notes_str
                    ),
                    line=action.line,
                )
            # Substitute wipes everything in the bar, then places the new events.
            result = []
            for label, hits in zip(beat_labels, note_groups):
                position = _beat_label_to_fraction(label, subdivision, beats_per_bar)
                for hit in hits:
                    mods = getattr(hit, "modifiers", []) or []
                    grace_inst = getattr(hit, "grace_instrument", None)
                    if mods:
                        _validate_flam_instrument(
                            str(hit),
                            mods,
                            f"variation substitute at beat {label!r}",
                            source_line=action.line,
                            grace_instrument=grace_inst,
                        )
                        _validate_choke_instrument(
                            str(hit),
                            mods,
                            f"variation substitute at beat {label!r}",
                            source_line=action.line,
                        )
                    result.append(
                        Event(
                            bar=absolute_bar,
                            beat_position=position,
                            instrument=str(hit),
                            modifiers=list(mods),
                            grace_instrument=grace_inst,
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
                _validate_double_modifier(action.modifiers, subdivision, f"variation add {action.instrument!r}", source_line=action.line)
                _validate_buzz_modifier_compat(action.modifiers, f"variation add {action.instrument!r}", source_line=action.line)
                _validate_flam_instrument(action.instrument, action.modifiers, f"variation add {action.instrument!r}", source_line=action.line, grace_instrument=action.grace_instrument)
                _validate_choke_instrument(action.instrument, action.modifiers, f"variation add {action.instrument!r}", source_line=action.line)
                if "double" in action.modifiers:
                    _validate_double_subdivision(subdivision, beats_per_bar, f"variation add {action.instrument!r}", source_line=action.line)
            duration: Fraction | None = None
            if "buzz" in action.modifiers:
                duration = _buzz_span(action.buzz_duration or "4", beats_per_bar, beat_unit)
            occupied = {e.beat_position for e in result if e.instrument == action.instrument}
            for pos in sorted(positions):
                if pos in occupied:
                    raise GrooveScriptError(
                        message=(
                            f"variation add {action.instrument!r} at {_beat_label_for(pos, beats_per_bar)} "
                            f"(bar {absolute_bar}): a {action.instrument!r} note is already present "
                            f"at that position — adding would stack two notes on top of each other"
                        ),
                        line=action.line,
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
                        grace_instrument=action.grace_instrument,
                        source_line=action.line,
                    )
                )
        elif action.action == "replace":
            if action.modifiers:
                _validate_double_modifier(action.modifiers, subdivision, f"variation replace → {action.target_instrument!r}", source_line=action.line)
                _validate_buzz_modifier_compat(action.modifiers, f"variation replace → {action.target_instrument!r}", source_line=action.line)
                _validate_flam_instrument(action.target_instrument, action.modifiers, f"variation replace → {action.target_instrument!r}", source_line=action.line, grace_instrument=action.grace_instrument)
                _validate_choke_instrument(action.target_instrument, action.modifiers, f"variation replace → {action.target_instrument!r}", source_line=action.line)
                if "double" in action.modifiers:
                    _validate_double_subdivision(subdivision, beats_per_bar, f"variation replace → {action.target_instrument!r}", source_line=action.line)
            # "at *" means "wherever the source instrument actually plays" —
            # restrict to existing source hits so we don't stamp the target at
            # grid slots that the source never occupied.
            if action.beats == "*":
                replace_positions = {
                    e.beat_position for e in result if e.instrument == action.instrument
                }
            else:
                replace_positions = positions
            result = [
                e for e in result
                if not (e.instrument == action.instrument and e.beat_position in replace_positions)
            ]
            duration = None
            if "buzz" in action.modifiers:
                duration = _buzz_span(action.buzz_duration or "4", beats_per_bar, beat_unit)
            occupied = {e.beat_position for e in result if e.instrument == action.target_instrument}
            for pos in sorted(replace_positions):
                if pos in occupied:
                    raise GrooveScriptError(
                        message=(
                            f"variation replace {action.instrument!r} with {action.target_instrument!r} "
                            f"at {_beat_label_for(pos, beats_per_bar)} (bar {absolute_bar}): a "
                            f"{action.target_instrument!r} note is already present at that position — "
                            f"replace would stack two notes on top of each other"
                        ),
                        line=action.line,
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
                        grace_instrument=action.grace_instrument,
                        source_line=action.line,
                    )
                )
        elif action.action == "modify_add":
            # Add each modifier to the named instrument's events at the target
            # positions, skipping modifiers the event already carries.
            matched_positions: set[Fraction] = set()
            for event in result:
                if event.beat_position not in positions:
                    continue
                if event.instrument != action.instrument:
                    continue
                matched_positions.add(event.beat_position)
                # Resolve the effective grace instrument: explicit on the
                # action wins; otherwise inherit whatever the event already
                # carried.
                effective_grace = (
                    action.grace_instrument
                    if action.grace_instrument is not None
                    else event.grace_instrument
                )
                _validate_flam_instrument(
                    event.instrument,
                    action.modifiers,
                    f"variation modify add at beat {event.beat_position}",
                    source_line=action.line,
                    grace_instrument=effective_grace,
                )
                _validate_choke_instrument(
                    event.instrument,
                    action.modifiers,
                    f"variation modify add at beat {event.beat_position}",
                    source_line=action.line,
                )
                added_any = False
                for mod in action.modifiers:
                    if mod not in event.modifiers:
                        event.modifiers.append(mod)
                        added_any = True
                if action.grace_instrument is not None:
                    event.grace_instrument = action.grace_instrument
                if "buzz" in action.modifiers and action.buzz_duration is not None:
                    event.buzz_duration = action.buzz_duration
                    event.duration = _buzz_span(action.buzz_duration, beats_per_bar, beat_unit)
                # When a modifier was actually added, point diagnostics at the
                # variation line rather than the original pattern line: the
                # newly-stamped modifier is what can create notation conflicts.
                if added_any and action.line is not None:
                    event.source_line = action.line
            # Enforce that explicitly named beats actually contained a hit for
            # the targeted instrument. ``*`` (all beats) intentionally tolerates
            # gaps — it means "wherever that instrument plays". An explicit
            # beat list is almost always a typo when nothing matches.
            if action.beats != "*":
                missing = positions - matched_positions
                if missing:
                    missing_labels = ", ".join(
                        _beat_label_for(pos, beats_per_bar) for pos in sorted(missing)
                    )
                    raise GrooveScriptError(
                        message=(
                            f"variation modify add to {action.instrument!r} "
                            f"at {missing_labels} (bar {absolute_bar}): no "
                            f"{action.instrument!r} hit found at "
                            f"{'that beat' if len(missing) == 1 else 'those beats'} "
                            f"— modify add can only decorate existing hits, "
                            f"use 'add' to introduce a new note"
                        ),
                        line=action.line,
                    )
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
                    if mod in ("flam", "drag"):
                        # Removing the ornament also clears any cross-inst
                        # grace target so we don't leave dangling state.
                        event.grace_instrument = None

    result.sort(key=lambda e: e.beat_position)
    return result


# Tiebreak order when multiple instruments share the highest hit count in
# bar 1 of a ``crash in`` section. Cymbals/rides come first in the order
# drummers conventionally swap to crash at a section start.
_CRASH_IN_TIEBREAK_PRIORITY: tuple[str, ...] = ("RD", "HH", "OH", "CR", "HF")

# Instruments eligible to be the "rider" a crash-in replaces on beat 1. The
# rider is the timekeeping surface the dominant hand stays on, so cymbals,
# hi-hats, cowbell, and even toms (Rosanna-style floor-tom grooves) qualify.
# The snare and its side-stick articulation never do — they're the backbeat
# voice, not a ride surface. Excluding them matters when a fill piles snare
# hits into a bar: without this they could out-count the real ride and get
# mis-elected as rider, so the crash would be appended on beat 1 instead of
# swapping the ride out (leaving a stray ride sounding under the crash).
_RIDER_INSTRUMENTS: frozenset[str] = _HAND_INSTRUMENTS - frozenset({"SN", "SCS"})


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
        # Rider candidates are the timekeeping cymbal/hi-hat family only (see
        # ``_RIDER_INSTRUMENTS``) — the rider is the thing the dominant hand
        # keeps time on. Foot-played BD/HF and the snare/tom voices are not
        # eligible even if they dominate the hit count (e.g. a fill that piles
        # snare hits into the bar, or a variation that thins the ride pattern).
        counts: dict[str, int] = {}
        for event in result:
            if event.instrument not in _RIDER_INSTRUMENTS:
                continue
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
                    # Strip ornaments that don't belong on the new crash:
                    # ``ghost`` (a crash is never ghosted), and ``flam``/``drag``
                    # which require a snare/tom main or an explicit grace inst.
                    kept_modifiers = [
                        m for m in event.modifiers if m not in ("ghost", "flam", "drag")
                    ]
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


def _apply_break(events: list[Event], spec: BreakSpec, section_bar_offset: int, bpb: int, total_bars: int) -> list[Event]:
    """Remove events covered by *spec* for the bar at *section_bar_offset*.

    ``through`` forms (end_exclusive=False): silence events where
      start_frac <= beat_position <= end_frac  (both endpoints inclusive).
    ``until`` forms (end_exclusive=True): silence events where
      start_frac <= beat_position < end_frac   (end endpoint exclusive).
    For end bars with no end beat, ``until bar N`` excludes bar N entirely
    (effectively silences through bar N-1).

    *total_bars* is the section length; it determines the end of the break
    when no explicit end clause was given.
    """
    bar_number = section_bar_offset + 1  # convert to 1-indexed
    written_end_bar = spec.effective_end_bar(total_bars)

    # For ``until bar N`` with no end beat, bar N is the first un-silenced bar.
    if spec.end_exclusive and spec.end_beat is None:
        eff_end_bar = written_end_bar - 1
    else:
        eff_end_bar = written_end_bar

    if bar_number < spec.start_bar or bar_number > eff_end_bar:
        return events

    # Lower bound: None means start-of-bar (silence from position 0).
    if bar_number == spec.start_bar and spec.start_beat is not None:
        start_frac: Fraction | None = _beat_label_to_fraction(spec.start_beat, 0, bpb)
    else:
        start_frac = None

    # Upper bound: None means end-of-bar (silence through last event).
    if bar_number == written_end_bar and spec.end_beat is not None:
        end_frac: Fraction | None = _beat_label_to_fraction(spec.end_beat, 0, bpb)
    else:
        end_frac = None

    result = []
    for e in events:
        in_range = True
        if start_frac is not None and e.beat_position < start_frac:
            in_range = False
        if end_frac is not None:
            if spec.end_exclusive:
                if e.beat_position >= end_frac:
                    in_range = False
            else:
                if e.beat_position > end_frac:
                    in_range = False
        if not in_range:
            result.append(e)
    return result


def _validate_break_specs(specs: list[BreakSpec], section_name: str, total_bars: int) -> None:
    """Raise :class:`GrooveScriptError` for break specs that reference bars outside the section."""
    for spec in specs:
        eff_end = spec.effective_end_bar(total_bars)
        if spec.start_bar < 1 or spec.start_bar > total_bars:
            raise GrooveScriptError(
                message=(
                    f"Section {section_name!r}: break start bar {spec.start_bar} is out of "
                    f"range (1–{total_bars})"
                ),
            )
        if eff_end < spec.start_bar or eff_end > total_bars:
            raise GrooveScriptError(
                message=(
                    f"Section {section_name!r}: break end bar {eff_end} is out of "
                    f"range ({spec.start_bar}–{total_bars})"
                ),
            )


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
        # crash_in: child's spec wins when set, else inherit parent's. The
        # `no_crash_in` opt-out propagates the same way (and overrides any
        # inherited spec at compile time).
        merged_crash_in = section.crash_in if section.crash_in is not None else original.crash_in
        merged_no_crash_in = section.no_crash_in or original.no_crash_in

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
            no_crash_in=merged_no_crash_in,
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
) -> tuple[list[Event], int, list[object]]:
    """Compile a one-off play bar's pattern lines into
    ``(events, subdivision, beat_tuplets)``.

    Infers the bar's subdivision from its pattern lines and classifies
    any tuplet groups so the emitter can wrap each tuplet beat correctly.
    """
    subdivision = _infer_bar_subdivision(pattern, beats_per_bar, beat_unit, context)
    events: list[Event] = []
    for line in pattern:
        events.extend(
            _expand_pattern_line(line, subdivision, bar=1, beats_per_bar=beats_per_bar, beat_unit=beat_unit)
        )
    events.sort(key=lambda e: e.beat_position)
    beat_tuplets = _classify_bar_tuplets(pattern, beats_per_bar, context)
    return events, subdivision, beat_tuplets


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
        fill_bars = max(1, len(fill.bars))
        for span in fill.dynamic_spans:
            # Fill-internal spans are 1-indexed within the fill, so their bar
            # numbers must fall inside [1, fill_bars]. Silently accepting an
            # out-of-range bar would shift the span past the end of the
            # section and drop it from the output — surprising for users who
            # wrote the section-bar number (where the fill is placed) instead
            # of the fill-internal bar number.
            if not (1 <= span.from_bar <= fill_bars and 1 <= span.to_bar <= fill_bars):
                raise GrooveScriptError(
                    message=(
                        f"{span.kind} span inside fill placed at bar {fp.bar} "
                        f"references bar {span.from_bar} to bar {span.to_bar}, "
                        f"but the fill only has {fill_bars} bar(s) — "
                        f"bar numbers inside a fill are 1-indexed within the fill"
                    ),
                    line=span.line,
                    hint=(
                        f"write bars 1..{fill_bars} (fill-internal); the "
                        f"compiler shifts them to section-bar {fp.bar} at "
                        f"placement time"
                    ),
                )
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
        if base.is_placeholder:
            raise ValueError(
                f"Groove {name!r} extends placeholder groove {base_name!r}; "
                f"placeholder grooves have no pattern to inherit from"
            )
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

        # Carry the base's count_notes through extend resolution when present.
        # ``compile_groove`` will expand the count string and overlay the
        # ``merged_bars`` pattern lines on top, so a groove that extends a
        # count+notes base preserves the base's tuplet annotations and per-beat
        # subdivision (which can't be reconstructed from raw pattern lines).
        merged_count_notes = base.count_notes

        # Merge bar_texts: base first, then overlay extending groove's texts.
        merged_texts = dict(base.bar_texts)
        merged_texts.update(groove.bar_texts)

        # Carry dynamic spans through extend so a hairpin declared inside the
        # base groove (or the extending groove) survives to the emitter.
        merged_dynamic_spans = (
            list(base.dynamic_spans) + list(groove.dynamic_spans)
        )

        # Chain extend_variations: the resolved base already has any of its
        # own variations flattened into ``base.extend_variations``, so we
        # apply those first, then this groove's own actions on top.
        merged_extend_variations = (
            list(base.extend_variations) + list(groove.extend_variations)
        )

        # Validate that every scoped block targets a bar that actually exists
        # in the merged groove. Catching this at extend-resolution time gives
        # a clear error before the groove is compiled to events.
        # When ``merged_count_notes`` is set the bar count comes from the
        # count+notes expansion (always one bar today); ``merged_bars`` holds
        # only the extending overlay so its length isn't the user-visible bar
        # count and we shouldn't validate against it.
        max_bar = 1 if merged_count_notes is not None else len(merged_bars)
        for ev in merged_extend_variations:
            if ev.bars is None:
                continue
            for bar_num in ev.bars:
                if bar_num < 1 or bar_num > max_bar:
                    raise ValueError(
                        f"Groove {name!r}: variation targets bar {bar_num} "
                        f"but the groove only has {max_bar} bar(s)"
                    )

        groove_defs[name] = Groove(
            name=name,
            bars=merged_bars,
            bar_texts=merged_texts,
            count_notes=merged_count_notes,
            extend=None,  # mark as resolved
            dynamic_spans=merged_dynamic_spans,
            extend_variations=merged_extend_variations,
        )
        groove_bar_texts_map[name] = merged_texts

        resolving.discard(name)
        resolved.add(name)

    for gname in list(groove_defs):
        _resolve(gname)


def _resolve_fill_extends(fill_map: dict[str, Fill]) -> None:
    """Resolve ``extend:`` references on fills in-place.

    Fill extension is purely additive: the base fill's bars are used as
    a starting point and the extension's lines are appended on top. No
    override or subtraction semantics, so overlap (same instrument at
    the same beat) is the author's responsibility.

    Bar-alignment rules:
    - Extension with 0 bars: use base bars unchanged (extend-only alias).
    - Extension with 1 bar and base with >1 bars: broadcast the
      extension's lines to every base bar.
    - Extension with N bars (N <= base bars): merge bar-by-bar; any
      uncovered base bars are kept as-is.
    - Extension with more bars than the base: error — the extension
      cannot lengthen the fill.
    """
    resolved: set[str] = set()
    resolving: set[str] = set()

    def _resolve(name: str) -> None:
        if name in resolved:
            return
        fill = fill_map.get(name)
        if fill is None or fill.extend is None:
            resolved.add(name)
            return
        if name in resolving:
            raise ValueError(f"Circular extend: reference involving fill {name!r}")
        resolving.add(name)

        base_name = fill.extend
        if base_name not in fill_map:
            raise ValueError(
                f"Fill {name!r} extends unknown fill {base_name!r}"
            )
        _resolve(base_name)

        base = fill_map[base_name]

        # Select per-base-bar extension contribution (lines and pattern_lines).
        def _empty() -> tuple[list, list]:
            return ([], [])

        if not fill.bars:
            extension_for_bar = [_empty() for _ in base.bars]
        elif len(fill.bars) == 1 and len(base.bars) > 1:
            broadcast = (
                list(fill.bars[0].lines),
                list(fill.bars[0].pattern_lines),
            )
            extension_for_bar = [broadcast for _ in base.bars]
        else:
            if len(fill.bars) > len(base.bars):
                raise ValueError(
                    f"Fill {name!r}: extend body has "
                    f"{len(fill.bars)} bar(s) but base fill {base_name!r} "
                    f"has only {len(base.bars)}; extension cannot lengthen "
                    "the fill"
                )
            extension_for_bar = [
                (list(fill.bars[i].lines), list(fill.bars[i].pattern_lines))
                if i < len(fill.bars)
                else _empty()
                for i in range(len(base.bars))
            ]

        merged_bars: list[FillBar] = []
        for base_bar, (extra_lines, extra_pattern_lines) in zip(
            base.bars, extension_for_bar
        ):
            merged_bars.append(
                FillBar(
                    label=base_bar.label,
                    lines=list(base_bar.lines) + extra_lines,
                    pattern_lines=list(base_bar.pattern_lines) + extra_pattern_lines,
                )
            )

        merged_spans = list(base.dynamic_spans) + list(fill.dynamic_spans)

        fill_map[name] = Fill(
            name=name,
            bars=merged_bars,
            dynamic_spans=merged_spans,
            extend=None,  # mark as resolved
        )

        resolving.discard(name)
        resolved.add(name)

    for fname in list(fill_map):
        _resolve(fname)


def _build_coverage_maps(
    section: Section,
    fill_map: dict[str, Fill],
    total_bars: int,
    bpb: int,
    beat_unit: int,
    variation_map: dict[str, VariationDef] | None = None,
) -> tuple[dict[int, tuple["IRFillBar", Fraction]], dict[int, Variation]]:
    """Build per-bar fill and variation coverage maps for a section.

    Returns ``(fill_coverage, variation_coverage)`` keyed by
    section-bar offset (0-indexed). ``total_bars`` bounds fill coverage
    so multi-bar fills that extend past the section are truncated.

    ``variation_map`` is consulted to resolve named references
    (``variation "name" at bar N`` with no body) to their action list.
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
        # Resolve name-only references ("variation \"foo\" at bar N" with no
        # body) against the shared variation_map. Inline blocks already carry
        # their own actions and are used verbatim.
        if not variation.actions and variation.name is not None:
            if variation_map is None or variation.name not in variation_map:
                raise GrooveScriptError(
                    message=(
                        f"Section {section.name!r} references unknown "
                        f"variation {variation.name!r}. Define it with "
                        f"`variation \"{variation.name}\":` at the top level, "
                        f"or use a built-in variation from the library."
                    ),
                )
            resolved = variation_map[variation.name]
            variation = Variation(
                name=variation.name,
                bars=variation.bars,
                actions=list(resolved.actions),
            )
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
        if s_bars is None:
            raise ValueError(
                f"Section {section.name!r} must define bars "
                f"(or set default_bars in metadata, or use like)"
            )
        # s_groove may remain None — this is the minimal-chart case:
        # the section renders as a placeholder groove (empty bars + label).
        if s_groove != section.groove or s_bars != section.bars:
            section = replace(section, groove=s_groove, bars=s_bars)
        patched_sections.append(section)

    sections = _resolve_inheritance(patched_sections)

    # Apply the top-level ``crash in`` directive (if any). Every section
    # after the first picks up a bar-1 crash-in by default; sections that
    # already declared their own ``crash in [at …]`` keep their explicit
    # spec, and sections marked ``no crash in`` opt out entirely.
    if song.crash_in is not None:
        promoted: list[Section] = []
        for index, section in enumerate(sections):
            if (
                index > 0
                and not section.no_crash_in
                and section.crash_in is None
            ):
                section = replace(section, crash_in=song.crash_in)
            promoted.append(section)
        sections = promoted

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
        if source.is_placeholder:
            raise ValueError(
                f"Groove {name!r} is a placeholder and has no body to compile; "
                f"this should have been routed through the placeholder path"
            )
        compiled = compile_groove(source, bpb, beat_unit)
        groove_cache[key] = compiled
        return compiled

    fill_map = {fill.name: fill for fill in song.fills}
    # Merge per-section inline fills into the shared fill map. Inline fills
    # use synthetic, unique names so there is no collision risk.
    for section in sections:
        for inline_fill in section.inline_fills:
            fill_map[inline_fill.name] = inline_fill

    # Pull any referenced fills not defined locally (and not inline) from
    # the built-in fill library. User definitions take precedence. This
    # also has to account for fills referenced only as extend bases, so
    # that an extending fill can inherit from a library fill.
    referenced_fills: set[str] = set()
    for section in sections:
        for placement in section.fills:
            referenced_fills.add(placement.fill_name)
    for fill in list(fill_map.values()):
        if fill.extend is not None:
            referenced_fills.add(fill.extend)
    from .library import get_library_fills
    library_fills = get_library_fills()
    for name in referenced_fills:
        if name not in fill_map and name in library_fills:
            fill_map[name] = library_fills[name]

    _resolve_fill_extends(fill_map)

    # Build the variation lookup map for name-only references
    # (``variation "foo" at bar N`` with no body). User-defined top-level
    # variations take precedence over built-in library entries, and any
    # referenced name not defined locally is pulled from the library.
    variation_map: dict[str, VariationDef] = {v.name: v for v in song.variations}
    referenced_variations: set[str] = set()
    for section in sections:
        for variation in section.variations:
            if not variation.actions and variation.name is not None:
                referenced_variations.add(variation.name)
    if referenced_variations:
        from .library import get_library_variations
        library_variations = get_library_variations()
        for name in referenced_variations:
            if name not in variation_map and name in library_variations:
                variation_map[name] = library_variations[name]

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
        expanded = _expand_play_block(
            section.play, _get_groove, bpb, beat_unit, section.name, groove_defs
        )
        total_bars = len(expanded)
        if total_bars == 0:
            raise ValueError(f"Section {section.name!r}: play: block expanded to zero bars")
        if section.bars is not None and section.bars != total_bars:
            raise ValueError(
                f"Section {section.name!r}: bars: {section.bars} does not match the "
                f"play: block, which expands to {total_bars} "
                f"bar{'s' if total_bars != 1 else ''}"
            )

        # Resolve labels for nameless placeholder spans. A single nameless
        # span uses ``"<Section> groove"`` (the same default as the
        # implicit minimal-chart case); two or more get numeric suffixes
        # (``"Verse groove 1"``, ``"Verse groove 2"``, …) so they can be
        # told apart on the page.
        nameless_first_offsets = [
            i for i, (_, _, _, ph, _, _, _) in enumerate(expanded)
            if ph is not None and ph[0] is None and ph[1]
        ]
        display_name = full_section_name[:1].upper() + full_section_name[1:]
        if len(nameless_first_offsets) == 1:
            nameless_label_for_offset = {nameless_first_offsets[0]: f"{display_name} groove"}
        else:
            nameless_label_for_offset = {
                offset: f"{display_name} groove {idx + 1}"
                for idx, offset in enumerate(nameless_first_offsets)
            }

        ir_section = IRSection(name=section.name, start_bar=start_bar_number, bars=total_bars, tempo=effective_tempo)
        fill_coverage, variation_coverage = _build_coverage_maps(section, fill_map, total_bars, bpb, beat_unit, variation_map)
        all_spans = _collect_section_dynamic_spans(section, None, fill_map, total_bars)
        dyn_starts, dyn_stops = _resolve_dynamic_spans(all_spans, total_bars, bpb)

        _validate_break_specs(section.breaks, section.name, total_bars)

        new_bars: list[IRBar] = []
        for section_bar_offset, (template_events, base_subdivision, is_rest, placeholder_info, phrase_position, phrase_length, base_beat_tuplets) in enumerate(expanded):
            absolute_bar = start_bar_number + section_bar_offset

            if placeholder_info is not None:
                # Placeholder bar: empty events, fixed subdivision=1, label
                # only on the first bar of the span. Variations cannot apply
                # (no notes to vary); fills and cues may overlay normally.
                if section_bar_offset in variation_coverage:
                    raise ValueError(
                        f"Section {section.name!r}: variation at bar "
                        f"{section_bar_offset + 1} targets a placeholder "
                        f"groove (no notes to vary)"
                    )
                placeholders: list[tuple[Fraction, str]] = []
                label, is_first = placeholder_info
                if is_first:
                    if label is None:
                        label = nameless_label_for_offset[section_bar_offset]
                    placeholders.append((Fraction(0), label))
                user_placeholders = _collect_bar_placeholders(
                    section, section_bar_offset, 1, bpb
                )
                placeholders.extend(user_placeholders)
                bar_cues = _collect_bar_cues(section, section_bar_offset, 1, bpb)
                new_bars.append(
                    IRBar(
                        number=absolute_bar,
                        subdivision=1,
                        events=[],
                        section_name=full_section_name if section_bar_offset == 0 else None,
                        section_bars=total_bars if section_bar_offset == 0 else None,
                        cues=bar_cues,
                        fill_placeholders=placeholders,
                        tempo=effective_tempo,
                        time_signature=effective_ts,
                        is_placeholder_groove=True,
                        dynamic_starts=dyn_starts.get(section_bar_offset, []),
                        dynamic_stops=dyn_stops.get(section_bar_offset, []),
                    )
                )
                continue

            # Re-stamp bar numbers on the template events for this absolute bar
            arranged_events = [
                Event(
                    bar=absolute_bar,
                    beat_position=event.beat_position,
                    instrument=event.instrument,
                    modifiers=list(event.modifiers),
                    duration=event.duration,
                    buzz_duration=event.buzz_duration,
                    grace_instrument=event.grace_instrument,
                    source_line=event.source_line,
                )
                for event in template_events
            ]
            bar_subdivision = base_subdivision
            bar_beat_tuplets: list[object] = list(base_beat_tuplets)

            if section_bar_offset in fill_coverage:
                fill_bar, start_pos = fill_coverage[section_bar_offset]
                _validate_fill_not_inside_tuplet(
                    bar_beat_tuplets, start_pos, bpb,
                    f"section {section.name!r} bar {section_bar_offset + 1}",
                )
                arranged_events = _apply_fill_overlay(arranged_events, fill_bar, start_pos, absolute_bar)
                bar_subdivision = max(bar_subdivision, fill_bar.subdivision)
                bar_beat_tuplets = _merge_fill_beat_tuplets(
                    bar_beat_tuplets, fill_bar.beat_tuplets, start_pos, bpb
                )
                is_rest = False  # fill replaces a rest bar entirely

            if section_bar_offset in variation_coverage:
                variation = variation_coverage[section_bar_offset]
                var_subdivision = _infer_variation_subdivision(variation.actions, bpb)
                bar_subdivision = max(bar_subdivision, var_subdivision)
                arranged_events = _apply_variation_actions(
                    arranged_events, variation.actions, bar_subdivision, absolute_bar, bpb, beat_unit
                )

            if (
                section.crash_in is not None
                and not section.no_crash_in
                and section.crash_in.applies_at(section_bar_offset)
            ):
                arranged_events = _apply_crash_in(arranged_events, absolute_bar)
                is_rest = False

            for break_spec in section.breaks:
                arranged_events = _apply_break(arranged_events, break_spec, section_bar_offset, bpb, total_bars)

            bar_cues = _collect_bar_cues(section, section_bar_offset, bar_subdivision, bpb)
            bar_placeholders = _collect_bar_placeholders(section, section_bar_offset, bar_subdivision, bpb)

            # Post-arrangement buzz validation: buzz may have arrived via
            # a fill overlay or variation add/replace; re-check overlap
            # against the final event list for this bar.
            context = f"section {section.name!r} bar {section_bar_offset + 1}"
            for event in arranged_events:
                _validate_buzz_event(event, bpb, context)
            _validate_buzz_overlap(arranged_events, context)
            _validate_grace_uniqueness(arranged_events, context)
            _validate_instrument_mutex(arranged_events, context)
            _validate_tuplet_grid_alignment(arranged_events, bar_beat_tuplets, bpb, context)

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
                    phrase_position=phrase_position,
                    phrase_length=phrase_length,
                    beat_tuplets=bar_beat_tuplets,
                )
            )
        return new_bars, ir_section

    def _process_placeholder_section(
        section, effective_ts, effective_tempo, full_section_name, start_bar_number,
        placeholder_label: str | None = None,
    ) -> tuple[list[IRBar], IRSection]:
        """Build IR for a section whose groove is a placeholder (TBD).

        Each bar is rendered as an invisible skip with no notes or rests.
        A boxed label sits above the first bar so the reader can tell the
        groove is intentionally left unspecified.

        ``placeholder_label`` overrides the default ``"<Section> groove"``
        derivation. Used when the section explicitly references a named
        placeholder (top-level ``groove placeholder "verse-A"`` or inline
        ``groove: placeholder "intro feel"``).
        """
        if section.variations:
            raise ValueError(
                f"Section {section.name!r}: variations cannot be applied to a "
                f"placeholder groove (no notes to vary)"
            )
        total_bars = section.bars
        ir_section = IRSection(
            name=section.name,
            start_bar=start_bar_number,
            bars=total_bars,
            tempo=effective_tempo,
        )
        bpb_local = _beats_per_bar(effective_ts)
        if placeholder_label is not None:
            section_label = placeholder_label
        else:
            display_name = full_section_name[:1].upper() + full_section_name[1:]
            section_label = f"{display_name} groove"
        new_bars: list[IRBar] = []
        for section_bar_offset in range(total_bars):
            absolute_bar = start_bar_number + section_bar_offset
            placeholders: list[tuple[Fraction, str]] = []
            if section_bar_offset == 0:
                placeholders.append((Fraction(0), section_label))
            user_placeholders = _collect_bar_placeholders(
                section, section_bar_offset, 1, bpb_local
            )
            placeholders.extend(user_placeholders)
            bar_cues = _collect_bar_cues(section, section_bar_offset, 1, bpb_local)
            new_bars.append(
                IRBar(
                    number=absolute_bar,
                    subdivision=1,
                    events=[],
                    section_name=full_section_name if section_bar_offset == 0 else None,
                    section_bars=total_bars if section_bar_offset == 0 else None,
                    cues=bar_cues,
                    fill_placeholders=placeholders,
                    tempo=effective_tempo,
                    time_signature=effective_ts,
                    is_placeholder_groove=True,
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
        if repeat_times is not None:
            if repeat_times < 1:
                raise GrooveScriptError(
                    message=(
                        f"Section {section.name!r}: repeat must be at least 1, "
                        f"got {repeat_times}"
                    ),
                )
            if repeat_times > section.bars:
                raise GrooveScriptError(
                    message=(
                        f"Section {section.name!r}: repeat ({repeat_times}) "
                        f"cannot exceed the section's bar count ({section.bars}) "
                        f"— the phrase would be shorter than one bar"
                    ),
                )
            if section.bars % repeat_times != 0:
                raise GrooveScriptError(
                    message=(
                        f"Section {section.name!r}: bars ({section.bars}) is "
                        f"not divisible by repeat ({repeat_times}); the section "
                        f"must contain a whole number of identical phrases"
                    ),
                )
        phrase_length = (section.bars // repeat_times) if repeat_times else None

        fill_coverage, variation_coverage = _build_coverage_maps(section, fill_map, section.bars, bpb, beat_unit, variation_map)

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

        _validate_break_specs(section.breaks, section.name, section.bars)

        new_bars: list[IRBar] = []
        for section_bar_offset in range(section.bars):
            absolute_bar = start_bar_number + section_bar_offset
            groove_bar_number = (section_bar_offset % groove.bars) + 1
            template_events = groove_events_by_bar[groove_bar_number]
            groove_bar_subdivision = groove.bar_subdivisions[groove_bar_number - 1]
            groove_bar_tuplets: list[object] = (
                groove.bar_beat_tuplets[groove_bar_number - 1]
                if groove_bar_number - 1 < len(groove.bar_beat_tuplets)
                else []
            )
            arranged_events = [
                Event(
                    bar=absolute_bar,
                    beat_position=event.beat_position,
                    instrument=event.instrument,
                    modifiers=list(event.modifiers),
                    duration=event.duration,
                    buzz_duration=event.buzz_duration,
                    grace_instrument=event.grace_instrument,
                    source_line=event.source_line,
                )
                for event in template_events
            ]

            if section_bar_offset in fill_coverage:
                fill_bar, start_pos = fill_coverage[section_bar_offset]
                _validate_fill_not_inside_tuplet(
                    groove_bar_tuplets, start_pos, bpb,
                    f"section {section.name!r} bar {section_bar_offset + 1}",
                )
                arranged_events = _apply_fill_overlay(arranged_events, fill_bar, start_pos, absolute_bar)
                bar_subdivision = max(groove_bar_subdivision, fill_bar.subdivision)
                # Merge fill tuplet annotations: a fill placed at beat N onward
                # replaces the groove's annotation for those beats.
                groove_bar_tuplets = _merge_fill_beat_tuplets(
                    groove_bar_tuplets, fill_bar.beat_tuplets, start_pos, bpb
                )
            else:
                bar_subdivision = groove_bar_subdivision

            if section_bar_offset in variation_coverage:
                variation = variation_coverage[section_bar_offset]
                var_subdivision = _infer_variation_subdivision(variation.actions, bpb)
                bar_subdivision = max(bar_subdivision, var_subdivision)
                arranged_events = _apply_variation_actions(
                    arranged_events, variation.actions, bar_subdivision, absolute_bar, bpb, beat_unit
                )

            if (
                section.crash_in is not None
                and not section.no_crash_in
                and section.crash_in.applies_at(section_bar_offset)
            ):
                arranged_events = _apply_crash_in(arranged_events, absolute_bar)

            for break_spec in section.breaks:
                arranged_events = _apply_break(arranged_events, break_spec, section_bar_offset, bpb, section.bars)

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
            _validate_grace_uniqueness(arranged_events, context)
            _validate_instrument_mutex(arranged_events, context)
            _validate_tuplet_grid_alignment(arranged_events, groove_bar_tuplets, bpb, context)

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
                    phrase_position=groove_bar_number,
                    phrase_length=groove.bars,
                    beat_tuplets=list(groove_bar_tuplets),
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
        elif section.groove is None:
            new_bars, ir_section = _process_placeholder_section(
                section, effective_ts, effective_tempo, full_section_name, current_bar_number
            )
        elif (resolved_groove := groove_defs.get(section.groove)) is not None and resolved_groove.is_placeholder:
            new_bars, ir_section = _process_placeholder_section(
                section, effective_ts, effective_tempo, full_section_name, current_bar_number,
                placeholder_label=resolved_groove.placeholder_label,
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
                raise GrooveScriptError(
                    message=(
                        f"buzz roll in bar {bar.number} ties past the end of the "
                        f"song (need {remainder} more of a bar)"
                    ),
                    line=event.source_line,
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
    groove_defs: dict[str, "Groove"] | None = None,
) -> list[tuple[list[Event], int, bool, tuple[str | None, bool] | None, int | None, int | None, list[object]]]:
    """Expand a play: block into a flat list of per-bar tuples.

    Each entry is ``(events, subdivision, is_rest, placeholder_info,
    phrase_position, phrase_length, beat_tuplets)`` where
    ``placeholder_info`` is ``None`` for regular bars or a
    ``(label_or_None, is_first_bar_of_span)`` tuple for placeholder-groove
    bars (label resolution for nameless placeholders is deferred to
    :func:`_process_play_section` because numbering depends on how many
    nameless spans the section ends up with). ``beat_tuplets`` is the
    bar's per-beat tuplet annotation list (empty when the bar carries no
    tuplet content).

    ``phrase_position`` / ``phrase_length`` carry the source groove's
    natural phrase metadata so the lilypond emitter can group multi-bar
    repeats; they are ``None`` for placeholder, rest, and inline-bar bars
    (no natural phrase to align to).

    Events are bar=1-relative (caller re-stamps to absolute bar numbers).
    ``subdivision`` is the grid for that bar; for placeholder bars it is
    fixed at 1 (matches ``_process_placeholder_section``).
    ``is_rest`` is True for whole-bar rest bars.

    ``get_groove`` is a callable ``(name, bpb, beat_unit) -> IRGroove`` so
    the caller controls how grooves are compiled/cached (needed because
    per-section time signature overrides recompile grooves at a different
    bpb/beat_unit). ``groove_defs`` is an optional name-to-Groove map used
    to detect placeholder grooves before compilation; an undefined name
    here auto-promotes to a named placeholder so users can reference
    grooves they haven't transcribed yet.
    """
    result: list[tuple[list[Event], int, bool, tuple[str | None, bool] | None, int | None, int | None, list[object]]] = []
    # name → (events, subdivision, beat_tuplets)
    named_bars: dict[str, tuple[list[Event], int, list[object]]] = {}
    last_groove_subdivision: int | None = None
    groove_defs = groove_defs or {}

    def _emit_placeholder_span(label: str | None, repeat: int) -> None:
        # A placeholder span is one contiguous block of ``repeat`` bars; the
        # label is attached to the first bar only. Subsequent bars carry the
        # same label tuple but with ``is_first=False`` so the renderer knows
        # not to re-emit the rehearsal markup.
        for i in range(repeat):
            result.append(([], 1, False, (label, i == 0), None, None, []))

    for item in play_items:
        if isinstance(item, PlayGroove):
            source = groove_defs.get(item.groove_name)
            if source is not None and source.is_placeholder:
                _emit_placeholder_span(source.placeholder_label, item.repeat)
                continue
            if source is None:
                # Auto-promote: an undefined groove reference inside play:
                # becomes a named placeholder using the reference name as
                # its label. Lets users sketch a chart by listing groove
                # names before transcribing them.
                _emit_placeholder_span(item.groove_name, item.repeat)
                continue
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
                    bar_tuplets = (
                        groove.bar_beat_tuplets[bar_num - 1]
                        if bar_num - 1 < len(groove.bar_beat_tuplets)
                        else []
                    )
                    result.append(
                        (groove_events_by_bar[bar_num], bar_sub, False, None, bar_num, groove.bars, list(bar_tuplets))
                    )

        elif isinstance(item, PlayBar):
            if item.pattern is not None:
                # Inline definition
                if item.name in named_bars:
                    raise ValueError(
                        f"play: duplicate bar name {item.name!r} in section"
                    )
                events, subdiv, bar_tuplets = _compile_play_bar_events(
                    item.pattern,
                    bpb,
                    beat_unit,
                    f"section {section_name!r} play bar {item.name!r}",
                )
                named_bars[item.name] = (events, subdiv, bar_tuplets)
            else:
                # Reference — must already be defined
                if item.name not in named_bars:
                    raise ValueError(
                        f"play: bar {item.name!r} referenced before it was defined"
                    )
                events, subdiv, bar_tuplets = named_bars[item.name]

            for _ in range(item.repeat):
                result.append((events, subdiv, False, None, None, None, list(bar_tuplets)))

        elif isinstance(item, PlayRest):
            subdiv = last_groove_subdivision if last_groove_subdivision is not None else _whole_bar_rest_subdivision(bpb)
            for _ in range(item.repeat):
                result.append(([], subdiv, True, None, None, None, []))

    return result
