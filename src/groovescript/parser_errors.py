"""Translate Lark parse exceptions into :class:`GrooveScriptError` diagnostics.

Lark reports errors against the *preprocessed* source; :func:`_translate_lark_error`
converts the token text and pointers back to the original coordinate space using
the column maps built by the preprocessors, and attaches a hint when one of the
``_hint_for_*`` helpers can produce one.
"""

from lark.exceptions import (
    UnexpectedCharacters,
    UnexpectedEOF,
    UnexpectedInput,
    UnexpectedToken,
)

from .errors import (
    GrooveScriptError,
    suggest_from_choices,
    suggest_instrument,
    suggest_modifier,
)
from .parser_preprocess import _remap_location

# ── Friendly-error translation ───────────────────────────────────────────
#
# ``parse()`` catches Lark's low-level exceptions and re-raises them as
# :class:`GrooveScriptError` with a source excerpt and, where possible, a
# hint explaining how to fix the problem. Keeping this logic next to the
# parser lets us reuse the preprocessed source text when computing hints
# (e.g. looking at the offending token under the caret).


_KEYWORD_CANDIDATES: list[str] = [
    "title", "tempo", "time_signature", "dsl_version",
    "metadata", "groove", "section", "fill", "bar", "bars", "beat", "at",
    "count", "notes", "repeat", "like", "except", "extend",
    "variation", "add", "remove", "replace", "with", "placeholder",
    "cue", "play", "rest", "text",
]


def _literal_patterns_for_terminals(
    exc: UnexpectedInput, names: set[str], identifiers_only: bool = True
) -> list[str]:
    """Return the string literals (e.g. 'subdivision') for the given terminal names.

    When ``identifiers_only`` is true (the default, used for spelling
    suggestions), punctuation literals like ``:`` and ``,`` are excluded.
    Callers that want to display *any* literal — including punctuation —
    should pass ``identifiers_only=False``.
    """
    d = getattr(exc, "_terminals_by_name", None) or {}
    literals: list[str] = []
    for name in names:
        term = d.get(name)
        if term is None:
            continue
        pattern = getattr(term, "pattern", None)
        value = getattr(pattern, "value", None)
        if not isinstance(value, str):
            continue
        if identifiers_only and not value.isidentifier():
            continue
        literals.append(value)
    return literals


# Terminal names that represent content tokens for which we can produce a
# human-friendly "expected a <thing>" hint when they show up in an expected
# set. Mapping order matters: the first match wins.
_CONTENT_TERMINAL_DESCRIPTIONS: list[tuple[str, str]] = [
    ("INSTRUMENT", "an instrument name"),
    ("BEAT_LABEL", "a beat number (like '1', '2&', '3e')"),
    ("INT", "an integer"),
    ("ESCAPED_STRING", "a double-quoted string"),
    ("TIME_SIGNATURE", "a time signature like '4/4'"),
    ("MODIFIER", "a modifier (ghost, accent, flam, drag, double)"),
]


def _describe_expected_content(allowed: set[str]) -> str | None:
    """Describe expected content terminals in plain English."""
    parts = [desc for name, desc in _CONTENT_TERMINAL_DESCRIPTIONS if name in allowed]
    if not parts:
        return None
    if len(parts) == 1:
        return "expected " + parts[0]
    return "expected " + ", ".join(parts[:-1]) + " or " + parts[-1]


