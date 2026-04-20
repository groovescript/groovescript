"""Lark ``Transformer`` that turns a parse tree into the GrooveScript AST.

The ``_parser`` module-level Lark instance is built from ``grammar.lark`` at
import time. ``_GrooveScriptTransformer`` walks the resulting parse tree
and constructs :class:`Song` plus its child AST nodes.
"""

import ast as _ast
import re
from pathlib import Path

from lark import Lark, Transformer, v_args

from .ast_nodes import (
    INHERIT_CATEGORIES,
    BeatHit,
    Cue,
    DynamicSpan,
    Fill,
    FillBar,
    FillLine,
    FillPlaceholder,
    FillPlacement,
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
    VariationDef,
)
from .parser_notation import (
    _extract_buzz_duration,
    _format_count_notes_mismatch,
    _normalize_beat_label,
    _normalize_instrument,
    _parse_count_tokens,
    _parse_notes_tokens,
)

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"


def _meta_line(meta) -> int | None:
    """Extract the 1-indexed source line from a Lark tree's propagated meta.

    Returns ``None`` when the tree is empty (no tokens) so callers can treat
    missing location info uniformly.
    """
    if getattr(meta, "empty", False):
        return None
    return getattr(meta, "line", None)


def _build_fill_bar(label: str | None, items) -> "FillBar":
    """Assemble a FillBar from fill_count_item results, resolving bare ``trip``/
    ``let``/``and`` beat labels against the most recently seen numeric beat."""
    lines: list = []
    pattern_lines: list = []
    current_beat = "1"

    def _resolve(beat: str) -> str:
        nonlocal current_beat
        if beat == "trip":
            return current_beat + "t"
        if beat == "let":
            return current_beat + "l"
        if beat == "and":
            return current_beat + "&"
        if beat and beat[0].isdigit():
            m = re.match(r"\d+", beat)
            if m:
                current_beat = m.group(0)
        return beat

    for item in items:
        if isinstance(item, FillLine):
            item.beat = _resolve(item.beat)
            lines.append(item)
        elif isinstance(item, PatternLine):
            pattern_lines.append(item)
        elif isinstance(item, list):
            for line in item:
                line.beat = _resolve(line.beat)
            lines.extend(item)
    return FillBar(label=label, lines=lines, pattern_lines=pattern_lines)


