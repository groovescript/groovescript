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
    "rb": "RB", "cb": "CB",
    "ft": "FT", "ht": "HT", "mt": "MT",
    "hf": "HF",
    "sp": "SP", "ch": "CH", "st": "ST", "cr2": "CR2",
    # Long-form aliases
    "bass": "BD", "kick": "BD",
    "snare": "SN",
    "click": "SCS", "cross-stick": "SCS",
    "hat": "HH", "hihat": "HH", "hi-hat": "HH",
    "openhat": "OH", "open": "OH",
    "ride": "RD",
    "crash": "CR",
    "ridebell": "RB", "bell": "RB",
    "cowbell": "CB",
    "floortom": "FT", "lowtom": "FT",
    "hightom": "HT", "hitom": "HT",
    "midtom": "MT",
    "hihatfoot": "HF", "hi-hat-foot": "HF", "footchick": "HF", "foot-chick": "HF",
    "splash": "SP",
    "china": "CH",
    "stack": "ST",
    "crash2": "CR2", "secondcrash": "CR2",
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


_TUPLET_RATIOS_NOTATION: dict[str, tuple[int, int]] = {
    "triplet": (3, 2),
    "quintuplet": (5, 4),
    "sextuplet": (6, 4),
    "septuplet": (7, 4),
    "nonuplet": (9, 8),
}


def _encode_tuplet_slot_label(
    anchor: str, slot: int, actual: int, normal: int
) -> str:
    """Encode a tuplet slot inside a count string as a synthetic label.

    Format: ``~T<anchor>_<slot>_<actual>_<normal>``. The leading ``~T`` is
    a sentinel so :func:`_beat_label_to_fraction` (and the bar-classifier
    in ``compiler.py``) can detect tuplet-slot labels without ambiguity.
    Whole-beat span only — half-beat tuplet groups inside count strings
    are not supported at this level.
    """
    return f"~T{anchor}_{slot}_{actual}_{normal}"


def _decode_tuplet_slot_label(
    label: str,
) -> tuple[str, int, int, int] | None:
    """Inverse of :func:`_encode_tuplet_slot_label`. Returns ``None`` for
    plain (non-tuplet) labels.
    """
    if not label.startswith("~T"):
        return None
    body = label[2:]
    parts = body.split("_")
    if len(parts) != 4:
        return None
    anchor, slot_s, actual_s, normal_s = parts
    try:
        return anchor, int(slot_s), int(actual_s), int(normal_s)
    except ValueError:
        return None


def _normalize_count_anchor(prefix: str, count_str: str) -> str:
    """Validate and canonicalise a count-string anchor prefix.

    Accepts ``"3"`` / ``"3&"`` / ``"3and"`` / ``"3trip"`` / etc. Returns the
    canonical short form (``"3"`` / ``"3&"`` / ``"3t"`` / …). Raises
    ``ValueError`` if the prefix isn't a valid beat label.
    """
    if not prefix:
        raise ValueError(
            f"Tuplet group has no anchor in count string: {count_str!r}"
        )
    if prefix.isdigit() and 1 <= int(prefix) <= 99:
        return prefix
    match = _POSITIONAL_BEAT_RE.match(prefix)
    if match is None:
        raise ValueError(
            f"Invalid tuplet anchor {prefix!r} in count string: {count_str!r}"
        )
    digits = match.group(1)
    suffix = match.group(2) or ""
    if suffix == "trip":
        return digits + "t"
    if suffix == "let":
        return digits + "l"
    if suffix == "and":
        return digits + "&"
    return digits + suffix


def _strip_anchor_to_digits(anchor: str) -> str:
    """Extract the digits-only part of an anchor for ``current_beat`` tracking."""
    match = _POSITIONAL_BEAT_RE.match(anchor)
    if match is None:
        return anchor
    return match.group(1)


