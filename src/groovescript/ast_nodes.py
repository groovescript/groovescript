from dataclasses import dataclass, field
from fractions import Fraction


# Categories that may be listed after ``like "x" with …`` to opt a child
# section into inheriting parent data beyond the "structure only" default.
INHERIT_CATEGORIES: frozenset[str] = frozenset({"fills", "variations", "cues"})


@dataclass(frozen=True)
class InheritSpec:
    """Parsed form of ``like "parent" [with …]`` on a section."""

    parent: str
    categories: frozenset[str] = field(default_factory=frozenset)

    def inherits(self, category: str) -> bool:
        return category in self.categories


class BeatHit(str):
    """A beat label with optional modifiers (flam, drag, ghost, accent).

    Inherits from str so that existing code comparing beats to plain strings
    (e.g. ``beats == ["1", "3"]``) continues to work.

    ``grace_instrument`` is set when the modifier list contains a parameterised
    flam/drag (e.g. ``flam:SN`` on a hi-tom hit means the grace stroke plays
    on snare). ``None`` means same-instrument flam/drag — the grace plays on
    the carrying instrument.
    """

    modifiers: list[str]
    buzz_duration: str | None
    grace_instrument: str | None

    def __new__(
        cls,
        label: str,
        modifiers: list[str] | None = None,
        buzz_duration: str | None = None,
        grace_instrument: str | None = None,
    ):
        instance = super().__new__(cls, label)
        instance.modifiers = modifiers if modifiers is not None else []
        instance.buzz_duration = buzz_duration
        instance.grace_instrument = grace_instrument
        return instance

    @property
    def label(self) -> str:
        return str(self)


@dataclass
class TupletSlot:
    """One hit slot inside a :class:`TupletGroup`.

    ``index`` is 1-indexed (1..N for an N-tuplet). ``modifiers`` and the
    grace/buzz fields mirror the per-hit decorations used elsewhere in the
    AST so existing modifier semantics (accent, ghost, flam, drag, …) apply
    uniformly inside tuplet groups.
    """

    index: int
    modifiers: list[str] = field(default_factory=list)
    buzz_duration: str | None = None
    grace_instrument: str | None = None


# Maps a tuplet-kind keyword to its (actual, normal) ratio. ``actual`` is
# the count of slots; ``normal`` is the duration unit those slots replace.
# 7:4 chosen for septuplet (jazz/prog drum convention).
_TUPLET_RATIOS: dict[str, tuple[int, int]] = {
    "triplet": (3, 2),
    "quintuplet": (5, 4),
    "sextuplet": (6, 4),
    "septuplet": (7, 4),
    "nonuplet": (9, 8),
}


@dataclass
class TupletGroup:
    """A tuplet group inside a pattern line.

    ``anchor`` is a normalised beat label (``"2"``, ``"2&"``, …) marking
    where the group starts. ``span`` is in beats: ``Fraction(1)`` for the
    default whole-beat span, ``Fraction(1, 2)`` when the kind was qualified
    with ``/8`` (half-beat span). ``ratio`` is the (actual, normal) tuplet
    ratio resolved from ``kind``.
    """

    kind: str
    ratio: tuple[int, int]
    span: Fraction
    anchor: str
    slots: list[TupletSlot] = field(default_factory=list)
    line: int | None = None


class InstrumentHit(str):
    """An instrument name with optional modifiers.

    Inherits from str for the same backward-compat reason as ``BeatHit``.

    ``grace_instrument`` carries the optional ``flam:<inst>`` / ``drag:<inst>``
    target — see :class:`BeatHit` for the semantics.
    """

    modifiers: list[str]
    buzz_duration: str | None
    grace_instrument: str | None

    def __new__(
        cls,
        instrument: str,
        modifiers: list[str] | None = None,
        buzz_duration: str | None = None,
        grace_instrument: str | None = None,
    ):
        instance = super().__new__(cls, instrument)
        instance.modifiers = modifiers if modifiers is not None else []
        instance.buzz_duration = buzz_duration
        instance.grace_instrument = grace_instrument
        return instance

    @property
    def instrument(self) -> str:
        return str(self)


@dataclass(frozen=True)
class CrashInSpec:
    """Where ``crash in`` applies within a section.

    Three shapes:
      * bare (``crash in``) — bar 1 only; ``bars`` empty, ``every`` is None.
      * explicit list (``crash in at 1, 9, 17``) — ``bars`` carries the
        1-indexed bar numbers; ``every`` is None.
      * star (``crash in at *N``) — ``every`` is N; ``bars`` empty. Crash-in
        applies at bar 1 and every N bars after (1, 1+N, 1+2N, ...).
    """

    bars: tuple[int, ...] = ()
    every: int | None = None

    def applies_at(self, section_bar_offset: int) -> bool:
        if self.every is not None:
            return section_bar_offset % self.every == 0
        if self.bars:
            return (section_bar_offset + 1) in self.bars
        return section_bar_offset == 0