class _GrooveScriptTransformer(Transformer):
    def __init__(self):
        super().__init__()
        self._inline_fill_counter = 0
        self._inline_groove_counter = 0

    def start(self, items):
        metadata = Metadata()
        grooves: list[Groove] = []
        fills: list[Fill] = []
        sections: list[Section] = []
        variations: list[VariationDef] = []

        for item in items:
            if isinstance(item, Metadata):
                self._merge_metadata(metadata, item)
            elif isinstance(item, Groove):
                grooves.append(item)
            elif isinstance(item, Fill):
                fills.append(item)
            elif isinstance(item, Section):
                sections.append(item)
            elif isinstance(item, VariationDef):
                variations.append(item)

        return Song(
            metadata=metadata,
            grooves=grooves,
            fills=fills,
            sections=sections,
            variations=variations,
        )

    def statement(self, items):
        return items[0]

    def metadata_block(self, items):
        metadata = Metadata()
        for item in items:
            self._merge_metadata(metadata, item)
        return metadata

    def metadata_line(self, items):
        return items[0]

    def title_line(self, items):
        return Metadata(title=_ast.literal_eval(str(items[0])))

    def tempo_line(self, items):
        tempo = int(items[0])
        if tempo <= 0:
            raise ValueError(f"tempo must be > 0, got {tempo}")
        return Metadata(tempo=tempo)

    def time_signature_line(self, items):
        return Metadata(time_signature=str(items[0]))

    def dsl_version_line(self, items):
        return Metadata(dsl_version=int(items[0]))

    def default_groove_line(self, items):
        return Metadata(default_groove=_ast.literal_eval(str(items[0])))

    def default_bars_line(self, items):
        return Metadata(default_bars=int(items[0]))

    def groove_def(self, items):
        name = _ast.literal_eval(str(items[0]))
        body = items[1]
        return self._build_groove_from_body(name, body)

    def _build_groove_from_body(self, name: str, body: dict) -> Groove:
        dynamic_spans = list(body.get("dynamic_spans", []))
        if body.get("count_notes") is not None:
            return Groove(
                name=name,
                bars=[],
                bar_texts={},
                count_notes=body["count_notes"],
                dynamic_spans=dynamic_spans,
            )
        if body.get("extend") is not None:
            return Groove(
                name=name,
                bars=body["bars"],
                bar_texts=body.get("bar_texts", {}),
                extend=body["extend"],
                dynamic_spans=dynamic_spans,
            )
        return Groove(
            name=name,
            bars=body["bars"],
            bar_texts=body.get("bar_texts", {}),
            dynamic_spans=dynamic_spans,
        )

    def groove_body(self, items):
        """Collect the parts of a groove body into a dict.

        Three shapes are possible:
          1. Classic: a ``pattern_content`` (instrument/bar lines).
          2. Count+notes: a ``groove_cn_body`` dict.
          3. Extend: an ``extend_body`` dict.
        """
        for item in items:
            if isinstance(item, dict) and "count_notes" in item:
                return item
            if isinstance(item, dict) and "extend" in item:
                return item
            if isinstance(item, dict) and "bars" in item:
                return item
        raise ValueError("groove_body: missing pattern, count+notes, or extend body")

    def groove_cn_body(self, items):
        count_str = _ast.literal_eval(str(items[0]))
        notes_str = _ast.literal_eval(str(items[1]))
        return {"count_notes": (count_str, notes_str)}

    def extend_body(self, items):
        """Parse ``extend: "base_groove"`` with optional pattern overrides."""
        base_name = _ast.literal_eval(str(items[0]))
        if len(items) > 1:
            # items[1] is the pattern_content result dict
            content = items[1]
            return {
                "extend": base_name,
                "bars": content["bars"],
                "bar_texts": content["bar_texts"],
                "dynamic_spans": content.get("dynamic_spans", []),
            }
        return {"extend": base_name, "bars": [], "bar_texts": {}, "dynamic_spans": []}

    def pattern_content(self, items):
        # Each item is either:
        #   - a PatternLine (from pattern_line)
        #   - a list of PatternLines (from groove_pos_line)
        #   - a (bar_num, lines, text, like_bar) tuple (from pattern_bar)
        #   - a DynamicSpan (from groove_dynamic_line)
        flat_items = []
        dynamic_spans: list[DynamicSpan] = []
        is_multi_bar = False
        for item in items:
            if isinstance(item, DynamicSpan):
                dynamic_spans.append(item)
            elif isinstance(item, tuple) and len(item) == 4 and isinstance(item[0], int):
                is_multi_bar = True
                flat_items.append(item)
            elif isinstance(item, list):
                flat_items.extend(item)  # flatten groove_pos_line result
            else:
                flat_items.append(item)  # PatternLine

        if not is_multi_bar:
            # Single-bar pattern: flat_items is a list of PatternLines
            return {"bars": [flat_items], "bar_texts": {}, "dynamic_spans": dynamic_spans}
        # Multi-bar pattern: flat_items contains (bar_num, lines, text, like_bar) tuples.
        # First pass: collect raw bars indexed by bar number.
        raw_bars: dict[int, tuple[list[PatternLine], str | None, int | None]] = {}
        for bar_num, lines, text, like_bar in flat_items:
            raw_bars[bar_num] = (lines, text, like_bar)
        # Second pass: resolve ``like: bar N`` references.
        bars = []
        bar_texts = {}
        for bar_num, (lines, text, like_bar) in sorted(raw_bars.items()):
            if like_bar is not None:
                if like_bar not in raw_bars:
                    raise ValueError(
                        f"bar {bar_num}: like: bar {like_bar} references a bar "
                        f"that does not exist in this groove"
                    )
                base_lines, _, _ = raw_bars[like_bar]
                # Merge: start with a copy of the base bar's lines, then
                # override with any lines from the current bar (same
                # instrument = replace, new instrument = add).
                merged: dict[str, PatternLine] = {
                    pl.instrument: pl for pl in base_lines
                }
                for pl in lines:
                    merged[pl.instrument] = pl
                lines = list(merged.values())
            bars.append(lines)
            if text is not None:
                bar_texts[bar_num] = text
        return {"bars": bars, "bar_texts": bar_texts, "dynamic_spans": dynamic_spans}

    def groove_dynamic_line(self, items):
        # items[0] is the ("dynamic_span", DynamicSpan) tuple from section_dynamic_line
        return items[0][1]

    def bar_like_line(self, items):
        return ("bar_like", int(items[0]))

    def pattern_bar(self, items):
        # items[0] is the bar INT, then pattern_bar_items:
        #   PatternLine (from pattern_line), list of PatternLines (from groove_pos_line),
        #   ("bar_text", str) tuple (from pattern_bar_text),
        #   or ("bar_like", int) tuple (from bar_like_line)
        bar_num = int(items[0])
        lines = []
        texts = []
        like_bar = None
        for item in items[1:]:
            if isinstance(item, PatternLine):
                lines.append(item)
            elif isinstance(item, list):
                lines.extend(item)
            elif isinstance(item, tuple) and item[0] == "bar_text":
                texts.append(item)
            elif isinstance(item, tuple) and item[0] == "bar_like":
                like_bar = item[1]
        text = texts[0][1] if texts else None
        return (bar_num, lines, text, like_bar)

    def pattern_bar_text(self, items):
        return ("bar_text", _ast.literal_eval(str(items[0])))

    @v_args(meta=True)
    def pattern_line(self, meta, items):
        return PatternLine(
            instrument=_normalize_instrument(str(items[0])),
            beats=items[1],
            line=_meta_line(meta),
        )

    @v_args(meta=True)
    def groove_pos_line(self, meta, items):
        """Position→instruments line in groove pattern: '1: BD, HH'
        Normalizes to a list of PatternLines, one per instrument hit."""
        beat_label = _normalize_beat_label(str(items[0]))

        instr_hits = items[1]  # list of InstrumentHit from fill_instruments
        source_line = _meta_line(meta)
        result = []
        for instr_hit in instr_hits:
            modifiers = getattr(instr_hit, "modifiers", [])
            buzz_dur = getattr(instr_hit, "buzz_duration", None)
            b = BeatHit(
                beat_label,
                modifiers if modifiers else None,
                buzz_duration=buzz_dur,
            )
            result.append(
                PatternLine(
                    instrument=str(instr_hit), beats=[b], line=source_line
                )
            )
        return result

    def fill_def(self, items):
        name = _ast.literal_eval(str(items[0]))
        extend: str | None = None
        bars: list[FillBar] = []
        dynamic_spans: list[DynamicSpan] = []
        for item in items[1:]:
            if isinstance(item, dict) and "fill_extend" in item:
                extend = item["fill_extend"]
            elif isinstance(item, DynamicSpan):
                dynamic_spans.append(item)
            else:
                bars.append(item)
        return Fill(
            name=name, bars=bars, dynamic_spans=dynamic_spans, extend=extend
        )

    def fill_extend_clause(self, items):
        return {"fill_extend": _ast.literal_eval(str(items[0]))}

    def fill_def_bare(self, items):
        """Fill with no count/bar delimiters — a single implicit bar."""
        name = _ast.literal_eval(str(items[0]))
        bar_items: list = []
        dynamic_spans: list[DynamicSpan] = []
        for item in items[1:]:
            if isinstance(item, DynamicSpan):
                dynamic_spans.append(item)
            else:
                bar_items.append(item)
        bar = _build_fill_bar(label=None, items=bar_items)
        return Fill(name=name, bars=[bar], dynamic_spans=dynamic_spans)

    def fill_def_extend_bare(self, items):
        """``extend: "base"`` followed by a bare single-bar body (no ``count``)."""
        name = _ast.literal_eval(str(items[0]))
        extend_clause = items[1]
        if not (isinstance(extend_clause, dict) and "fill_extend" in extend_clause):
            raise ValueError(
                f"fill {name!r}: expected extend clause before bare body"
            )
        extend = extend_clause["fill_extend"]
        bar_items: list = []
        dynamic_spans: list[DynamicSpan] = []
        for item in items[2:]:
            if isinstance(item, DynamicSpan):
                dynamic_spans.append(item)
            else:
                bar_items.append(item)
        bar = _build_fill_bar(label=None, items=bar_items)
        return Fill(
            name=name, bars=[bar], dynamic_spans=dynamic_spans, extend=extend
        )

    def fill_dynamic_line(self, items):
        return items[0][1]

    def fill_count_block(self, items):
        label = _ast.literal_eval(str(items[0]))
        return _build_fill_bar(label=label, items=items[1:])

    def fill_bar_numbered(self, items):
        """Fill bar delimited by 'bar N:' — beats fully specified, no count label."""
        # items[0] is the bar number INT; we don't retain it (file order = bar order),
        # but it acts as a visual delimiter and lets the grammar split bars.
        return _build_fill_bar(label=None, items=items[1:])

    def fill_cn_bar(self, items):
        """Count+notes fill bar: positional 1-1 mapping of count tokens to notes.

        When the ``notes:`` line is omitted, every count slot defaults to a
        single snare hit — the most common starting point for a fill.
        """
        count_str = _ast.literal_eval(str(items[0]))
        beat_labels = _parse_count_tokens(count_str)
        if len(items) == 1:
            note_groups = [[InstrumentHit("SN")] for _ in beat_labels]
        else:
            notes_str = _ast.literal_eval(str(items[1]))
            note_groups = _parse_notes_tokens(notes_str)
            if len(beat_labels) != len(note_groups):
                raise ValueError(
                    _format_count_notes_mismatch("fill block", count_str, notes_str)
                )
        lines = [
            FillLine(beat=beat, instruments=instruments)
            for beat, instruments in zip(beat_labels, note_groups)
        ]
        return FillBar(label=count_str, lines=lines)

    def fill_line(self, items):
        beat = _normalize_beat_label(str(items[0]))
        instruments = items[1]
        return FillLine(beat=beat, instruments=instruments)

    @v_args(meta=True)
    def fill_instr_line(self, meta, items):
        """Instrument→positions line in fill count block: 'BD: 1, 3' or 'BD: *8 except 4&'
        Normalizes to a list of FillLines (one per beat) or a PatternLine (for star specs)."""
        instrument = _normalize_instrument(str(items[0]))
        value = items[1]  # list of BeatHit from beat_list, or StarSpec from star/star_except
        if isinstance(value, StarSpec):
            return PatternLine(instrument=instrument, beats=value, line=_meta_line(meta))
        result = []
        for beat_hit in value:
            modifiers = getattr(beat_hit, "modifiers", [])
            buzz_dur = getattr(beat_hit, "buzz_duration", None)
            inst_hit = InstrumentHit(
                instrument, modifiers if modifiers else None, buzz_duration=buzz_dur
            )
            result.append(FillLine(beat=str(beat_hit), instruments=[inst_hit]))
        return result

    def fill_instrument_hit(self, items):
        instrument = _normalize_instrument(str(items[0]))
        raw_mods = [str(m) for m in items[1:]]
        modifiers, buzz_dur = _extract_buzz_duration(raw_mods)
        return InstrumentHit(
            instrument, modifiers if modifiers else None, buzz_duration=buzz_dur
        )

    def fill_instruments(self, items):
        return list(items)

    def section_def(self, items):
        name = _ast.literal_eval(str(items[0]))
        bars = None
        groove = None
        repeat = None
        inherit = None
        tempo = None
        time_signature = None
        play = None
        crash_in = False
        fill_placements: list[FillPlacement] = []
        fill_placeholders: list[FillPlaceholder] = []
        inline_fills: list[Fill] = []
        inline_grooves_list: list[Groove] = []
        variations: list[Variation] = []
        cues: list[Cue] = []
        dynamic_spans: list[DynamicSpan] = []

        for item in items[1:]:
            key, value = item
            if key == "bars":
                bars = value
            elif key == "groove":
                groove = value
            elif key == "inline_groove":
                inline_grooves_list.append(value)
                groove = value.name
            elif key == "repeat":
                repeat = value
            elif key == "inherit":
                inherit = value
            elif key == "tempo":
                tempo = value
            elif key == "time_signature":
                time_signature = value
            elif key == "play":
                # value is (play_items, inline_grooves_from_play)
                play_items, play_inline_grooves = value
                play = play_items
                inline_grooves_list.extend(play_inline_grooves)
            elif key == "fill":
                fill_placements.append(value)
            elif key == "fill_many":
                fill_placements.extend(value)
            elif key == "inline_fill":
                fill_def, placement = value
                inline_fills.append(fill_def)
                fill_placements.append(placement)
            elif key == "inline_fill_many":
                fill_def, placements = value
                inline_fills.append(fill_def)
                fill_placements.extend(placements)
            elif key == "fill_placeholder":
                fill_placeholders.append(value)
            elif key == "variation":
                variations.append(value)
            elif key == "cue":
                cues.append(value)
            elif key == "dynamic_span":
                dynamic_spans.append(value)
            elif key == "crash_in":
                crash_in = True

        if play is not None:
            if bars is not None or groove is not None or repeat is not None:
                raise ValueError(
                    f"Section {name!r}: play: is mutually exclusive with bars:, groove:, and repeat:"
                )
            if not play:
                raise ValueError(f"Section {name!r}: play: block must not be empty")
        # Validation of required bars/groove is deferred to compile time so
        # that metadata defaults (default_bars / default_groove) can fill
        # gaps.  The parser no longer rejects missing bars/groove here.

        return Section(
            name=name,
            bars=bars,
            groove=groove,
            repeat=repeat,
            fills=fill_placements,
            fill_placeholders=fill_placeholders,
            inline_fills=inline_fills,
            inline_grooves=inline_grooves_list,
            variations=variations,
            inherit=inherit,
            cues=cues,
            dynamic_spans=dynamic_spans,
            tempo=tempo,
            time_signature=time_signature,
            play=play,
            crash_in=crash_in,
        )

    def play_block(self, items):
        """Collect play items and any inline grooves defined inside them.

        Inline ``groove:`` bodies under ``play:`` are emitted by
        :meth:`play_groove_inline` as ``("inline_play_groove", PlayGroove, Groove)``
        tuples; we split them into a plain play-item list plus an
        ``inline_grooves`` list so :meth:`section_def` can register the
        grooves on the Section alongside the section-level inline grooves.
        """
        play_items: list = []
        inline_grooves: list[Groove] = []
        for item in items:
            if isinstance(item, tuple) and item and item[0] == "inline_play_groove":
                _, play_groove_node, groove = item
                play_items.append(play_groove_node)
                inline_grooves.append(groove)
            else:
                play_items.append(item)
        return ("play", (play_items, inline_grooves))

    def play_groove_named(self, items):
        name = _ast.literal_eval(str(items[0]))
        repeat = items[1] if len(items) > 1 else 1
        return PlayGroove(groove_name=name, repeat=repeat)

    def play_groove_inline(self, items):
        """Inline nameless groove inside a ``play:`` block.

        Builds a :class:`Groove` from the body, assigns a synthetic name,
        and returns a tagged tuple so :meth:`play_block` can register the
        groove on the enclosing Section while still producing an ordinary
        :class:`PlayGroove` play item.
        """
        repeat = 1
        body = None
        for item in items:
            if isinstance(item, int):
                repeat = item
            elif isinstance(item, dict):
                body = item
        if body is None:
            raise ValueError("play_groove_inline: missing groove body")
        self._inline_groove_counter += 1
        synthetic_name = f"__inline_play_groove_{self._inline_groove_counter}"
        groove = self._build_groove_from_body(synthetic_name, body)
        play_groove_node = PlayGroove(groove_name=synthetic_name, repeat=repeat)
        return ("inline_play_groove", play_groove_node, groove)

    def play_groove_named_inline(self, items):
        """Inline named groove inside a ``play:`` block.

        Defines a groove with a user-supplied name in-place and references
        it at the same time. Subsequent ``groove "<name>" xN`` items in the
        same section (or inheriting sections via ``like:``) resolve to this
        definition.
        """
        name = _ast.literal_eval(str(items[0]))
        repeat = 1
        body = None
        for item in items[1:]:
            if isinstance(item, int):
                repeat = item
            elif isinstance(item, dict):
                body = item
        if body is None:
            raise ValueError("play_groove_named_inline: missing groove body")
        groove = self._build_groove_from_body(name, body)
        play_groove_node = PlayGroove(groove_name=name, repeat=repeat)
        return ("inline_play_groove", play_groove_node, groove)

    def play_bar(self, items):
        name = _ast.literal_eval(str(items[0]))
        repeat = 1
        pattern = None
        for item in items[1:]:
            if isinstance(item, int):
                repeat = item
            elif isinstance(item, tuple) and item[0] == "play_bar_body":
                pattern = item[1]
        return PlayBar(name=name, pattern=pattern, repeat=repeat)

    def play_bar_body(self, items):
        pattern: list[PatternLine] = []
        for item in items:
            if isinstance(item, PatternLine):
                pattern.append(item)
            elif isinstance(item, list):
                pattern.extend(item)
        return ("play_bar_body", pattern)

    def play_rest(self, items):
        repeat = items[0] if items else 1
        return PlayRest(repeat=repeat)

    def repeat_count(self, items):
        value = int(items[0])
        if value < 1:
            raise ValueError(f"repeat count must be >= 1, got {value}")
        return value

    def section_line(self, items):
        return items[0]

    def bars_line(self, items):
        return ("bars", int(items[0]))

    def groove_line(self, items):
        """Either a named reference ``groove: "name"`` or an inline body.

        The named form returns ``("groove", name)``. The inline form
        synthesises a ``Groove`` under a unique name and returns
        ``("inline_groove", groove)`` so the section_def reducer can register
        it on the Section and replace the section's groove reference with
        the synthetic name.
        """
        first = items[0]
        if hasattr(first, "type") and first.type == "ESCAPED_STRING":
            return ("groove", _ast.literal_eval(str(first)))
        body = first
        self._inline_groove_counter += 1
        synthetic_name = f"__inline_groove_{self._inline_groove_counter}"
        groove = self._build_groove_from_body(synthetic_name, body)
        return ("inline_groove", groove)

    def repeat_line(self, items):
        return ("repeat", int(items[0]))

    def like_line(self, items):
        parent = _ast.literal_eval(str(items[0]))
        categories: list[str] = []
        for tok in items[1:]:
            name = str(tok)
            if name not in INHERIT_CATEGORIES:
                raise ValueError(
                    f'like: unknown inherit category {name!r}; expected one of '
                    f'{sorted(INHERIT_CATEGORIES)}'
                )
            if name in categories:
                raise ValueError(
                    f'like: duplicate inherit category {name!r} in "with" list'
                )
            categories.append(name)
        spec = InheritSpec(parent=parent, categories=frozenset(categories))
        return ("inherit", spec)

    def section_tempo_line(self, items):
        tempo = int(items[0])
        if tempo <= 0:
            raise ValueError(f"tempo must be > 0, got {tempo}")
        return ("tempo", tempo)

    def section_time_signature_line(self, items):
        return ("time_signature", str(items[0]))

    def section_crash_in_line(self, items):
        return ("crash_in", True)

    def section_fill_line(self, items):
        # Eight alternatives combining named/inline × single-bar/multi-bar × with/without beat:
        #   Named placement: [ESCAPED_STRING, [INT+], (BEAT_LABEL)?]
        #   Inline placement: [[INT+], (BEAT_LABEL)?, FillBar+]
        # ``bar_number_list`` always reduces to a Python list[int], so a single
        # bar still shows up as a one-element list.
        first = items[0]
        if hasattr(first, "type") and first.type == "ESCAPED_STRING":
            fill_name = _ast.literal_eval(str(first))
            bar_nums = items[1]  # list[int] from bar_number_list
            beat = _normalize_beat_label(str(items[2])) if len(items) > 2 else None
            placements = [
                FillPlacement(fill_name=fill_name, bar=bar, beat=beat)
                for bar in bar_nums
            ]
            if len(placements) == 1:
                return ("fill", placements[0])
            return ("fill_many", placements)

        # Inline fill: items[0] is the bar_number_list (list[int]).
        bar_nums = first
        idx = 1
        beat: str | None = None
        if idx < len(items) and hasattr(items[idx], "type") and items[idx].type == "BEAT_LABEL":
            beat = _normalize_beat_label(str(items[idx]))
            idx += 1
        fill_bars = []
        dynamic_spans = []
        for item in items[idx:]:
            if isinstance(item, DynamicSpan):
                dynamic_spans.append(item)
            else:
                fill_bars.append(item)
        self._inline_fill_counter += 1
        synthetic_name = f"__inline_fill_{self._inline_fill_counter}"
        fill_def = Fill(name=synthetic_name, bars=fill_bars, dynamic_spans=dynamic_spans)
        placements = [
            FillPlacement(fill_name=synthetic_name, bar=bar, beat=beat)
            for bar in bar_nums
        ]
        if len(placements) == 1:
            return ("inline_fill", (fill_def, placements[0]))
        return ("inline_fill_many", (fill_def, placements))

    def section_inline_fill_bare(self, items):
        """Inline fill with no `count "..."` header — a single implicit bar
        whose beats are fully specified by the lines themselves.

        Layout: [bar_nums, (BEAT_LABEL)?, fill_count_item*, DynamicSpan*]."""
        bar_nums = items[0]
        idx = 1
        beat: str | None = None
        if idx < len(items) and hasattr(items[idx], "type") and items[idx].type == "BEAT_LABEL":
            beat = _normalize_beat_label(str(items[idx]))
            idx += 1
        bar_items: list = []
        dynamic_spans: list[DynamicSpan] = []
        for item in items[idx:]:
            if isinstance(item, DynamicSpan):
                dynamic_spans.append(item)
            else:
                bar_items.append(item)
        bar = _build_fill_bar(label=None, items=bar_items)
        self._inline_fill_counter += 1
        synthetic_name = f"__inline_fill_{self._inline_fill_counter}"
        fill_def = Fill(name=synthetic_name, bars=[bar], dynamic_spans=dynamic_spans)
        placements = [
            FillPlacement(fill_name=synthetic_name, bar=n, beat=beat)
            for n in bar_nums
        ]
        if len(placements) == 1:
            return ("inline_fill", (fill_def, placements[0]))
        return ("inline_fill_many", (fill_def, placements))

    def section_fill_placeholder_line(self, items):
        # Four alternatives depending on whether label and/or beat are present:
        #   fill placeholder at bar N              → items = [INT]
        #   fill placeholder "label" at bar N      → items = [ESCAPED_STRING, INT]
        #   fill placeholder at bar N beat X       → items = [INT, BEAT_LABEL]
        #   fill placeholder "label" at bar N beat X → items = [ESCAPED_STRING, INT, BEAT_LABEL]
        if items[0].type == "ESCAPED_STRING":
            label = _ast.literal_eval(str(items[0]))
            bar = int(items[1])
            beat = str(items[2]) if len(items) > 2 else None
        else:
            label = "fill"
            bar = int(items[0])
            beat = str(items[1]) if len(items) > 1 else None
        if beat:
            beat = _normalize_beat_label(beat)
        return ("fill_placeholder", FillPlaceholder(label=label, bar=bar, beat=beat))

    def section_cue_line(self, items):
        text = _ast.literal_eval(str(items[0]))
        bar = int(items[1])
        beat = _normalize_beat_label(str(items[2])) if len(items) > 2 else None
        return ("cue", Cue(text=text, bar=bar, beat=beat))

    @v_args(meta=True)
    def section_dynamic_line(self, meta, items):
        # Five alternatives depending on form:
        #   cresc bar N                                    → [KIND, INT]         (shorthand)
        #   cresc from bar N to bar M                      → [KIND, INT, INT]
        #   cresc from bar N beat X to bar M               → [KIND, INT, BEAT, INT]
        #   cresc from bar N to bar M beat Y               → [KIND, INT, INT, BEAT]
        #   cresc from bar N beat X to bar M beat Y        → [KIND, INT, BEAT, INT, BEAT]
        kind = str(items[0])
        # Normalize long-form synonyms to canonical kind values.
        if kind == "crescendo":
            kind = "cresc"
        elif kind == "decrescendo":
            kind = "decresc"
        source_line = _meta_line(meta)
        # Walk items[1:] parsing INT/BEAT_LABEL tokens in order
        ints = []
        beats = []
        for item in items[1:]:
            if hasattr(item, "type") and item.type == "BEAT_LABEL":
                beats.append(_normalize_beat_label(str(item)))
            else:
                ints.append(int(item))
        if len(ints) == 1:
            # Shorthand: cresc bar N → single-bar hairpin
            return ("dynamic_span", DynamicSpan(kind=kind, from_bar=ints[0], to_bar=ints[0], line=source_line))
        from_bar, to_bar = ints[0], ints[1]
        if len(beats) == 0:
            from_beat, to_beat = None, None
        elif len(beats) == 2:
            from_beat, to_beat = beats[0], beats[1]
        elif len(items) == 4:
            # Distinguish the two single-beat alternatives by token order.
            # items: [KIND, INT, BEAT, INT] or [KIND, INT, INT, BEAT]
            if hasattr(items[2], "type") and items[2].type == "BEAT_LABEL":
                from_beat, to_beat = beats[0], None
            else:
                from_beat, to_beat = None, beats[0]
        else:
            from_beat, to_beat = None, None
        return ("dynamic_span", DynamicSpan(kind=kind, from_bar=from_bar, to_bar=to_bar, from_beat=from_beat, to_beat=to_beat, line=source_line))

    def bar_number_list(self, items):
        return [int(i) for i in items]

    def variation_def(self, items):
        name = _ast.literal_eval(str(items[0]))
        raw_actions = list(items[1:])
        actions: list[VariationAction] = []
        for item in raw_actions:
            if isinstance(item, list) and item and isinstance(item[0], VariationAction):
                actions.extend(item)
            elif isinstance(item, VariationAction):
                actions.append(item)
        return VariationDef(name=name, actions=actions)

    def section_variation_ref(self, items):
        # variation "name" at bar N, M  —  no body. Resolved to actions by
        # the compiler from the top-level variation defs plus library.
        name = _ast.literal_eval(str(items[0]))
        bar_nums = items[1]  # list[int] from bar_number_list
        return ("variation", Variation(name=name, bars=bar_nums, actions=[]))

    def section_variation_block(self, items):
        # Four alternatives (with/without name × bar/bars):
        #   variation "name" at bar N, M: … → [STR, [N, M], actions…]
        #   variation        at bar N, M: … → [[N, M], actions…]
        first = items[0]
        if hasattr(first, "type") and first.type == "ESCAPED_STRING":
            name = _ast.literal_eval(str(first))
            bar_nums = items[1]  # list[int] from bar_number_list
            raw_actions = list(items[2:])
        else:
            name = None
            bar_nums = items[0]  # list[int] from bar_number_list
            raw_actions = list(items[1:])
        # add/remove/replace actions now return a list (one VariationAction per
        # instrument in a multi-instrument form). Flatten them while passing
        # through substitute_action, which returns a single VariationAction.
        actions: list[VariationAction] = []
        for item in raw_actions:
            if isinstance(item, list) and item and isinstance(item[0], VariationAction):
                actions.extend(item)
            elif isinstance(item, VariationAction):
                actions.append(item)
        return ("variation", Variation(name=name, bars=bar_nums, actions=actions))

    def add_instr_spec(self, items):
        # items: [INSTRUMENT, *MODIFIER tokens]
        instrument = _normalize_instrument(str(items[0]))
        raw_mods = [str(m) for m in items[1:]]
        modifiers, buzz_dur = _extract_buzz_duration(raw_mods)
        return (instrument, modifiers, buzz_dur)

    def replace_instr_spec(self, items):
        # items: [INSTRUMENT, *MODIFIER tokens]
        instrument = _normalize_instrument(str(items[0]))
        raw_mods = [str(m) for m in items[1:]]
        modifiers, buzz_dur = _extract_buzz_duration(raw_mods)
        return (instrument, modifiers, buzz_dur)

    @v_args(meta=True)
    def add_action(self, meta, items):
        # items: [(instrument, modifiers, buzz_duration)+, pattern_value]
        beats = items[-1]
        specs = items[:-1]
        source_line = _meta_line(meta)
        return [
            VariationAction(
                action="add",
                instrument=instrument,
                beats=beats,
                modifiers=list(modifiers),
                buzz_duration=buzz_duration,
                line=source_line,
            )
            for instrument, modifiers, buzz_duration in specs
        ]

    @v_args(meta=True)
    def remove_action(self, meta, items):
        # items: [INSTRUMENT+, pattern_value]
        beats = items[-1]
        instruments = [_normalize_instrument(str(tok)) for tok in items[:-1]]
        source_line = _meta_line(meta)
        return [
            VariationAction(
                action="remove", instrument=instrument, beats=beats, line=source_line
            )
            for instrument in instruments
        ]

    @v_args(meta=True)
    def replace_action(self, meta, items):
        # items: [INSTRUMENT+ (from), (INSTRUMENT, modifiers, buzz_duration)+ (to), pattern_value]
        beats = items[-1]
        middle = items[:-1]
        sources: list[str] = []
        targets: list[tuple[str, list[str], str | None]] = []
        for item in middle:
            if isinstance(item, tuple):
                targets.append(item)
            else:
                sources.append(_normalize_instrument(str(item)))
        if len(sources) != len(targets):
            raise ValueError(
                f"replace: number of source instruments ({len(sources)}) must "
                f"match number of target instruments ({len(targets)})"
            )
        source_line = _meta_line(meta)
        return [
            VariationAction(
                action="replace",
                instrument=source,
                target_instrument=target,
                beats=beats,
                modifiers=list(target_mods),
                buzz_duration=target_buzz,
                line=source_line,
            )
            for source, (target, target_mods, target_buzz) in zip(sources, targets)
        ]

    @v_args(meta=True)
    def substitute_action(self, meta, items):
        # items: [ESCAPED_STRING count, ESCAPED_STRING notes]
        count_str = _ast.literal_eval(str(items[0]))
        notes_str = _ast.literal_eval(str(items[1]))
        return VariationAction(
            action="substitute",
            count_notes=(count_str, notes_str),
            line=_meta_line(meta),
        )

    @v_args(meta=True)
    def modify_add_action(self, meta, items):
        # items: [MODIFIER+, INSTRUMENT, variation_target]
        beats = items[-1]
        instrument = _normalize_instrument(str(items[-2]))
        raw_mods = [str(m) for m in items[:-2]]
        modifiers, buzz_dur = _extract_buzz_duration(raw_mods)
        return VariationAction(
            action="modify_add",
            instrument=instrument,
            beats=beats,
            modifiers=list(modifiers),
            buzz_duration=buzz_dur,
            line=_meta_line(meta),
        )

    @v_args(meta=True)
    def modify_remove_action(self, meta, items):
        # items: [MODIFIER+, INSTRUMENT, variation_target]
        beats = items[-1]
        instrument = _normalize_instrument(str(items[-2]))
        raw_mods = [str(m) for m in items[:-2]]
        modifiers, buzz_dur = _extract_buzz_duration(raw_mods)
        return VariationAction(
            action="modify_remove",
            instrument=instrument,
            beats=beats,
            modifiers=list(modifiers),
            buzz_duration=buzz_dur,
            line=_meta_line(meta),
        )

    def star(self, items):
        """Parse a ``*N``/``*Nt`` STAR_VALUE token into a :class:`StarSpec`."""
        token = str(items[0])
        assert token.startswith("*"), token
        body = token[1:]
        triplet = body.endswith("t")
        digits = body[:-1] if triplet else body
        return StarSpec(note_value=int(digits), triplet=triplet)

    def star_except(self, items):
        """Parse ``*N except beat_list`` into a :class:`StarSpec` with exclusions."""
        token = str(items[0])
        assert token.startswith("*"), token
        body = token[1:]
        triplet = body.endswith("t")
        digits = body[:-1] if triplet else body
        beat_list = items[1]  # list of BeatHit from beat_list rule
        except_beats = tuple(_normalize_beat_label(str(b)) for b in beat_list)
        return StarSpec(note_value=int(digits), triplet=triplet, except_beats=except_beats)

    def variation_star(self, items):
        """Return the bare ``*`` wildcard for variation action targets.

        Variation actions use ``*`` to mean "every beat in the bar" — kept
        distinct from pattern-line ``*N`` stars, which encode a note value.
        """
        return "*"

    def beat_list(self, items):
        return list(items)

    def beat(self, items):
        label = _normalize_beat_label(str(items[0]))
        raw_mods = [str(m) for m in items[1:]]
        modifiers, buzz_dur = _extract_buzz_duration(raw_mods)
        return BeatHit(label, modifiers if modifiers else None, buzz_duration=buzz_dur)

    @staticmethod
    def _merge_metadata(target: Metadata, incoming: Metadata) -> None:
        if incoming.title is not None:
            target.title = incoming.title
        if incoming.tempo is not None:
            target.tempo = incoming.tempo
        if incoming.time_signature != "4/4":
            target.time_signature = incoming.time_signature
        if incoming.dsl_version is not None:
            target.dsl_version = incoming.dsl_version
        if incoming.default_groove is not None:
            target.default_groove = incoming.default_groove
        if incoming.default_bars is not None:
            target.default_bars = incoming.default_bars


_parser = Lark(
    _GRAMMAR_PATH.read_text(),
    parser="lalr",
    start="start",
    propagate_positions=True,
)
