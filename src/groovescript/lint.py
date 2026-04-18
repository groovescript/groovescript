"""Stylistic lint checks for GrooveScript source files.

These checks are surfaced via ``groovescript lint --style``. Unlike the
errors raised by :mod:`parser` and :mod:`compiler`, style warnings do not
block compilation — they highlight code that is legal but stylistically
questionable or that references names that will not be found at compile
time, so the author can catch such issues earlier and with a more focused
diagnostic.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction

from .ast_nodes import PlayGroove, Section, Song


@dataclass
class StyleWarning:
    """A single stylistic issue with a source location and optional hint."""

    message: str
    line: int | None = None
    column: int | None = None
    length: int = 1
    hint: str | None = None

    def render(self, filename: str | None = None, source: str | None = None) -> str:
        """Render a Rust-style ``warning:`` diagnostic, mirroring
        :meth:`GrooveScriptError.render` so CLI output is visually
        consistent between errors and warnings.
        """
        out: list[str] = [f"warning: {self.message}"]
        if self.line is not None:
            where = filename or "<input>"
            col_part = f":{self.column}" if self.column is not None else ""
            out.append(f"  --> {where}:{self.line}{col_part}")
            line_text = self._source_line(source)
            if line_text is not None:
                gutter = f"{self.line:>4}"
                pad = " " * len(gutter)
                out.append(f"{pad} |")
                out.append(f"{gutter} | {line_text}")
                if self.column is not None:
                    caret_pad = " " * (self.column - 1)
                    caret = "^" * max(self.length, 1)
                    hint_suffix = f" hint: {self.hint}" if self.hint else ""
                    out.append(f"{pad} | {caret_pad}{caret}{hint_suffix}")
                elif self.hint:
                    out.append(f"{pad} | hint: {self.hint}")
            elif self.hint:
                out.append(f"hint: {self.hint}")
        elif self.hint:
            out.append(f"hint: {self.hint}")
        return "\n".join(out)

    def _source_line(self, source: str | None) -> str | None:
        if source is None or self.line is None:
            return None
        lines = source.splitlines()
        idx = self.line - 1
        if 0 <= idx < len(lines):
            return lines[idx]
        return None


# Instrument and beat-label regex fragments used to detect the two groove
# line styles in a textual pass. These mirror the patterns in
# ``grammar.lark`` (and ``parser._PP_INSTRUMENT_RE`` / ``_PP_BEAT_LABEL_RE``).
_INSTRUMENT_RE = (
    r"(?:SRS|SCS|cross-stick|rimshot|floortom|hightom|hitom|lowtom|midtom"
    r"|openhat|hihatfoot|footchick|hihat|snare|crash|click|ride|bass|kick"
    r"|open|hat|BD|bd|SN|sn|OH|oh|RD|rd|CR|cr|FT|ft|HH|hh|HT|ht|MT|mt|HF|hf)"
)
_BEAT_LABEL_RE = r"[1-9][0-9]?(?:trip|let|and|[e&atl])?"

_INSTR_LINE_RE = re.compile(rf"^(?P<indent>\s+){_INSTRUMENT_RE}\s*:")
_POS_LINE_RE = re.compile(rf"^(?P<indent>\s+){_BEAT_LABEL_RE}\s*:")
_GROOVE_HEADER_RE = re.compile(r"^\s*groove\s+\"[^\"]*\"\s*:")
_BAR_HEADER_RE = re.compile(r"^(?P<indent>\s+)bar\s+\d+\s*:")


def _check_mixed_groove_styles(source: str) -> list[StyleWarning]:
    """Warn when a single groove body (or single ``bar N:`` block) mixes
    instrument→positions and position→instruments lines.

    Both styles are legal and can be mixed — the grammar accepts either
    — but a consistent choice makes the groove easier to read. The check
    is scoped per-bar: within a ``bar N:`` block the two styles are
    compared only against other lines in the same bar, never across bars.
    """
    warnings: list[StyleWarning] = []
    lines = source.split("\n")
    i = 0
    while i < len(lines):
        if _GROOVE_HEADER_RE.match(lines[i]):
            # Collect the contiguous indented body below this header.
            body_start = i + 1
            j = body_start
            while j < len(lines):
                line = lines[j]
                if line.strip() == "":
                    j += 1
                    continue
                # A non-indented line ends the groove body.
                if not line.startswith((" ", "\t")):
                    break
                # A new top-level ``groove``/``section``/``fill`` would
                # also end it, but those are not indented, so the check
                # above already covers them.
                j += 1
            warnings.extend(_scan_groove_body(lines, body_start, j))
            i = j
            continue
        i += 1
    return warnings


def _scan_groove_body(
    lines: list[str], start: int, end: int
) -> list[StyleWarning]:
    """Walk lines[start:end] splitting on ``bar N:`` headers and check each
    bar scope (or the whole single-bar body) for style mixing.
    """
    warnings: list[StyleWarning] = []
    bar_scopes: list[tuple[int, int]] = []  # (scope_start, scope_end) exclusive
    # Detect whether the body is multi-bar by looking for at least one
    # ``bar N:`` header at the body's base indent.
    base_indent: str | None = None
    has_bar_header = False
    for k in range(start, end):
        if lines[k].strip() == "":
            continue
        m = _BAR_HEADER_RE.match(lines[k])
        if base_indent is None:
            # The first non-blank line sets the body indent, whether bar
            # header or a plain pattern line.
            lead = len(lines[k]) - len(lines[k].lstrip())
            base_indent = lines[k][:lead]
        if m and m.group("indent") == base_indent:
            has_bar_header = True
            break

    if not has_bar_header:
        bar_scopes.append((start, end))
    else:
        # Slice the body at each ``bar N:`` header.
        cur = None
        for k in range(start, end):
            if _BAR_HEADER_RE.match(lines[k]):
                if cur is not None:
                    bar_scopes.append((cur, k))
                cur = k + 1
        if cur is not None:
            bar_scopes.append((cur, end))

    for scope_start, scope_end in bar_scopes:
        warnings.extend(_check_scope_style_mix(lines, scope_start, scope_end))
    return warnings


def _check_scope_style_mix(
    lines: list[str], start: int, end: int
) -> list[StyleWarning]:
    """Emit at most one warning per scope: when the scope contains both
    styles, point at the second style's first occurrence so the author
    sees exactly where consistency broke.
    """
    instr_line: int | None = None
    pos_line: int | None = None
    for k in range(start, end):
        if _INSTR_LINE_RE.match(lines[k]):
            if instr_line is None:
                instr_line = k + 1
        elif _POS_LINE_RE.match(lines[k]):
            if pos_line is None:
                pos_line = k + 1
    if instr_line is not None and pos_line is not None:
        # Point at whichever appeared second — that's the line that
        # "broke" the consistency of the scope.
        later = max(instr_line, pos_line)
        # Column 1 works here; the scope-level diagnostic is about the
        # groove as a whole rather than a particular token on the line.
        return [
            StyleWarning(
                message=(
                    "groove body mixes instrument→positions and "
                    "position→instruments lines"
                ),
                line=later,
                column=1,
                hint="pick one style per groove (or per bar) for readability",
            )
        ]
    return []


# ── Unused / dangling reference checks ────────────────────────────────────


def _collect_referenced_groove_names(song: Song) -> set[str]:
    """Walk the song and return every groove name referenced by a section.

    Covers classic sections (``groove: "name"``), ``play:`` items
    (``groove "name" x2``), and inline unnamed grooves (which never appear
    on the unused-definitions list because they have synthetic names but
    are always consumed by their enclosing section).
    """
    referenced: set[str] = set()
    default = song.metadata.default_groove
    if default is not None:
        referenced.add(default)
    for section in song.sections:
        if section.groove is not None:
            referenced.add(section.groove)
        if section.play is not None:
            for item in section.play:
                if isinstance(item, PlayGroove):
                    referenced.add(item.groove_name)
    # ``extend:`` inside a groove should also count — an extended groove
    # pulls in its base, so the base is not "unused" even if no section
    # names it directly.
    for groove in song.grooves:
        if groove.extend is not None:
            referenced.add(groove.extend)
    return referenced


def _collect_referenced_fill_names(song: Song) -> set[str]:
    referenced: set[str] = set()
    for section in song.sections:
        for placement in section.fills:
            referenced.add(placement.fill_name)
    return referenced


def _check_unused_definitions(song: Song) -> list[StyleWarning]:
    """Warn on top-level grooves/fills that are never referenced."""
    warnings: list[StyleWarning] = []
    used_grooves = _collect_referenced_groove_names(song)
    for groove in song.grooves:
        if groove.name not in used_grooves:
            warnings.append(
                StyleWarning(
                    message=f"groove {groove.name!r} is defined but never used",
                    hint=(
                        "reference it from a section with "
                        f"`groove: \"{groove.name}\"` or remove the definition"
                    ),
                )
            )
    used_fills = _collect_referenced_fill_names(song)
    for fill in song.fills:
        if fill.name not in used_fills:
            warnings.append(
                StyleWarning(
                    message=f"fill {fill.name!r} is defined but never used",
                    hint=(
                        "place it with "
                        f"`fill \"{fill.name}\" at bar N` in a section, "
                        "or remove the definition"
                    ),
                )
            )
    return warnings


def _check_section_like_refs(song: Song) -> list[StyleWarning]:
    """Warn when a section's ``like`` points at an unknown section name.

    Compile time also rejects this, but with a less focused diagnostic;
    catching it in the style lint lets the author fix the typo before
    trying a full compile.
    """
    warnings: list[StyleWarning] = []
    known: set[str] = {s.name for s in song.sections}
    for section in song.sections:
        if section.inherit is None:
            continue
        parent = section.inherit.parent
        if parent in known:
            continue
        suggestion = _closest_name(parent, known)
        hint = (
            f"did you mean {suggestion!r}?" if suggestion else
            "define the referenced section first, or remove the `like` line"
        )
        warnings.append(
            StyleWarning(
                message=(
                    f"section {section.name!r} has `like "
                    f"\"{parent}\"` but no such section is defined"
                ),
                hint=hint,
            )
        )
    return warnings


def _closest_name(target: str, choices: set[str]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(target, list(choices), n=1, cutoff=0.6)
    return matches[0] if matches else None


def _check_bar_hands(events: list, bar_context: str) -> list[StyleWarning]:
    """Return warnings for beat positions where hand-played instruments exceed what 2 hands can play.

    A flam uses both hands by itself, so a flam plus any other hand instrument is flagged.
    Without a flam, more than 2 simultaneous hand instruments are flagged.
    """
    from .compiler import _HAND_INSTRUMENTS

    by_pos: dict[Fraction, list[tuple[str, list[str]]]] = defaultdict(list)
    for event in events:
        if event.instrument in _HAND_INSTRUMENTS:
            by_pos[event.beat_position].append((event.instrument, event.modifiers))
    warnings: list[StyleWarning] = []
    for pos, instrument_mods in sorted(by_pos.items()):
        instruments = [inst for inst, _ in instrument_mods]
        flam_instruments = [inst for inst, mods in instrument_mods if "flam" in mods]
        if flam_instruments and len(instruments) >= 2:
            names = ", ".join(instruments)
            flam_names = ", ".join(flam_instruments)
            warnings.append(StyleWarning(
                message=(
                    f"{bar_context}: flam on {flam_names} uses both hands but "
                    f"{len(instruments) - len(flam_instruments)} other hand-played instrument(s) "
                    f"also sound at beat position {pos} ({names})"
                ),
                hint="a flam uses both hands; remove or revoice the simultaneous parts",
            ))
        elif len(instruments) > 2:
            names = ", ".join(instruments)
            warnings.append(StyleWarning(
                message=(
                    f"{bar_context}: {len(instruments)} hand-played instruments "
                    f"sound simultaneously at beat position {pos} ({names})"
                ),
                hint="a drummer only has 2 hands; remove or revoice one of the simultaneous parts",
            ))
    return warnings


def check_notation(ir) -> list[StyleWarning]:
    """Check compiled IR for physical notation impossibilities.

    Currently detects beat positions where more than 2 hand-played instruments
    sound simultaneously (a drummer only has 2 hands).  Runs unconditionally on
    both ``lint`` and ``compile``; does not block output.
    """
    from .compiler import IRGroove, IRSong

    warnings: list[StyleWarning] = []
    if isinstance(ir, IRSong):
        for bar in ir.bars:
            context = f"bar {bar.number}"
            if bar.section_name:
                context += f" (section '{bar.section_name}')"
            warnings.extend(_check_bar_hands(bar.events, context))
    elif isinstance(ir, IRGroove):
        bar_nums = sorted({e.bar for e in ir.events})
        for bar_num in bar_nums:
            bar_events = [e for e in ir.events if e.bar == bar_num]
            warnings.extend(_check_bar_hands(bar_events, f"groove '{ir.name}' bar {bar_num}"))
    return warnings


def check_style(source: str, song: Song) -> list[StyleWarning]:
    """Run every style check against ``source`` / ``song`` and return the
    concatenated list of :class:`StyleWarning` values in source order
    where a location is known; unused-definition warnings (which do not
    carry a location) are appended at the end.
    """
    warnings: list[StyleWarning] = []
    warnings.extend(_check_mixed_groove_styles(source))
    warnings.extend(_check_section_like_refs(song))
    warnings.extend(_check_unused_definitions(song))
    # Sort located warnings first (stable on line/column); locationless
    # ones keep their original order at the tail.
    located = [w for w in warnings if w.line is not None]
    unlocated = [w for w in warnings if w.line is None]
    located.sort(key=lambda w: (w.line or 0, w.column or 0))
    return located + unlocated