def _parse_count_tuplet_group(
    raw: str,
) -> tuple[str, int, int, list[int]]:
    """Parse a ``{kind <slots>}`` token from a count string into
    ``(kind, actual, normal, slot_indices)``. The slot indices are
    1-based.

    Half-beat or quarter-beat ``/N`` qualifiers are not currently
    supported inside count strings — count slots are anchored on whole
    beats.
    """
    inner = raw[1:-1].strip()
    parts = [p for p in inner.replace(",", " ").split() if p]
    if not parts:
        raise ValueError(f"Empty tuplet group in count string: {raw!r}")
    kind_part = parts[0]
    if "/" in kind_part:
        raise ValueError(
            f"Half-beat tuplet ``{kind_part}`` is not supported inside count "
            f"strings; count-form anchors are restricted to whole beats. For "
            f"sub-beat tuplets, write the slots out as a pattern line — e.g. "
            f"``SN: 2&{{{kind_part} 1, 2, 3}}`` inside a ``count \"label\":`` "
            f"block."
        )
    if kind_part not in _TUPLET_RATIOS_NOTATION:
        raise ValueError(
            f"Unknown tuplet kind {kind_part!r} in count group {raw!r}"
        )
    actual, normal = _TUPLET_RATIOS_NOTATION[kind_part]
    slots: list[int] = []
    for slot_tok in parts[1:]:
        if not slot_tok.isdigit():
            raise ValueError(
                f"Non-integer slot {slot_tok!r} in count group {raw!r}"
            )
        slot = int(slot_tok)
        if slot < 1 or slot > actual:
            raise ValueError(
                f"Slot index {slot} out of range for {kind_part} "
                f"(must be 1..{actual}) in {raw!r}"
            )
        if slot in slots:
            raise ValueError(
                f"Slot {slot} listed more than once in {raw!r}"
            )
        slots.append(slot)
    if not slots:
        raise ValueError(f"Tuplet group {raw!r} has no slots")
    return kind_part, actual, normal, slots


def _expand_count_tuplet_group(
    raw: str, anchor: str, count_str: str
) -> list[str]:
    """Expand a count-string tuplet group into synthetic slot labels
    anchored at ``anchor``."""
    _, actual, normal, slots = _parse_count_tuplet_group(raw)
    return [
        _encode_tuplet_slot_label(anchor, slot, actual, normal)
        for slot in slots
    ]


def _extract_count_tuplet_groups(
    count_str: str,
) -> list[tuple[str, str, int, int, list[int]]]:
    """Pull every tuplet group from a count string.

    Returns a list of ``(anchor, kind, actual, normal, slot_indices)``
    tuples — one per occurrence. Used by the groove/fill compilers to
    build per-bar tuplet annotations from count+notes input.
    """
    out: list[tuple[str, str, int, int, list[int]]] = []
    tokens = _split_count_tokens_with_tuplets(count_str)
    current_beat: str | None = None
    for token in tokens:
        brace_open = token.find("{")
        if brace_open > 0 and token.endswith("}"):
            anchor_label = _normalize_count_anchor(token[:brace_open], count_str)
            current_beat = _strip_anchor_to_digits(anchor_label)
            kind, actual, normal, slots = _parse_count_tuplet_group(token[brace_open:])
            out.append((anchor_label, kind, actual, normal, slots))
            continue
        if token.startswith("{") and token.endswith("}"):
            if current_beat is None:
                raise ValueError(
                    f"Tuplet group {token!r} has no preceding beat number in: "
                    f"{count_str!r}"
                )
            kind, actual, normal, slots = _parse_count_tuplet_group(token)
            out.append((current_beat, kind, actual, normal, slots))
            continue
        if token.isdigit() and 1 <= int(token) <= 99:
            current_beat = token
        else:
            match = _POSITIONAL_BEAT_RE.match(token)
            if match:
                current_beat = match.group(1)
    return out


