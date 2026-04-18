"""Drum-notation token parsing shared by the Lark transformer and the
count+notes preprocessor paths.

Covers instrument-name normalisation, beat-label normalisation, count-string
tokenisation, notes-string tokenisation (including parenthesised simultaneous
groups), modifier helpers (plain modifiers + ``buzz[:duration]``), and a
column-accurate diagnostic formatter for count/notes slot-count mismatches.
"""

import re

from .ast_nodes import InstrumentHit


# Instrument name aliases — maps lowercase alias → canonical abbreviation.
# Used both in the grammar transformer (for all notation contexts) and in the
# count+notes fill parser.
_INSTRUMENT_ALIASES: dict[str, str] = {
    # Canonical abbreviations (also accepted lowercase)
    "bd": "BD", "sn": "SN", "scs": "SCS",
    "hh": "HH", "oh": "OH", "rd": "RD", "cr": "CR",
    "ft": "FT", "ht": "HT", "mt": "MT",
    "hf": "HF",
    # Long-form aliases
    "bass": "BD", "kick": "BD",
    "snare": "SN",
    "click": "SCS", "cross-stick": "SCS",
    "hat": "HH", "hihat": "HH", "hi-hat": "HH",
    "openhat": "OH", "open": "OH",
    "ride": "RD",
    "crash": "CR",
    "floortom": "FT", "lowtom": "FT",
    "hightom": "HT", "hitom": "HT",
    "midtom": "MT",
    "hihatfoot": "HF", "hi-hat-foot": "HF", "footchick": "HF", "foot-chick": "HF",
}


def _normalize_instrument(name: str) -> str:
    """Normalise an instrument name or alias to its canonical abbreviation."""
    canon = _INSTRUMENT_ALIASES.get(name.lower())
    if canon is None:
        raise ValueError(f"Unknown instrument name: {name!r}")
    return canon


def _normalize_beat_label(label: str) -> str:
    """Normalize a beat label with verbose suffixes to its canonical short form.

    Verbose suffixes:
        - ``trip`` → ``t``   (e.g. ``3trip`` → ``3t``)
        - ``let``  → ``l``   (e.g. ``3let``  → ``3l``)
        - ``and``  → ``&``   (e.g. ``1and``  → ``1&``)
    """
    if len(label) > 4 and label.endswith("trip"):
        return label[:-4] + "t"
    if len(label) > 3 and label.endswith("let"):
        return label[:-3] + "l"
    if len(label) > 3 and label.endswith("and"):
        return label[:-3] + "&"
    return label


_POSITIONAL_BEAT_RE = re.compile(r"^([1-9][0-9]?)(trip|let|and|[e&atl])?$")


def _parse_count_tokens(count_str: str) -> list[str]:
    """Convert a count string like '3 e & a 4' into beat labels.

    Supported tokens:
        - digits 1-99       : start a new beat (e.g. "3" → "3", "12" → "12")
        - e / & / a         : 16th-note suffixes of the current beat
        - and               : long-form alias for "&"
        - trip / let        : 8th-note triplet suffixes ("t"/"l")
        - 1e, 1and, 1trip…  : positional forms (also 10e, 12&, 11trip, …)

    Examples::
        "3 e & a 4"     → ["3", "3e", "3&", "3a", "4"]
        "1 & 2 & 3 & 4" → ["1", "1&", "2", "2&", "3", "3&", "4"]
        "1 and 2 and"   → ["1", "1&", "2", "2&"]
        "3 trip let 4"  → ["3", "3t", "3l", "4"]
        "1 1trip 1let"  → ["1", "1t", "1l"]
        "10 11 12"      → ["10", "11", "12"]
    """
    tokens = count_str.split()
    result: list[str] = []
    current_beat: str | None = None

    for token in tokens:
        if token.isdigit() and 1 <= int(token) <= 99:
            current_beat = token
            result.append(token)
        elif token in ("e", "&", "a"):
            if current_beat is None:
                raise ValueError(
                    f"Count suffix {token!r} has no preceding beat number in: {count_str!r}"
                )
            result.append(current_beat + token)
        elif token == "and":
            if current_beat is None:
                raise ValueError(
                    f"Count suffix 'and' has no preceding beat number in: {count_str!r}"
                )
            result.append(current_beat + "&")
        elif token == "trip":
            if current_beat is None:
                raise ValueError(
                    f"Count suffix 'trip' has no preceding beat number in: {count_str!r}"
                )
            result.append(current_beat + "t")
        elif token == "let":
            if current_beat is None:
                raise ValueError(
                    f"Count suffix 'let' has no preceding beat number in: {count_str!r}"
                )
            result.append(current_beat + "l")
        else:
            # Positional forms: 1e, 1and, 1trip, 12&, 10trip, etc.
            match = _POSITIONAL_BEAT_RE.match(token)
            if not match:
                raise ValueError(f"Unrecognised count token {token!r} in: {count_str!r}")
            digits = match.group(1)
            suffix = match.group(2) or ""
            current_beat = digits
            if suffix == "trip":
                result.append(digits + "t")
            elif suffix == "let":
                result.append(digits + "l")
            elif suffix == "and":
                result.append(digits + "&")
            elif suffix:
                # 1e, 1&, 1a, 1t, 1l (or 12e, 12&, …)
                result.append(digits + suffix)
            else:
                # Plain digit — handled by the isdigit() branch above, but
                # a lone "10" also reaches here when the guard is isdigit().
                result.append(digits)

    return result


