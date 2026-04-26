"""Source-level preprocessors that run before Lark sees the text.

Three rewrites happen per line, in order:
  1. ``_quote_unquoted_count_notes`` wraps bare ``count:``/``notes:`` values in
     double quotes so the grammar's ``ESCAPED_STRING`` terminal matches.
  2. ``_commafy_bar_list`` inserts commas between adjacent bar numbers after
     ``variation ... at bar(s)`` / ``fill ... at bar(s)`` prefixes.
  3. ``_rewrite_rhs_list`` inserts commas between adjacent items in pattern
     lines, position→instrument lines, and variation action RHS lists.

Line counts are preserved 1:1 between original and preprocessed source; the
column-mapping helpers let diagnostics report errors against the original
column the author typed rather than against columns in the synthesized text.
"""

import re
from difflib import SequenceMatcher

from .parser_notation import (
    _is_buzz_token,
    _is_modifier_token,
    _normalize_modifier,
)

# ── Comma-insertion preprocessor ──────────────────────────────────────────
#
# Commas are optional in any context where a list of primary tokens (beats
# or instruments) may be adjacent: pattern lines (`BD: 1 3`), position-style
# groove/fill lines (`1: BD HH`), and variation actions (`add SN at 1 3`).
# LALR(1) can't disambiguate "next item in list" from "start of next
# line" when both begin with the same terminal, so we insert the missing
# commas at the source level before Lark sees the text.


# Bare suffix tokens that refer to the last seen beat number instead of
# starting a new beat. When seen on its own, the preprocessor resolves the
# token to ``<last_beat><mapped_suffix>``. Only recognized in beat-list
# contexts (pattern lines and variation actions), not in
# position→instrument lines.
_BARE_SUFFIX_TOKENS: dict[str, str] = {
    "and": "&",
    "e": "e",
    "&": "&",
    "a": "a",
    "trip": "trip",
    "let": "let",
}

# Instrument tokens recognized by the preprocessor. Must stay in sync with
# grammar.lark's INSTRUMENT terminal (minus the `hi-hat` variant which is
# only accepted inside count+notes string bodies, not on DSL lines).
_PP_INSTRUMENT_RE = (
    r"(?:SRS|SCS|cross-stick|rimshot|floortom|hightom|hitom|lowtom|midtom"
    r"|openhat|hihatfoot|footchick|hihat|snare|crash|click|ride|bass|kick|open|hat"
    r"|BD|bd|SN|sn|OH|oh|RD|rd|CR|cr|FT|ft|HH|hh|HT|ht|MT|mt|HF|hf)"
)
_PP_BEAT_LABEL_RE = r"[1-9][0-9]?(?:trip|let|and|[e&atl])?"

_PP_PATTERN_LINE_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<lhs>{_PP_INSTRUMENT_RE}):(?P<rhs>.*)$"
)
_PP_POS_LINE_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<lhs>{_PP_BEAT_LABEL_RE}):(?P<rhs>.*)$"
)
_PP_VAR_ACTION_RE = re.compile(
    r"^(?P<indent>\s*)(?P<prefix>(?:add|remove|replace)\b[^\n]*?\sat\s+)"
    r"(?P<rhs>.*)$"
)


def _strip_trailing_comment(line: str) -> tuple[str, str]:
    """Split off a trailing ``//…`` or ``#…`` comment.

    Respects double-quoted strings so that ``"//"`` inside a string literal
    is preserved.
    """
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            in_str = not in_str
        elif not in_str:
            if c == "#":
                return line[:i], line[i:]
            if c == "/" and i + 1 < len(line) and line[i + 1] == "/":
                return line[:i], line[i:]
        i += 1
    return line, ""