def _hint_for_unexpected_characters(
    exc: UnexpectedCharacters, source: str
) -> tuple[str, int, int] | None:
    """Return ``(hint, underline_length, column_offset)`` for an UnexpectedCharacters error.

    ``column_offset`` is how many columns *before* the raw error position the
    caret should be moved, so that e.g. a lex error mid-word underlines the
    full word the user typed (``snars``) rather than the first bad character
    (``a``).
    """
    pos = exc.pos_in_stream or 0
    end = pos
    while end < len(source) and (source[end].isalnum() or source[end] in "_-"):
        end += 1
    token = source[pos:end]

    # If the previous token ended right where we're erroring, the user
    # probably typed one long identifier that the lexer split. Look back
    # through token_history for an adjacent INSTRUMENT or keyword-like
    # token so we can offer a spelling correction against the combined
    # word.
    history = list(getattr(exc, "token_history", None) or [])
    prev_combined: tuple[str, int] | None = None  # (text, start_pos)
    if token and history:
        prev = history[-1]
        prev_end_pos = getattr(prev, "end_pos", None)
        if prev_end_pos is not None and prev_end_pos == pos and str(prev).isalnum():
            prev_combined = (str(prev) + token, prev_end_pos - len(str(prev)))

    allowed = set(exc.allowed or [])
    hints: list[str] = []
    underline = max(end - pos, 1)
    col_offset = 0

    # Case A: adjacent previous-token + current word suggest something the
    # lexer split at the longest prefix it recognised. Try:
    #   * misspelled instrument (prev was INSTRUMENT)
    #   * misspelled keyword (prev was any keyword-ish terminal whose value
    #     starts the combined text)
    if prev_combined is not None:
        combined, combined_start = prev_combined
        prev_tok = history[-1]
        prev_type = getattr(prev_tok, "type", None)
        if prev_type == "INSTRUMENT":
            suggestion = suggest_instrument(combined)
            if suggestion:
                hints.append(
                    f"unknown instrument '{combined}' — did you mean '{suggestion}'?"
                )
                underline = len(combined)
                col_offset = pos - combined_start
        if not hints:
            suggestion = suggest_from_choices(combined, _KEYWORD_CANDIDATES)
            if suggestion and suggestion != combined:
                hints.append(f"did you mean '{suggestion}'?")
                underline = len(combined)
                col_offset = pos - combined_start

    if not hints and token:
        # Spell-check against expected keyword literals.
        literals = _literal_patterns_for_terminals(exc, allowed)
        if literals:
            suggestion = suggest_from_choices(token, literals)
            if suggestion:
                hints.append(f"did you mean '{suggestion}'?")

        # If the parser was expecting an INSTRUMENT, try the known aliases.
        if "INSTRUMENT" in allowed and not hints:
            suggestion = suggest_instrument(token)
            if suggestion:
                hints.append(f"unknown instrument '{token}' — did you mean '{suggestion}'?")

        # Modifier suggestion when BEAT_LABEL or MODIFIER is expected and
        # the offending word is alphabetic — a typo'd modifier like
        # 'accnt' looks like a bare beat label to the parser.
        if not hints and token.isalpha():
            mod_suggestion = suggest_modifier(token)
            if mod_suggestion and (
                "MODIFIER" in allowed or "BEAT_LABEL" in allowed
            ):
                hints.append(
                    f"unknown modifier '{token}' — did you mean '{mod_suggestion}'?"
                )

        # BEAT_LABEL expected but got a non-digit token.
        if "BEAT_LABEL" in allowed and not hints and not token[:1].isdigit():
            hints.append("expected a beat number like '1', '2&', or '3e'")

    if not hints:
        # Fallback: describe expected content terminals, and/or list the
        # expected literal patterns. In the fallback we include all string
        # literals, including punctuation like ':' and ',' so errors about
        # missing separators produce useful hints.
        content_desc = _describe_expected_content(allowed)
        literals = _literal_patterns_for_terminals(exc, allowed, identifiers_only=False)
        literals_sorted = sorted(set(literals))
        parts: list[str] = []
        if content_desc:
            parts.append(content_desc)
        if literals_sorted:
            kw = ", ".join(f"'{k}'" for k in literals_sorted)
            if parts:
                parts.append(f"or keyword: {kw}")
            else:
                if len(literals_sorted) == 1:
                    parts.append(f"expected '{literals_sorted[0]}'")
                else:
                    parts.append(f"expected one of: {kw}")
        if parts:
            hints.append(" ".join(parts))

    if not hints:
        return None
    return hints[0], underline, col_offset


