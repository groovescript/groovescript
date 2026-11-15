"""``groovescript fmt``: canonical layout for ``.gs`` files.

The grammar ignores whitespace, so layout carries no meaning and the
formatter is free to rewrite it. It works line by line, keeping every
comment and every token, and changes only:

- indentation: two spaces per nesting level, where nesting comes from the
  parse tree (groove / fill / section / ``bar N:`` / ``play:`` /
  ``variation ... :`` / ``lyrics:`` / inline fill and groove bodies), not
  from the old indentation (statements are one per line: the line-based
  preprocessors reject a statement split across lines). A comment takes
  the indentation of the code below it.
- spacing inside a line: single spaces between tokens, none before ``,``
  or ``:``, one after them (``flam:SN``-style modifier suffixes are left
  joined), none inside tuplet braces. Strings and comments are untouched,
  as is the author's choice of commas versus spaces in beat lists.
- alignment: in a run of consecutive ``instrument: beats`` or
  ``beat: instruments`` lines, the values start in one column.
- blank lines: at most one in a row, one before each top-level block
  (above any comment attached to it), none at the start or end.

Safety net: the formatted text must compile to exactly the same LilyPond,
MIDI and MusicXML as the input, or :func:`format_source` raises instead of
returning it. Only charts that compile can be formatted.
"""

from __future__ import annotations

import re

from lark import Tree

from .compiler import compile_groove, compile_song
from .errors import GrooveScriptError
from .lilypond import emit_lilypond
from .midi import emit_midi
from .musicxml import emit_musicxml
from .parser import parse
from .parser_preprocess import _preprocess_with_map
from .parser_transformer import _parser

INDENT = "  "

# Rules whose header line opens a block: lines after the header, up to the
# rule's last line, sit one level deeper.
_BLOCK_RULES = frozenset({
    "metadata_block",
    "groove_def",
    "fill_def",
    "fill_def_bare",
    "fill_def_extend_bare",
    "section_def",
    "variation_def",
    "pattern_bar",
    "fill_count_block",
    "fill_bar_numbered",
    "play_block",
    "play_groove_named_inline",
    "play_groove_inline",
    "play_bar",
    "section_variation_block",
    "extend_variation_block",
    "section_lyrics_block",
    "section_fill_line",
    "section_inline_fill_bare",
    "groove_line",
})

# Top-level statements that get a blank line above them.
_TOP_LEVEL_BLOCKS = frozenset({
    "metadata_block",
    "groove_def",
    "groove_placeholder_def",
    "fill_def",
    "fill_def_bare",
    "fill_def_extend_bare",
    "section_def",
    "variation_def",
})

# Modifiers whose ``:<suffix>`` is part of the token (``flam:SN``, ``buzz:8``).
_JOINED_COLON_WORDS = ("flam", "drag", "buzz")

# A pattern line whose value column can be aligned: ``KEY: value`` where KEY
# is a single word (instrument or beat label) and value is non-empty.
_ALIGNABLE_RE = re.compile(r"^(?P<key>[A-Za-z0-9&-]+):(?P<rest> \S.*)$")
# Keywords that also take ``word: value`` form but are not pattern lines.
_NOT_PATTERN_KEYS = frozenset({
    "title", "tempo", "time_signature", "dsl_version", "default_groove",
    "default_bars", "feel", "lyrics_style", "bars", "groove", "repeat",
    "extend", "count", "notes", "text", "like", "play", "metadata", "lyrics",
})


class FormatError(GrooveScriptError):
    """The formatter could not produce a safe result."""


