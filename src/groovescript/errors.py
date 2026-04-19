"""User-facing error reporting for GrooveScript.

This module defines :class:`GrooveScriptError`, a single exception class used
for all errors that should be presented to the user when parsing or compiling
a ``.gs`` file. It carries a source location (filename, line, column, span)
plus an optional hint, and knows how to render itself as a multi-line
diagnostic in the style::

    error: unknown instrument 'snars'
      --> song.gs:4:5
       |
     4 |     snars: 1, 3
       |     ^^^^^ hint: did you mean 'snare'?

Both the CLI and the test suite rely on :meth:`GrooveScriptError.render` for
the formatted output; :meth:`__str__` delegates to it so ``str(err)`` and
tracebacks are equally readable.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass


# Known instrument aliases (lowercase) used for spelling-suggestion hints.
# Duplicated here rather than imported from parser.py to avoid a circular
# import — parser.py imports this module.
_KNOWN_INSTRUMENT_ALIASES: tuple[str, ...] = (
    "bd", "sn", "scs", "hh", "oh", "rd", "cr", "ft", "ht", "mt", "hf",
    "bass", "kick", "snare", "click", "cross-stick",
    "hat", "hihat", "openhat", "open",
    "ride", "crash", "floortom", "lowtom", "hightom", "hitom", "midtom",
    "hihatfoot", "footchick",
)

_KNOWN_MODIFIERS: tuple[str, ...] = ("ghost", "accent", "flam", "drag", "double", "32nd")


@dataclass
class GrooveScriptError(Exception):
    """A user-facing GrooveScript error.

    Attributes:
        message: Short one-line description of what went wrong.
        filename: Path of the source file, or ``None`` for anonymous input.
        source: Full source text, used to show the offending line.
        line: 1-indexed line number, or ``None`` if no location is known.
        column: 1-indexed column number, or ``None`` if no location is known.
        length: Number of characters to underline (defaults to 1).
        hint: Optional single-line suggestion for how to fix the error.
    """

    message: str
    filename: str | None = None
    source: str | None = None
    line: int | None = None
    column: int | None = None
    length: int = 1
    hint: str | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)

    # ── Rendering ────────────────────────────────────────────────────────

    def render(self) -> str:
        """Return a multi-line formatted diagnostic for terminal display."""
        out: list[str] = [f"error: {self.message}"]

        if self.line is not None:
            where = self.filename or "<input>"
            col_part = f":{self.column}" if self.column is not None else ""
            out.append(f"  --> {where}:{self.line}{col_part}")

            line_text = self._source_line()
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

    def __str__(self) -> str:  # pragma: no cover — trivial delegator
        return self.render()

    def _source_line(self) -> str | None:
        if self.source is None or self.line is None:
            return None
        lines = self.source.splitlines()
        idx = self.line - 1
        if 0 <= idx < len(lines):
            return lines[idx]
        return None


# ── Helpers for building hints ───────────────────────────────────────────


def suggest_instrument(token: str) -> str | None:
    """Suggest a known instrument alias close to ``token``, or ``None``."""
    matches = difflib.get_close_matches(token.lower(), _KNOWN_INSTRUMENT_ALIASES, n=1, cutoff=0.6)
    return matches[0] if matches else None


def suggest_modifier(token: str) -> str | None:
    matches = difflib.get_close_matches(token.lower(), _KNOWN_MODIFIERS, n=1, cutoff=0.6)
    return matches[0] if matches else None


def suggest_from_choices(token: str, choices: list[str]) -> str | None:
    """Generic close-match suggestion against an explicit list of choices."""
    matches = difflib.get_close_matches(token.lower(), [c.lower() for c in choices], n=1, cutoff=0.6)
    if not matches:
        return None
    # Return the original-casing version.
    for c in choices:
        if c.lower() == matches[0]:
            return c
    return matches[0]