@dataclass(frozen=True)
class StarSpec:
    """A ``*N`` / ``*Nt`` / ``*<kind>`` pattern-line value.

    Two shapes:

    * **Note-value form**: ``note_value`` is the denominator of the note
      value (2, 4, 8, or 16) and ``triplet`` flips the 3:2 variant —
      ``*8t`` means 8th-note triplets across the bar.
    * **Named-tuplet form**: ``tuplet_kind`` names one of
      ``triplet``/``quintuplet``/``sextuplet``/``septuplet``/``nonuplet``,
      meaning "fill the bar with one tuplet of that kind per beat".
      ``tuplet_span`` is in beats (``Fraction(1)`` default, ``Fraction(1, 2)``
      for ``/8`` half-beat granularity). When ``tuplet_kind`` is set,
      ``note_value`` and ``triplet`` are unused.

    ``except_beats`` excludes specific beat labels from the expanded pattern.
    """

    note_value: int = 0
    triplet: bool = False
    except_beats: tuple[str, ...] = ()
    tuplet_kind: str | None = None
    tuplet_span: Fraction = Fraction(1)

    def __str__(self) -> str:
        if self.tuplet_kind is not None:
            base = f"*{self.tuplet_kind}"
            if self.tuplet_span == Fraction(1, 2):
                base = f"{base}/8"
            elif self.tuplet_span == Fraction(1, 4):
                base = f"{base}/16"
        else:
            base = f"*{self.note_value}{'t' if self.triplet else ''}"
        if self.except_beats:
            return f"{base} except {', '.join(self.except_beats)}"
        return base


@dataclass
class PatternLine:
    """A single instrument line in a groove pattern."""

    instrument: str  # BD, SN, SCS, HH, OH, RD, CR, FT, HT, MT, HF
    # Either a list of BeatHit/str entries (e.g. ``["1", "2&", "3e"]``) or a
    # ``StarSpec`` describing a ``*N``/``*Nt`` auto-fill.
    beats: list[str] | StarSpec
    # 1-indexed source line where this pattern line appeared, for diagnostics.
    line: int | None = None


@dataclass
class Metadata:
    """Song-level metadata."""

    title: str | None = None
    tempo: int | None = None
    time_signature: str = "4/4"
    dsl_version: int | None = None
    default_groove: str | None = None
    default_bars: int | None = None


@dataclass
class Groove:
    """A named groove definition."""

    name: str
    bars: list[list[PatternLine]]
    bar_texts: dict[int, str] = field(default_factory=dict)  # 1-indexed bar -> text annotation
    # Count+notes form — alternative to explicit pattern lines. When present,
    # ``bars`` is empty at parse time; the compiler expands ``count_notes``
    # into a single bar of PatternLines and infers the subdivision from the
    # beat labels in the count string.
    count_notes: tuple[str, str] | None = None
    # Groove extension: name of the base groove to inherit from. The
    # extending groove starts with a copy of the base groove's pattern
    # lines; new instruments are added and same-instrument lines override.
    extend: str | None = None
    # Dynamic spans declared inside the groove. Bar numbers are 1-indexed
    # within the groove; the compiler translates them to section-bar
    # offsets and repeats them per groove cycle.
    dynamic_spans: list["DynamicSpan"] = field(default_factory=list)
    # Variation actions applied to a groove defined via ``extend:``. Each
    # entry targets a set of 1-indexed bars (``None`` = every bar) and
    # carries an ordered list of variation actions to apply to those bars
    # once the base groove's events have been expanded.
    extend_variations: list["GrooveExtendVariation"] = field(default_factory=list)
    # Placeholder grooves are TBD slots that render as empty bars with a
    # boxed label. ``bars`` is empty and the other content fields are
    # ignored. ``placeholder_label`` carries the user-facing label: the
    # original quoted name for named placeholders, or ``None`` for the
    # nameless variant (the compiler picks a label from the section name).
    is_placeholder: bool = False
    placeholder_label: str | None = None

    @property
    def pattern(self) -> list[PatternLine]:
        """Compatibility accessor for single-bar grooves."""
        return self.bars[0]