def _hint_for_unexpected_token(exc: UnexpectedToken) -> str | None:
    """Return a hint string for an UnexpectedToken error, or ``None``."""
    expected = set(exc.expected or set())
    token = exc.token
    tok_value = str(token) if token is not None else ""
    tok_type = getattr(token, "type", None)

    # Case 1: parser expected a keyword — suggest close match against the
    # actual token text.
    literals = _literal_patterns_for_terminals(exc, expected)
    if literals and tok_value:
        suggestion = suggest_from_choices(tok_value, literals)
        if suggestion:
            return f"did you mean '{suggestion}'?"

    # Case 2: parser got an identifier where an instrument was expected.
    if "INSTRUMENT" in expected and tok_value:
        suggestion = suggest_instrument(tok_value)
        if suggestion:
            return f"unknown instrument '{tok_value}' — did you mean '{suggestion}'?"

    # Case 3: the token is a recognised instrument but the grammar expected
    # a specific keyword at this point. Suggest a close keyword match.
    if tok_type == "INSTRUMENT" and tok_value:
        suggestion = suggest_from_choices(tok_value, _KEYWORD_CANDIDATES)
        if suggestion and suggestion != tok_value:
            return f"did you mean '{suggestion}'?"

    # Case 4: $END (EOF) or hit a newline — indicate the expected next token.
    content_desc = _describe_expected_content(expected)
    literals_all = _literal_patterns_for_terminals(exc, expected, identifiers_only=False)
    literals_sorted = sorted(set(literals_all))
    parts: list[str] = []
    if content_desc:
        parts.append(content_desc)
    if literals_sorted:
        kw = ", ".join(f"'{k}'" for k in literals_sorted)
        if parts:
            parts.append(f"or keyword: {kw}")
        else:
            if len(literals_sorted) == 1:
                parts.append(f"expected '{literals_sorted[0]}'")
            else:
                parts.append(f"expected one of: {kw}")
    return " ".join(parts) or None


def _translate_lark_error(
    exc: UnexpectedInput,
    preprocessed: str,
    original: str,
    col_maps: list[list[int] | None],
    filename: str | None,
) -> GrooveScriptError:
    """Convert a Lark parse exception into a :class:`GrooveScriptError`.

    Lark reports line/column against the *preprocessed* source, so token text
    and positional lookups use ``preprocessed``. The resulting error, however,
    stores ``original`` as its ``source`` and remaps line/column back to the
    original coordinate space so diagnostics point at what the author wrote.
    """
    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)

    if isinstance(exc, UnexpectedCharacters):
        result = _hint_for_unexpected_characters(exc, preprocessed)
        if result:
            hint, length, col_offset = result
        else:
            hint, length, col_offset = None, 1, 0
        if column is not None and col_offset:
            column = column - col_offset
        pos = (exc.pos_in_stream or 0) - col_offset
        if length == 1 and 0 <= pos < len(preprocessed):
            bad_char = preprocessed[pos]
            if bad_char == "\n":
                message = "unexpected end of line"
            else:
                message = f"unexpected character {bad_char!r}"
        else:
            token = preprocessed[pos : pos + length]
            message = f"unexpected token {token!r}"
        line, column = _remap_location(line, column, col_maps)
        return GrooveScriptError(
            message=message,
            filename=filename,
            source=original,
            line=line,
            column=column,
            length=length,
            hint=hint,
        )

    if isinstance(exc, UnexpectedToken):
        hint = _hint_for_unexpected_token(exc)
        tok = exc.token
        tok_text = str(tok) if tok is not None else ""
        length = max(len(tok_text), 1) if tok_text else 1
        if tok_text:
            message = f"unexpected {tok_text!r}"
        else:
            message = "unexpected input"
        line, column = _remap_location(line, column, col_maps)
        return GrooveScriptError(
            message=message,
            filename=filename,
            source=original,
            line=line,
            column=column,
            length=length,
            hint=hint,
        )

    if isinstance(exc, UnexpectedEOF):
        literals = _literal_patterns_for_terminals(exc, set(exc.expected or []))
        if literals:
            literals_sorted = sorted(set(literals))
            hint = "expected " + ", ".join(f"'{k}'" for k in literals_sorted)
        else:
            hint = None
        # UnexpectedEOF doesn't carry line/column: point at the last line.
        # Line counts are preserved by the preprocessor, so we can use the
        # original source directly.
        src_lines = original.splitlines() or [""]
        eof_line = len(src_lines)
        eof_col = len(src_lines[-1]) + 1
        return GrooveScriptError(
            message="unexpected end of file",
            filename=filename,
            source=original,
            line=eof_line,
            column=eof_col,
            length=1,
            hint=hint,
        )

    return GrooveScriptError(
        message=str(exc),
        filename=filename,
        source=original,
    )


def _location_from_tree(obj) -> tuple[int | None, int | None]:
    """Pull (line, column) from a Lark Tree's propagated metadata, if any."""
    meta = getattr(obj, "meta", None)
    if meta is None:
        return None, None
    line = getattr(meta, "line", None) if not getattr(meta, "empty", False) else None
    column = getattr(meta, "column", None) if not getattr(meta, "empty", False) else None
    return line, column