def _count_token_columns(count_str: str) -> list[int]:
    """Return the 0-indexed start column of each slot emitted by
    :func:`_parse_count_tokens` for ``count_str``.

    Every whitespace/comma-separated token in ``count_str`` corresponds to
    exactly one slot (a digit starts a new beat, a suffix token attaches a
    subdivision to the current beat), so this is a straight tokenize-with-
    positions pass. Keeping it in sync with ``_parse_count_tokens`` is cheap
    because the tokenisation rules are identical.
    """
    cols: list[int] = []
    i, n = 0, len(count_str)
    while i < n:
        while i < n and (count_str[i].isspace() or count_str[i] == ","):
            i += 1
        if i >= n:
            break
        cols.append(i)
        while i < n and not count_str[i].isspace() and count_str[i] != ",":
            i += 1
    return cols


def _notes_slot_columns(notes_str: str) -> list[int]:
    """Return the 0-indexed start column of each slot in ``notes_str``.

    Mirrors the tokenisation used by :func:`_parse_notes_tokens`: a slot is
    started by an instrument name or a parenthesised simultaneous group,
    and trailing modifier tokens (``ghost``, ``accent``, ``flam``, ``drag``,
    ``double``, ``32nd``, ``buzz[:N]``) attach to the preceding slot
    without producing a new one.
    """
    cols: list[int] = []
    i, n = 0, len(notes_str)
    while i < n:
        while i < n and (notes_str[i].isspace() or notes_str[i] == ","):
            i += 1
        if i >= n:
            break
        start = i
        if notes_str[i] == "(":
            depth = 0
            while i < n:
                if notes_str[i] == "(":
                    depth += 1
                elif notes_str[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            cols.append(start)
            continue
        while i < n and not notes_str[i].isspace() and notes_str[i] not in ",()":
            i += 1
        token = notes_str[start:i]
        if cols and _is_modifier_token(token):
            continue
        cols.append(start)
    return cols


def _format_count_notes_mismatch(
    context: str, count_str: str, notes_str: str
) -> str:
    """Build a column-aligned diagnostic for a count+notes slot-count mismatch.

    ``context`` is a short phrase identifying where the mismatch was found
    (``"fill block"``, ``"groove body"``, ``"variation substitute"``); it
    prefixes the first line so the user can see which construct triggered
    the error. The body of the message shows both strings stacked with a
    caret under the first orphan slot.
    """
    count_labels = _parse_count_tokens(count_str)
    note_groups = _parse_notes_tokens(notes_str)
    n, m = len(count_labels), len(note_groups)

    count_cols = _count_token_columns(count_str)
    note_cols = _notes_slot_columns(notes_str)

    header = (
        f"{context}: count has {n} slot(s) but notes has {m} slot(s)"
    )
    count_prefix = "   count: "
    notes_prefix = "   notes: "
    lines = [header, f"{count_prefix}{count_str}", f"{notes_prefix}{notes_str}"]

    # Underline the first orphan slot — i.e. the first slot on whichever
    # side has extra tokens — so the author can see exactly where the
    # alignment breaks.
    if n > m and m < len(count_cols):
        caret_col = len(count_prefix) + count_cols[m]
        lines.append(" " * caret_col + "^ this count slot has no matching note")
    elif m > n and n < len(note_cols):
        caret_col = len(notes_prefix) + note_cols[n]
        lines.append(" " * caret_col + "^ this note has no matching count slot")
    return "\n".join(lines)


def _parse_notes_tokens(notes_str: str) -> list[list[InstrumentHit]]:
    """Parse a notes string into a list of instrument groups.

    Each element is a list of ``InstrumentHit`` objects representing
    simultaneous hits at that beat position.

    Accepts a unified grammar: a sequence of hit specs, where each spec is
    either a bare instrument name or a parenthesised simultaneous group
    ``(a b)`` / ``(a, b)`` — both comma- and whitespace-separated group
    syntaxes are accepted. Each hit spec may be followed by trailing
    modifiers (``ghost``, ``accent``, ``flam``, ``drag``) which attach to
    every instrument in the most recently seen hit. Hit specs may be
    separated by commas or by whitespace::

        "snare, bass accent, (snare, crash) flam"
            → [[SN], [BD accent], [SN flam, CR flam]]
        "(crash bass) accent, snare"
            → [[CR accent, BD accent], [SN]]
        "SN SN SN SN"          → [[SN], [SN], [SN], [SN]]
        "snare (bass crash)"   → [[SN], [BD, CR]]
    """
    s = notes_str.strip()
    if not s:
        return []

    groups: list[list[InstrumentHit]] = []
    current_group: list[InstrumentHit] | None = None
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace() or c == ",":
            i += 1
            continue

        if c == "(":
            j = s.index(")", i)
            inner = s[i + 1 : j]
            # Finish any previous group before starting a new paren group.
            if current_group is not None:
                groups.append(current_group)
            current_group = _parse_paren_group_instruments(inner)
            i = j + 1
            continue

        # Read an identifier token (instrument or modifier) up to whitespace,
        # comma, or '('.
        j = i
        while j < len(s) and not s[j].isspace() and s[j] not in ",()":
            j += 1
        token = s[i:j]
        i = j
        if not token:
            continue

        if _is_modifier_token(token):
            if current_group is None:
                raise ValueError(
                    f"Modifier {token!r} before any instrument in notes: {notes_str!r}"
                )
            # Attach this modifier to every instrument in the current group.
            if _is_buzz_token(token):
                _, dur = _split_buzz_modifier(token)
                for hit in current_group:
                    if "buzz" not in hit.modifiers:
                        hit.modifiers.append("buzz")
                    hit.buzz_duration = dur
            else:
                norm_token = _normalize_modifier(token)
                for hit in current_group:
                    hit.modifiers.append(norm_token)
            continue

        # Instrument token → finish the current group, start a new one.
        if current_group is not None:
            groups.append(current_group)
        current_group = [InstrumentHit(_normalize_instrument(token))]

    if current_group is not None:
        groups.append(current_group)
    return groups


def _parse_paren_group_instruments(inner: str) -> list[InstrumentHit]:
    """Parse the inside of a ``(...)`` simultaneous group.

    Accepts either comma-delimited or whitespace-delimited instrument lists,
    each item optionally followed by trailing modifiers that attach to that
    instrument only::

        "bass, crash"           → [BD, CR]
        "bass crash"            → [BD, CR]
        "snare accent, bass"    → [SN accent, BD]
        "snare accent bass"     → [SN accent, BD]
    """
    if "," in inner:
        subs = [s.strip() for s in inner.split(",") if s.strip()]
    else:
        tokens = inner.split()
        subs = []
        current: list[str] = []
        for tok in tokens:
            if _is_modifier_token(tok):
                if not current:
                    raise ValueError(
                        f"Modifier {tok!r} before any instrument in group: {inner!r}"
                    )
                current.append(tok)
            else:
                if current:
                    subs.append(" ".join(current))
                current = [tok]
        if current:
            subs.append(" ".join(current))
    hits: list[InstrumentHit] = []
    for sub in subs:
        parts = sub.split()
        inst = _normalize_instrument(parts[0])
        sub_mods, buzz_dur = _extract_buzz_duration(parts[1:])
        hits.append(
            InstrumentHit(inst, sub_mods if sub_mods else None, buzz_duration=buzz_dur)
        )
    return hits


def _parse_hit_spec(spec: str) -> list[InstrumentHit]:
    """Parse a single comma-delimited hit spec.

    A spec is either a parenthesised simultaneous group followed by optional
    modifiers that apply to all notes in the group, or a single instrument
    name followed by optional modifiers::

        "snare"                → [SN]
        "bass accent"          → [BD accent]
        "(bass, crash)"        → [BD, CR]
        "(bass crash)"         → [BD, CR]
        "(snare, crash) flam"  → [SN flam, CR flam]
        "(snare crash) flam"   → [SN flam, CR flam]
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("Empty hit spec in notes string")

    if spec.startswith("("):
        end = spec.rindex(")")
        inner = spec[1:end]
        trailing = spec[end + 1 :].split()
        outer_mods_raw = list(trailing)
        hits = _parse_paren_group_instruments(inner)
        outer_mods, outer_buzz = _extract_buzz_duration(outer_mods_raw)
        if outer_mods or outer_buzz is not None:
            hits = [
                InstrumentHit(
                    str(h),
                    (list(h.modifiers) if h.modifiers else []) + outer_mods,
                    buzz_duration=outer_buzz if outer_buzz is not None else h.buzz_duration,
                )
                for h in hits
            ]
        return hits

    parts = spec.split()
    inst = _normalize_instrument(parts[0])
    mods, buzz_dur = _extract_buzz_duration(parts[1:])
    return [InstrumentHit(inst, list(mods) if mods else None, buzz_duration=buzz_dur)]


_MODIFIER_TOKENS: set[str] = {"ghost", "accent", "flam", "drag", "double", "32nd"}

_MODIFIER_ALIASES: dict[str, str] = {"32nd": "double"}

# Valid buzz durations (note values). Dotted ("d") and double-dotted ("dd")
# variants of each are accepted as well — see ``_BUZZ_TOKEN_RE`` below.
_VALID_BUZZ_NOTE_VALUES: frozenset[int] = frozenset({1, 2, 4, 8, 16})

_BUZZ_TOKEN_RE = re.compile(r"^buzz(?::([1-9][0-9]?d{0,2}))?$")


def _is_buzz_token(token: str) -> bool:
    """True if ``token`` is the bare ``buzz`` modifier or ``buzz:<duration>``."""
    return _BUZZ_TOKEN_RE.match(token) is not None


def _is_modifier_token(token: str) -> bool:
    """True if ``token`` is a plain modifier or a buzz-roll modifier."""
    return token in _MODIFIER_TOKENS or _is_buzz_token(token)


def _split_buzz_modifier(token: str) -> tuple[str, str | None]:
    """Split a ``buzz`` / ``buzz:<duration>`` token into ("buzz", duration).

    Returns ``("buzz", "4")`` for a bare ``buzz`` (quarter-note default).
    """
    match = _BUZZ_TOKEN_RE.match(token)
    if match is None:
        raise ValueError(f"not a buzz token: {token!r}")
    return "buzz", match.group(1) or "4"


def _normalize_modifier(m: str) -> str:
    """Normalize a modifier token to its canonical form (e.g. '32nd' → 'double')."""
    if _is_buzz_token(m):
        return "buzz"
    return _MODIFIER_ALIASES.get(m, m)


def _extract_buzz_duration(raw_modifiers: list[str]) -> tuple[list[str], str | None]:
    """Pull the buzz duration out of a raw modifier token list.

    Returns ``(canonical_modifiers, buzz_duration_or_None)``. ``buzz`` tokens
    (with or without a duration suffix) are collapsed into a single ``"buzz"``
    entry in the canonical list; the duration string (default ``"4"``) is
    returned separately. A non-buzz token is normalised via
    ``_normalize_modifier``.
    """
    canonical: list[str] = []
    buzz_duration: str | None = None
    for raw in raw_modifiers:
        if _is_buzz_token(raw):
            _, dur = _split_buzz_modifier(raw)
            buzz_duration = dur
            if "buzz" not in canonical:
                canonical.append("buzz")
        else:
            canonical.append(_normalize_modifier(raw))
    return canonical, buzz_duration