def _split_count_tokens_with_tuplets(count_str: str) -> list[str]:
    """Tokenise a count string while keeping ``{kind …}`` groups atomic.

    A brace group becomes a single token. When it's immediately preceded by
    a beat-number prefix (``2{sextuplet 1, 4}``), the prefix is captured in
    the same token so the parser treats the leading number as the tuplet's
    anchor — exactly like the pattern-line ``2{sextuplet …}`` form. Other
    runs split on whitespace and commas as usual.
    """
    out: list[str] = []
    i, n = 0, len(count_str)
    while i < n:
        c = count_str[i]
        if c.isspace() or c == ",":
            i += 1
            continue
        if c == "{":
            depth = 0
            j = i
            while j < n:
                if count_str[j] == "{":
                    depth += 1
                elif count_str[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            out.append(count_str[i:j])
            i = j
            continue
        j = i
        while j < n and not count_str[j].isspace() and count_str[j] != "," and count_str[j] != "{":
            j += 1
        token = count_str[i:j]
        i = j
        # If the token is a bare beat label and the *very next* non-space
        # character is ``{``, fuse the brace group onto this token so the
        # author's anchor binds explicitly.
        if token and (token.isdigit() or _POSITIONAL_BEAT_RE.match(token)):
            k = i
            while k < n and count_str[k].isspace():
                k += 1
            if k < n and count_str[k] == "{":
                depth = 0
                m = k
                while m < n:
                    if count_str[m] == "{":
                        depth += 1
                    elif count_str[m] == "}":
                        depth -= 1
                        if depth == 0:
                            m += 1
                            break
                    m += 1
                token = token + count_str[k:m]
                i = m
        if token:
            out.append(token)
    return out


def _parse_count_tokens(count_str: str) -> list[str]:
    """Convert a count string like '3 e & a 4' into beat labels.

    Supported tokens:
        - digits 1-99       : start a new beat (e.g. "3" → "3", "12" → "12")
        - e / & / a         : 16th-note suffixes of the current beat
        - and               : long-form alias for "&"
        - trip / let        : 8th-note triplet suffixes ("t"/"l")
        - 1e, 1and, 1trip…  : positional forms (also 10e, 12&, 11trip, …)
        - ``{kind 1, 2, …}``: tuplet group (whole-beat span). Each listed
          slot index becomes a synthetic label encoded by
          :func:`_encode_tuplet_slot_label`. The anchor is the most recent
          beat label seen before the group.

    Examples::
        "3 e & a 4"     → ["3", "3e", "3&", "3a", "4"]
        "1 & 2 & 3 & 4" → ["1", "1&", "2", "2&", "3", "3&", "4"]
        "1 and 2 and"   → ["1", "1&", "2", "2&"]
        "3 trip let 4"  → ["3", "3t", "3l", "4"]
        "1 1trip 1let"  → ["1", "1t", "1l"]
        "10 11 12"      → ["10", "11", "12"]
        "1 {sextuplet 1, 2, 3, 4, 5, 6} 3 4"
                       → ["1",
                          "~T1_1_6_4", "~T1_2_6_4", "~T1_3_6_4",
                          "~T1_4_6_4", "~T1_5_6_4", "~T1_6_6_4",
                          "3", "4"]

    The ``{kind …}`` group attaches to the most recently seen beat number,
    matching the way ``trip``/``let`` already attach. A group at the start
    of a count string with no preceding number raises ``ValueError``.
    """
    tokens = _split_count_tokens_with_tuplets(count_str)
    result: list[str] = []
    current_beat: str | None = None

    for token in tokens:
        # Fused anchor + brace group: ``2{sextuplet 1, 4}``. Strip the anchor
        # prefix and feed the brace group with that anchor.
        brace_open = token.find("{")
        if brace_open > 0 and token.endswith("}"):
            anchor_prefix = token[:brace_open]
            brace_part = token[brace_open:]
            anchor_label = _normalize_count_anchor(anchor_prefix, count_str)
            current_beat = _strip_anchor_to_digits(anchor_label)
            result.extend(
                _expand_count_tuplet_group(
                    brace_part, anchor=anchor_label, count_str=count_str
                )
            )
            continue
        if token.startswith("{") and token.endswith("}"):
            if current_beat is None:
                raise ValueError(
                    f"Tuplet group {token!r} has no preceding beat number in: "
                    f"{count_str!r}"
                )
            result.extend(
                _expand_count_tuplet_group(token, anchor=current_beat, count_str=count_str)
            )
            continue
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
                raise ValueError(f"Unrecognized count token {token!r} in: {count_str!r}")
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
            elif _is_grace_token(token):
                name, raw_inst = _split_grace_modifier(token)
                grace_inst = (
                    _normalize_instrument(raw_inst) if raw_inst is not None else None
                )
                for hit in current_group:
                    if name not in hit.modifiers:
                        hit.modifiers.append(name)
                    if grace_inst is not None:
                        if (
                            hit.grace_instrument is not None
                            and hit.grace_instrument != grace_inst
                        ):
                            raise ValueError(
                                f"conflicting grace instruments on {str(hit)!r}: "
                                f"{hit.grace_instrument!r} and {grace_inst!r}"
                            )
                        hit.grace_instrument = grace_inst
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
        sub_mods, buzz_dur, grace_inst = _extract_modifier_args(parts[1:])
        hits.append(
            InstrumentHit(
                inst,
                sub_mods if sub_mods else None,
                buzz_duration=buzz_dur,
                grace_instrument=grace_inst,
            )
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
        outer_mods, outer_buzz, outer_grace = _extract_modifier_args(outer_mods_raw)
        if outer_mods or outer_buzz is not None or outer_grace is not None:
            hits = [
                InstrumentHit(
                    str(h),
                    (list(h.modifiers) if h.modifiers else []) + outer_mods,
                    buzz_duration=outer_buzz if outer_buzz is not None else h.buzz_duration,
                    grace_instrument=outer_grace if outer_grace is not None else h.grace_instrument,
                )
                for h in hits
            ]
        return hits

    parts = spec.split()
    inst = _normalize_instrument(parts[0])
    mods, buzz_dur, grace_inst = _extract_modifier_args(parts[1:])
    return [
        InstrumentHit(
            inst,
            list(mods) if mods else None,
            buzz_duration=buzz_dur,
            grace_instrument=grace_inst,
        )
    ]


_MODIFIER_TOKENS: set[str] = {"ghost", "accent", "choke", "fermata", "flam", "drag", "double", "32nd"}

_MODIFIER_ALIASES: dict[str, str] = {"32nd": "double"}

# Valid buzz durations (note values). Dotted ("d") and double-dotted ("dd")
# variants of each are accepted as well — see ``_BUZZ_TOKEN_RE`` below.
_VALID_BUZZ_NOTE_VALUES: frozenset[int] = frozenset({1, 2, 4, 8, 16})

_BUZZ_TOKEN_RE = re.compile(r"^buzz(?::([1-9][0-9]?d{0,2}))?$")

# ``flam[:<inst>]`` / ``drag[:<inst>]`` — the optional ``:<inst>`` names the
# instrument the grace stroke(s) play on. The inner instrument name is
# validated downstream via ``_normalize_instrument``; the regex itself is
# permissive so unknown names produce a clean GrooveScriptError.
_GRACE_TOKEN_RE = re.compile(r"^(flam|drag)(?::([A-Za-z-]+))?$")


def _is_buzz_token(token: str) -> bool:
    """True if ``token`` is the bare ``buzz`` modifier or ``buzz:<duration>``."""
    return _BUZZ_TOKEN_RE.match(token) is not None


def _is_grace_token(token: str) -> bool:
    """True if ``token`` is ``flam``/``drag`` with or without a ``:<inst>`` suffix."""
    return _GRACE_TOKEN_RE.match(token) is not None


def _split_grace_modifier(token: str) -> tuple[str, str | None]:
    """Split ``flam`` / ``flam:SN`` / ``drag:HT`` into (modifier_name, raw_grace_inst).

    The raw grace-instrument string is returned unnormalised so the caller
    can produce its own diagnostic with the original spelling. Returns
    ``(modifier, None)`` for the bare ``flam``/``drag`` form.
    """
    match = _GRACE_TOKEN_RE.match(token)
    if match is None:
        raise ValueError(f"not a flam/drag token: {token!r}")
    return match.group(1), match.group(2)


def _is_modifier_token(token: str) -> bool:
    """True if ``token`` is a plain modifier, a buzz-roll modifier, or a
    flam/drag modifier with optional ``:<grace_instrument>`` suffix."""
    return (
        token in _MODIFIER_TOKENS
        or _is_buzz_token(token)
        or _is_grace_token(token)
    )


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
    if _is_grace_token(m):
        # Strip the optional ``:<inst>`` suffix; the grace instrument is
        # captured separately by ``_extract_modifier_args``.
        name, _ = _split_grace_modifier(m)
        return name
    return _MODIFIER_ALIASES.get(m, m)


def _extract_buzz_duration(raw_modifiers: list[str]) -> tuple[list[str], str | None]:
    """Pull the buzz duration out of a raw modifier token list.

    Returns ``(canonical_modifiers, buzz_duration_or_None)``. ``buzz`` tokens
    (with or without a duration suffix) are collapsed into a single ``"buzz"``
    entry in the canonical list; the duration string (default ``"4"``) is
    returned separately. A non-buzz token is normalized via
    ``_normalize_modifier``.

    Kept as a thin wrapper over ``_extract_modifier_args`` for callers that
    don't need the grace-instrument extraction.
    """
    canonical, buzz_duration, _ = _extract_modifier_args(raw_modifiers)
    return canonical, buzz_duration


def _extract_modifier_args(
    raw_modifiers: list[str],
) -> tuple[list[str], str | None, str | None]:
    """Pull buzz duration and grace instrument out of a raw modifier token list.

    Returns ``(canonical_modifiers, buzz_duration_or_None, grace_instrument_or_None)``.

    * ``buzz`` tokens (with or without ``:<duration>`` suffix) collapse into a
      single ``"buzz"`` entry; duration string returned separately (default
      ``"4"``).
    * ``flam``/``drag`` tokens (with or without ``:<inst>`` suffix) collapse to
      ``"flam"``/``"drag"``; the instrument string is normalised via
      ``_normalize_instrument`` and returned separately.
    * Other tokens pass through ``_normalize_modifier`` (e.g. ``32nd`` →
      ``double``).

    A flam/drag without a ``:<inst>`` suffix leaves ``grace_instrument`` as
    ``None`` (same-instrument flam — caller falls back to the main hit's
    instrument). Specifying both ``flam:X`` and ``flam:Y`` on the same hit
    raises ``ValueError``.
    """
    canonical: list[str] = []
    buzz_duration: str | None = None
    grace_instrument: str | None = None
    for raw in raw_modifiers:
        if _is_buzz_token(raw):
            _, dur = _split_buzz_modifier(raw)
            buzz_duration = dur
            if "buzz" not in canonical:
                canonical.append("buzz")
        elif _is_grace_token(raw):
            name, raw_inst = _split_grace_modifier(raw)
            if raw_inst is not None:
                normalised = _normalize_instrument(raw_inst)
                if grace_instrument is not None and grace_instrument != normalised:
                    raise ValueError(
                        f"conflicting grace instruments: "
                        f"{grace_instrument!r} and {normalised!r}"
                    )
                grace_instrument = normalised
            if name not in canonical:
                canonical.append(name)
        else:
            canonical.append(_normalize_modifier(raw))
    return canonical, buzz_duration, grace_instrument