def _group_list_items(rhs: str, allow_bare_suffix: bool = False) -> str:
    """Group a space-or-comma-delimited list of ``primary MODIFIER*`` items
    with explicit commas between items.

    ``BD: 1 3`` → ``BD: 1, 3``
    ``1: BD HH flam CR`` → ``1: BD, HH flam, CR``
    ``HH: *8`` → ``HH: *8`` (unchanged)

    When ``allow_bare_suffix`` is true, a bare suffix token (``and``, ``e``,
    ``&``, ``a``, ``trip``, ``let``) resolves to the most recently seen
    beat digit plus that suffix — same semantics as ``_parse_count_tokens``
    for count strings. So ``1 and 2 and`` → ``1, 1&, 2, 2&``.

    Leaves the RHS unchanged when it contains a string literal (e.g. a
    ``groove: "name"`` line that the caller passed in by mistake) so we
    never corrupt a quoted value.
    """
    stripped = rhs.strip()
    if not stripped:
        return stripped
    # ``*N`` / ``*Nt`` star-value RHS: pass through untouched, unless it
    # contains an ``except`` clause whose beat list needs comma insertion.
    if stripped.startswith("*"):
        except_match = re.match(r"(\*(?:2|4|8|16)t?)\s+except\s+(.*)", stripped)
        if except_match:
            star_part = except_match.group(1)
            beat_rhs = except_match.group(2)
            beat_rhs_commafied = _group_list_items(beat_rhs, allow_bare_suffix=True)
            return f"{star_part} except {beat_rhs_commafied}"
        return stripped
    if '"' in stripped:
        return stripped
    tokens = [t for t in stripped.replace(",", " ").split() if t]
    if not tokens:
        return stripped
    items: list[str] = []
    current: list[str] = []
    last_beat_digits: str | None = None
    for tok in tokens:
        if _is_modifier_token(tok):
            norm_tok = _normalize_modifier(tok) if not _is_buzz_token(tok) else tok
            if current:
                current.append(norm_tok)
            else:
                items.append(norm_tok)
            continue
        # Bare suffix token (only in beat-list contexts): attach to the
        # most recently seen beat number.
        if (
            allow_bare_suffix
            and tok in _BARE_SUFFIX_TOKENS
            and last_beat_digits is not None
        ):
            resolved = last_beat_digits + _BARE_SUFFIX_TOKENS[tok]
            if current:
                items.append(" ".join(current))
            current = [resolved]
            continue
        # Primary (beat label or instrument).
        if current:
            items.append(" ".join(current))
        current = [tok]
        if tok and tok[0].isdigit():
            m = re.match(r"\d+", tok)
            if m:
                last_beat_digits = m.group(0)
    if current:
        items.append(" ".join(current))
    return ", ".join(items)


def _rewrite_rhs_list(line: str) -> str:
    """Apply the comma-insertion rules to one source line.

    Tries each rewrite rule in turn. The first that matches wins. Lines
    that don't look like a list-bearing construct are passed through
    unchanged.

    Pattern lines and variation actions are beat-list contexts, so they
    enable ``allow_bare_suffix`` to expand tokens like ``and`` / ``e`` /
    ``&`` / ``a`` / ``trip`` / ``let`` to the most recently seen beat.
    Position→instrument lines list instruments, not beats, so bare suffix
    resolution is disabled there.
    """
    code, comment = _strip_trailing_comment(line)

    m = _PP_PATTERN_LINE_RE.match(code)
    if m:
        new_rhs = _group_list_items(m.group("rhs"), allow_bare_suffix=True)
        rewritten = f'{m.group("indent")}{m.group("lhs")}: {new_rhs}' if new_rhs else code
        return rewritten + comment

    m = _PP_POS_LINE_RE.match(code)
    if m:
        new_rhs = _group_list_items(m.group("rhs"), allow_bare_suffix=False)
        rewritten = f'{m.group("indent")}{m.group("lhs")}: {new_rhs}' if new_rhs else code
        return rewritten + comment

    m = _PP_VAR_ACTION_RE.match(code)
    if m:
        new_rhs = _group_list_items(m.group("rhs"), allow_bare_suffix=True)
        rewritten = f'{m.group("indent")}{m.group("prefix")}{new_rhs}' if new_rhs else code
        return rewritten + comment

    return line


_PP_COUNT_NOTES_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>count|notes):\s*(?P<value>\S.*?)\s*$"
)


def _quote_unquoted_count_notes(line: str) -> str:
    """Wrap the value of a bare ``count: <...>`` or ``notes: <...>`` line in
    double quotes so the grammar's ``ESCAPED_STRING`` terminal matches.

    Leaves already-quoted values alone. Matches only the standalone
    ``key: value`` shape — the block form ``count "label":`` has a space and
    a quote between ``count`` and ``:`` and is therefore not matched here.
    """
    code, comment = _strip_trailing_comment(line)
    m = _PP_COUNT_NOTES_RE.match(code)
    if not m:
        return line
    value = m.group("value")
    if value.startswith('"'):
        return line
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    rewritten = f'{m.group("indent")}{m.group("key")}: "{escaped}"'
    return rewritten + comment


_PP_BAR_LIST_RE = re.compile(
    r'^(?P<indent>\s*)'
    r'(?P<prefix>(?:variation(?:\s+"[^"]*")?\s+at\s+bars?\s+)'
    r'|(?:fill\s+"[^"]*"\s+at\s+bars?\s+)'
    r'|(?:fill\s+at\s+bars?\s+)'
    r'|(?:crash\s+in\s+at\s+))'
    r'(?P<rest>.*)$'
)