def format_source(source: str) -> str:
    """Return ``source`` in canonical layout.

    Raises:
        GrooveScriptError: if ``source`` does not parse or compile (the
            formatter only handles valid charts), or if formatting would
            change the compiled output (a formatter bug; nothing is lost).
    """
    reference = _compiled_outputs(source)
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    depth, top_level_starts = _structure(lines)

    out: list[str] = []
    code_depths: list[int | None] = []  # per output line; None = blank/comment
    for number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            out.append("")
            code_depths.append(None)
            continue
        code, comment = _split_comment(stripped)
        if not code:
            out.append(stripped)  # indented later from the code below
            code_depths.append(None)
            continue
        level = depth.get(number, 0)
        text = _respace(code)
        if comment:
            gap = _original_gap(raw)
            text = f"{text}{gap}{comment}"
        out.append(INDENT * level + text)
        code_depths.append(level)

    _indent_comments(out, code_depths)
    _align_pattern_runs(out, code_depths)
    out = _normalise_blank_lines(out, top_level_starts)
    result = "\n".join(out).rstrip("\n") + "\n"

    if _compiled_outputs(result) != reference:
        raise FormatError(
            message="formatting would change the compiled chart, so the file was left as is",
            hint="this is a groovescript bug; please report it with the file",
        )
    return result


# ── Structure from the parse tree ────────────────────────────────────────────

def _structure(lines: list[str]) -> tuple[dict[int, int], set[int]]:
    """Nesting depth per 1-indexed line, and the header lines of top-level
    blocks. Uses the raw Lark tree of the preprocessed text, whose line
    numbers match the source 1:1."""
    preprocessed, _ = _preprocess_with_map("\n".join(lines))
    tree = _parser.parse(preprocessed)
    depth: dict[int, int] = {}
    top_level: set[int] = set()
    for child in tree.children:
        if isinstance(child, Tree) and child.data in _TOP_LEVEL_BLOCKS:
            top_level.add(child.meta.line)
    for node in tree.iter_subtrees():
        if node.data not in _BLOCK_RULES or node.meta.empty:
            continue
        if node.data == "play_bar" and not _has_child(node, "play_bar_body"):
            continue
        if node.data == "groove_line" and not _has_child(node, "groove_body"):
            continue
        for line in range(node.meta.line + 1, node.meta.end_line + 1):
            depth[line] = depth.get(line, 0) + 1
    return depth, top_level


def _has_child(node: Tree, name: str) -> bool:
    return any(isinstance(c, Tree) and c.data == name for c in node.children)


# ── Within-line spacing ──────────────────────────────────────────────────────

def _split_comment(line: str) -> tuple[str, str]:
    """Split ``line`` into (code, comment) at the first ``#`` or ``//``
    outside a string. Both parts are stripped."""
    in_string = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "#" or line.startswith("//", i):
            return line[:i].rstrip(), line[i:].rstrip()
        i += 1
    return line.rstrip(), ""


def _original_gap(raw: str) -> str:
    """Whitespace between the code and its trailing comment in ``raw``,
    kept so hand-aligned comment columns survive (at least one space)."""
    code, comment = _split_comment(raw.strip())
    stripped = raw.strip()
    start = stripped.find(comment, len(code))
    gap = stripped[len(code):start]
    return gap if gap.strip() == "" and gap else " "


def _respace(code: str) -> str:
    """Normalise spacing in a comment-free code fragment, leaving strings
    exactly as written."""
    parts: list[str] = []  # alternating code / string chunks
    buf = ""
    in_string = False
    i = 0
    while i < len(code):
        ch = code[i]
        if in_string:
            buf += ch
            if ch == "\\" and i + 1 < len(code):
                buf += code[i + 1]
                i += 2
                continue
            if ch == '"':
                parts.append(buf)
                buf = ""
                in_string = False
        elif ch == '"':
            parts.append(_respace_code(buf))
            buf = ch
            in_string = True
        else:
            buf += ch
        i += 1
    parts.append(buf if in_string else _respace_code(buf))
    # Re-join, keeping exactly one space between a string and neighbouring
    # code unless punctuation hugs it.
    out = ""
    for chunk in parts:
        if not chunk:
            continue
        if out.endswith(" ") and chunk.startswith(" "):
            chunk = chunk[1:]  # never collapse inside strings, only here
        if out and chunk.startswith('"') and not out.endswith((" ", "{")):
            out += " "
        elif out and out.endswith('"') and not chunk.startswith((" ", ",", ":", "}")):
            out += " "
        out += chunk
    return out.strip()