@dataclass
class GrooveExtendVariation:
    """A scoped bundle of variation actions declared inside ``extend:``.

    ``bars`` is ``None`` to apply to every bar of the base groove, or a
    1-indexed list of bar numbers to target only those bars.
    """

    bars: list[int] | None
    actions: list["VariationAction"]


@dataclass
class FillLine:
    """One beat position in a fill with one or more simultaneous instruments."""

    beat: str  # beat label like "3", "3e", "3&", "3a"
    instruments: list[str]  # simultaneous hits e.g. ["BD", "CR"]


@dataclass
class FillBar:
    """One bar of fill events, from a 'count' block."""

    label: str | None  # human-readable count label e.g. "3 e & a 4"; None when omitted
    lines: list[FillLine]
    pattern_lines: list[PatternLine] = field(default_factory=list)  # star-spec instrument lines (e.g. BD: *8 except 4&)


@dataclass
class Fill:
    """A named fill definition composed of one or more bar blocks."""

    name: str
    bars: list[FillBar]
    # Dynamic spans declared inside the fill. Bar numbers are 1-indexed
    # within the fill; the compiler translates them to section-bar
    # offsets at placement time.
    dynamic_spans: list["DynamicSpan"] = field(default_factory=list)
    # Fill extension: name of the base fill to inherit from. The extending
    # fill starts with a copy of the base fill's bars; the extension's
    # pattern lines are appended (purely additive layering). Only the
    # instrument->positions syntax is accepted in extension bodies.
    extend: str | None = None


@dataclass
class FillPlacement:
    """A fill placed at a specific bar (and optional beat) within a section."""

    fill_name: str
    bar: int  # 1-indexed within the section
    beat: str | None = None  # if None, replaces whole bar; else starts at this beat


@dataclass
class FillPlaceholder:
    """A placeholder annotation placed at a specific bar within a section.

    The groove underneath renders normally; only a text label (e.g. "fill")
    is added above the staff to indicate that a fill is intended.
    """

    label: str  # displayed above the bar; defaults to "fill"
    bar: int    # 1-indexed within the section
    beat: str | None = None  # if None, placed at bar start; else at this beat label


@dataclass
class VariationAction:
    """A single add/remove/replace/substitute/modify action within a variation block."""

    action: str  # "add", "remove", "replace", "substitute", "modify_add", or "modify_remove"
    instrument: str = ""  # instrument to add/remove/replace/modify (unused for "substitute")
    beats: str | list[str] = field(default_factory=list)  # "*" or list of beat labels
    target_instrument: str | None = None  # for "replace": the replacement instrument
    modifiers: list[str] = field(default_factory=list)  # "ghost", "accent"
    # For "substitute": a (count_str, notes_str) pair that replaces every
    # event in the targeted bar with the events expanded from the count+notes
    # body. Mutually exclusive with instrument/beats/target_instrument.
    count_notes: tuple[str, str] | None = None
    # Buzz-roll duration (e.g. "4", "2d") when modifiers contains "buzz".
    buzz_duration: str | None = None
    # Grace-stroke instrument when modifiers contains "flam" or "drag" with a
    # parameterised form (``flam:SN`` etc.). ``None`` means same-instrument
    # flam/drag — the grace plays on the action's main instrument.
    grace_instrument: str | None = None
    # 1-indexed source line where this action appeared, for diagnostics.
    line: int | None = None


@dataclass
class Variation:
    """An inline variation block applied to one or more bars within a section.

    When ``actions`` is empty and ``name`` is set, this is a reference to a
    reusable variation (top-level ``variation "name":`` definition, or
    built-in variation library entry) that the compiler resolves by name.
    """

    name: str | None  # optional human-readable label for the variation
    bars: list[int]  # 1-indexed within the section (was singular ``bar``)
    actions: list[VariationAction]


@dataclass
class VariationDef:
    """A top-level reusable variation definition.

    A ``VariationDef`` captures a named bundle of variation actions that can
    be applied to any bar in any section via ``variation "name" at bar N``
    (no trailing body). Parallel to :class:`Groove` and :class:`Fill` as a
    reusable, library-friendly artefact.
    """

    name: str
    actions: list[VariationAction]


@dataclass
class Cue:
    """A text cue placed at a specific bar (and optional beat) within a section."""

    text: str
    bar: int  # 1-indexed within the section
    beat: str | None = None  # if None, placed at bar start; else at this beat label