def _commafy_bar_list(line: str) -> str:
    """Insert commas between adjacent bar numbers after ``variation ... at bar(s)``,
    ``fill ... at bar(s)``, or ``crash in at`` so ``variation at bars 1 5:`` parses the
    same as ``variation at bars 1, 5:`` (and likewise for the others).

    Stops at the first non-INT token (``beat``, ``:``, end-of-line, ``*N``, etc.)
    so surrounding syntax is preserved.
    """
    code, comment = _strip_trailing_comment(line)
    match = _PP_BAR_LIST_RE.match(code)
    if not match:
        return line
    indent = match.group("indent")
    prefix = match.group("prefix")
    rest = match.group("rest")
    # Walk ``rest`` collecting INT tokens up to the first non-INT/non-comma.
    i = 0
    bar_tokens: list[str] = []
    while i < len(rest):
        c = rest[i]
        if c.isspace() or c == ",":
            i += 1
            continue
        if c.isdigit():
            j = i
            while j < len(rest) and rest[j].isdigit():
                j += 1
            bar_tokens.append(rest[i:j])
            i = j
            continue
        break
    if not bar_tokens:
        return line
    commafied = ", ".join(bar_tokens)
    remainder = rest[i:]
    if remainder and not remainder.startswith(" "):
        remainder = " " + remainder
    rewritten = f"{indent}{prefix}{commafied}{remainder}"
    return rewritten + comment


def _build_line_col_map(original: str, preprocessed: str) -> list[int]:
    """Map each preprocessed 1-indexed column to an original 1-indexed column.

    The preprocessors rewrite lines before Lark sees them (inserting commas,
    quoting count/notes values, expanding bare suffixes). Lark reports error
    columns in the preprocessed coordinate space, but those need to be
    translated back to the original source so diagnostics point at what the
    author wrote rather than at synthesized text.

    Returns a list of length ``len(preprocessed) + 2``. Index ``c`` (1 <= c
    <= len(preprocessed)) gives the best-guess original column for
    preprocessed column ``c``. For characters inserted by the preprocessor,
    the mapping falls through to the original column where the insertion
    occurred.
    """
    m = [0] * (len(preprocessed) + 2)
    matcher = SequenceMatcher(a=original, b=preprocessed, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                m[j1 + k + 1] = i1 + k + 1
        elif tag == "replace":
            span = max(i2 - i1, 1)
            for k in range(j2 - j1):
                orig_offset = min(k, span - 1)
                m[j1 + k + 1] = i1 + orig_offset + 1
        elif tag == "insert":
            for k in range(j2 - j1):
                m[j1 + k + 1] = i1 + 1
        # "delete" op: no preprocessed columns consumed.
    m[len(preprocessed) + 1] = len(original) + 1
    return m


def _preprocess_with_map(
    source: str,
) -> tuple[str, list[list[int] | None]]:
    """Run the line-rewriting preprocessors and also build a column map.

    Returns ``(preprocessed_text, col_maps)`` where ``col_maps[i]`` is the
    column map for line ``i`` (0-indexed) as described in
    :func:`_build_line_col_map`, or ``None`` if the line was not modified.
    Line numbers are preserved 1:1 between original and preprocessed source,
    so no line map is needed.
    """
    processed_lines: list[str] = []
    col_maps: list[list[int] | None] = []
    for raw_line in source.split("\n"):
        line = _quote_unquoted_count_notes(raw_line)
        line = _commafy_bar_list(line)
        line = _rewrite_rhs_list(line)
        processed_lines.append(line)
        col_maps.append(None if line == raw_line else _build_line_col_map(raw_line, line))
    return "\n".join(processed_lines), col_maps


def _remap_location(
    line: int | None,
    column: int | None,
    col_maps: list[list[int] | None],
) -> tuple[int | None, int | None]:
    """Translate a ``(line, column)`` from preprocessed to original coords."""
    if line is None or column is None:
        return line, column
    idx = line - 1
    if 0 <= idx < len(col_maps):
        m = col_maps[idx]
        if m is None:
            return line, column
        if 0 < column < len(m):
            return line, m[column]
    return line, column


def _preprocess_commas(source: str) -> str:
    """Insert optional commas in list contexts so Lark's LALR grammar sees
    a fully-commafied source. Also wraps unquoted ``count:`` / ``notes:``
    values in double quotes so the grammar's string terminal can match.
    """
    preprocessed, _ = _preprocess_with_map(source)
    return preprocessed