def _respace_code(text: str) -> str:
    if not text:
        return text
    lead = " " if text[0].isspace() else ""
    trail = " " if text[-1].isspace() else ""
    s = re.sub(r"\s+", " ", text).strip()
    s = re.sub(r" ?, ?", ", ", s)
    s = re.sub(r",\s*$", ",", s)
    # Colons: no space before; one after, except a joined modifier suffix.
    s = re.sub(r" :", ":", s)
    s = re.sub(r":(?=\S)", ": ", s)
    s = _fix_joined(s)
    # Tuplet braces: ``2{sextuplet 1, 2}``.
    s = re.sub(r" ?\{ ?", "{", s)
    s = re.sub(r" ?\}", "}", s)
    s = s.replace(", }", "}")
    return (lead if s else "") + s + (trail if s else "")


def _fix_joined(s: str) -> str:
    """Re-join ``flam: SN`` / ``buzz: 8`` (modifier suffixes are one token)."""
    for word in _JOINED_COLON_WORDS:
        s = re.sub(rf"(?<![A-Za-z]){word}: (?=[A-Za-z0-9])", f"{word}:", s)
    return s


# ── Comments, alignment, blank lines ─────────────────────────────────────────

def _indent_comments(out: list[str], code_depths: list[int | None]) -> None:
    """Indent comment-only lines like the next code line (they usually
    describe what follows); trailing comments at the end of a block take
    the previous code line's depth."""
    for i, line in enumerate(out):
        if code_depths[i] is not None or not line:
            continue
        level = None
        for j in range(i + 1, len(out)):
            if code_depths[j] is not None:
                level = code_depths[j]
                break
        if level is None:
            for j in range(i - 1, -1, -1):
                if code_depths[j] is not None:
                    level = code_depths[j]
                    break
        out[i] = INDENT * (level or 0) + line.strip()


def _align_pattern_runs(out: list[str], code_depths: list[int | None]) -> None:
    """Align the value column of consecutive pattern lines at one depth."""
    i = 0
    while i < len(out):
        run = []
        j = i
        while j < len(out) and code_depths[j] is not None and _alignable(out[j]):
            if run and code_depths[j] != code_depths[run[0]]:
                break
            run.append(j)
            j += 1
        if len(run) > 1:
            width = max(len(_ALIGNABLE_RE.match(out[k].strip())["key"]) for k in run)
            for k in run:
                m = _ALIGNABLE_RE.match(out[k].strip())
                key = m["key"] + ":"
                out[k] = INDENT * code_depths[k] + key.ljust(width + 1) + m["rest"]
        i = max(j, i + 1)


def _alignable(line: str) -> bool:
    m = _ALIGNABLE_RE.match(line.strip())
    return bool(m) and m["key"] not in _NOT_PATTERN_KEYS


def _normalise_blank_lines(out: list[str], top_level_starts: set[int]) -> list[str]:
    """Collapse blank runs, trim the ends, and put one blank line above each
    top-level block (above its attached comment, if any)."""
    want_blank_before: set[int] = set()
    for line_no in top_level_starts:
        idx = line_no - 1
        while idx > 0 and out[idx - 1].strip() and _is_comment(out[idx - 1]):
            idx -= 1
        want_blank_before.add(idx)
    result: list[str] = []
    for idx, line in enumerate(out):
        if idx in want_blank_before and result and result[-1] != "":
            result.append("")
        if line == "" and (not result or result[-1] == ""):
            continue
        result.append(line)
    while result and result[-1] == "":
        result.pop()
    return result


def _is_comment(line: str) -> bool:
    s = line.strip()
    return s.startswith("#") or s.startswith("//")


# ── Safety net ───────────────────────────────────────────────────────────────

def _compiled_outputs(source: str) -> tuple:
    song = parse(source)
    if not song.grooves and not song.sections:
        return ("empty", song.metadata)
    ir = compile_song(song) if song.sections else compile_groove(song.grooves[0])
    return (emit_lilypond(ir), emit_midi(ir), emit_musicxml(ir))


__all__ = ["format_source", "FormatError"]