@dataclass
class DynamicSpan:
    """A crescendo or decrescendo hairpin spanning a range of bars/beats."""

    kind: str  # "cresc" or "decresc"
    from_bar: int  # 1-indexed within the section
    to_bar: int  # 1-indexed within the section
    from_beat: str | None = None  # if None, starts at beginning of bar
    to_beat: str | None = None  # if None, ends at end of bar
    # 1-indexed source line where this span was declared, for diagnostics.
    line: int | None = None


@dataclass(frozen=True)
class BreakSpec:
    """A break directive that silences a range of beats/bars within a section.

    All bar numbers are 1-indexed within the section. When ``end_bar`` is
    ``None`` it defaults to ``start_bar`` (single-bar break). When a beat is
    ``None`` the bound is open: ``start_beat=None`` means start-of-bar;
    ``end_beat=None`` means end-of-bar.

    Events whose beat_position is within [start_frac, end_frac] (both
    endpoints inclusive) are removed. For bars that lie strictly between
    start_bar and end_bar the entire bar is silenced.
    """

    start_bar: int  # 1-indexed within section
    start_beat: str | None = None  # None = start of bar
    end_bar: int | None = None  # None = same as start_bar
    end_beat: str | None = None  # None = end of bar
    # True when the ``until`` keyword was used: the end boundary is exclusive.
    # For an end beat this means beat_position < end_frac (not <=).
    # For an end bar with no beat this means bar N is the first bar NOT silenced.
    end_exclusive: bool = False

    def effective_end_bar(self, total_bars: int) -> int:
        """Return the last bar covered by this break (1-indexed).

        When ``end_bar`` is ``None`` (no ``through`` clause) the break runs to
        the end of the section, so ``total_bars`` is returned.
        """
        return self.end_bar if self.end_bar is not None else total_bars
@dataclass
class PlayGroove:
    """A groove reference inside a play: block."""

    groove_name: str
    repeat: int = 1


@dataclass
class PlayBar:
    """An inline one-off bar (or reference to one) inside a play: block."""

    name: str  # per-section identifier
    pattern: list[PatternLine] | None  # None => reference to a previously-defined bar
    repeat: int = 1


@dataclass
class PlayRest:
    """One or more bars of silence inside a play: block.

    A single rest bar renders as a whole-bar rest (``R1`` in 4/4); two
    or more consecutive rest bars collapse visually into a single
    multi-bar rest measure with the count displayed above the staff
    (the conventional "tacet N bars" notation). Playback in MIDI and
    MusicXML always emits ``repeat`` bars of silence regardless of the
    visual collapse."""

    repeat: int = 1


PlayItem = PlayGroove | PlayBar | PlayRest


@dataclass
class Section:
    """A song section that references a groove."""

    name: str
    bars: int | None  # None when using like: or play:
    groove: str | None  # None when using like: or play:
    repeat: int | None = None  # Number of times to repeat the phrase (phrase length = groove length)
    fills: list[FillPlacement] = field(default_factory=list)
    fill_placeholders: list[FillPlaceholder] = field(default_factory=list)
    inline_fills: list[Fill] = field(default_factory=list)  # one-off fills defined inside the section
    inline_grooves: list[Groove] = field(default_factory=list)  # one-off unnamed grooves defined inside the section
    variations: list[Variation] = field(default_factory=list)
    # Inheritance spec: ``like "parent"`` (structure only), or
    # ``like "parent" with fills, variations, cues`` (opt-in categories).
    inherit: InheritSpec | None = None
    cues: list[Cue] = field(default_factory=list)
    dynamic_spans: list[DynamicSpan] = field(default_factory=list)
    tempo: int | None = None  # per-section tempo override
    time_signature: str | None = None  # per-section time signature override
    play: list[PlayItem] | None = None  # mutually exclusive with bars/groove/repeat
    # Section-scoped ``crash in`` directive. ``None`` means "not declared on
    # this section"; the compiler may still apply a crash-in if a top-level
    # ``crash in`` directive is in effect (subject to ``no_crash_in``).
    crash_in: CrashInSpec | None = None
    # Set by the section-scoped ``no crash in`` opt-out — disables both any
    # inherited crash-in and any top-level crash-in for this section.
    no_crash_in: bool = False
    breaks: list["BreakSpec"] = field(default_factory=list)


@dataclass
class Song:
    """Top-level GrooveScript document."""

    metadata: Metadata = field(default_factory=Metadata)
    grooves: list[Groove] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    variations: list[VariationDef] = field(default_factory=list)
    # Top-level ``crash in`` directive. When set, every section after the
    # first gets a bar-1 crash-in by default; sections opt out with
    # ``no crash in`` and override the bars with their own ``crash in [at …]``.
    crash_in: CrashInSpec | None = None
