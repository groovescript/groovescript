from dataclasses import dataclass, field


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
    """

    modifiers: list[str]
    buzz_duration: str | None

    def __new__(
        cls,
        label: str,
        modifiers: list[str] | None = None,
        buzz_duration: str | None = None,
    ):
        instance = super().__new__(cls, label)
        instance.modifiers = modifiers if modifiers is not None else []
        instance.buzz_duration = buzz_duration
        return instance

    @property
    def label(self) -> str:
        return str(self)


class InstrumentHit(str):
    """An instrument name with optional modifiers.

    Inherits from str for the same backward-compat reason as ``BeatHit``.
    """

    modifiers: list[str]
    buzz_duration: str | None

    def __new__(
        cls,
        instrument: str,
        modifiers: list[str] | None = None,
        buzz_duration: str | None = None,
    ):
        instance = super().__new__(cls, instrument)
        instance.modifiers = modifiers if modifiers is not None else []
        instance.buzz_duration = buzz_duration
        return instance

    @property
    def instrument(self) -> str:
        return str(self)


@dataclass(frozen=True)
class StarSpec:
    """A ``*N`` / ``*Nt`` pattern-line value.

    ``note_value`` is the denominator of the note value (2, 4, 8, or 16),
    meaning "every 1/note_value note". ``triplet`` is ``True`` for the
    triplet variant (``*8t`` = 8th-note triplets, ``*4t`` = quarter-note
    triplets, etc.).

    ``except_beats`` is an optional tuple of beat labels to exclude from the
    expanded star pattern (e.g. ``*16 except 2a, 4a``).
    """

    note_value: int
    triplet: bool = False
    except_beats: tuple[str, ...] = ()

    def __str__(self) -> str:
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

    @property
    def pattern(self) -> list[PatternLine]:
        """Compatibility accessor for single-bar grooves."""
        return self.bars[0]


@dataclass
class FillLine:
    """One beat position in a fill with one or more simultaneous instruments."""

    beat: str  # beat label like "3", "3e", "3&", "3a"
    instruments: list[str]  # simultaneous hits e.g. ["BD", "CR"]


@dataclass
class FillBar:
    """One bar of fill events, from a 'count' block."""

    label: str  # human-readable count label e.g. "3 e & a 4"
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
    # 1-indexed source line where this action appeared, for diagnostics.
    line: int | None = None


@dataclass
class Variation:
    """An inline variation block applied to one or more bars within a section."""

    name: str | None  # optional human-readable label for the variation
    bars: list[int]  # 1-indexed within the section (was singular ``bar``)
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
    """One or more bars of silence inside a play: block."""

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
    crash_in: bool = False  # replace first riding hit of bar 1 with a crash


@dataclass
class Song:
    """Top-level GrooveScript document."""

    metadata: Metadata = field(default_factory=Metadata)
    grooves: list[Groove] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
