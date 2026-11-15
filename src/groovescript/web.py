"""In-browser entry point used by the web editor (via Pyodide).

The web editor runs this package inside a Web Worker and calls :func:`build`
on every (debounced) edit. Everything here is plain data in, plain data out
so it crosses the Python/JavaScript boundary cleanly: no exceptions escape,
and every problem comes back as a diagnostic the editor can underline.

The CLI is the reference for behaviour: ``build`` runs the same
parse -> compile -> emit pipeline as ``groovescript musicxml`` / ``midi``
and the same checks as ``groovescript lint --style``.
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from .compiler import IRSong, compile_song, compile_standalone_groove
from .errors import GrooveScriptError
from .fmt import format_source
from .lint import StyleWarning, check_notation, check_style
from .midi import emit_midi
from .musicxml import emit_musicxml
from .parser import parse
from .parser_notation import _INSTRUMENT_ALIASES
from .parser_preprocess import _preprocess_with_map
from .parser_transformer import _parser

#: Pseudo-filename shown in rendered diagnostics.
EDITOR_FILENAME = "chart.gs"


@dataclass
class BuildResult:
    """Outcome of one editor build.

    ``diagnostics`` holds dicts with ``severity`` (``"error"``, ``"warning"``
    or ``"info"``), ``message``, ``hint``, 1-indexed ``line`` / ``column``
    (``None`` when unknown), ``length`` and the CLI-style ``rendered`` text.
    ``musicxml`` / ``midi`` are ``None`` whenever there is an error or the
    chart has nothing to play yet.
    """

    diagnostics: list[dict] = field(default_factory=list)
    musicxml: str | None = None
    midi: bytes | None = None
    title: str | None = None
    bar_count: int = 0
    # Names the chart defines, for completion / hover / go-to-definition:
    # {"grooves"|"fills"|"variations"|"sections": [{name, line, end_line}]}.
    # None when the source does not parse (the editor keeps the last set).
    symbols: dict | None = None

    @property
    def ok(self) -> bool:
        return not any(d["severity"] == "error" for d in self.diagnostics)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "diagnostics": self.diagnostics,
            "musicxml": self.musicxml,
            "midi": self.midi,
            "title": self.title,
            "bar_count": self.bar_count,
            "symbols": self.symbols,
        }


def _error_diagnostic(err: GrooveScriptError, source: str) -> dict:
    if err.source is None:
        err.source = source
    if err.filename is None:
        err.filename = EDITOR_FILENAME
    return {
        "severity": "error",
        "message": err.message,
        "hint": err.hint,
        "line": err.line,
        "column": err.column,
        "length": max(err.length, 1),
        "rendered": err.render(),
    }


def _warning_diagnostic(w: StyleWarning, source: str, severity: str) -> dict:
    return {
        "severity": severity,
        "message": w.message,
        "hint": w.hint,
        "line": w.line,
        "column": w.column,
        "length": max(w.length, 1),
        "rendered": w.render(filename=EDITOR_FILENAME, source=source),
    }


def _plain_error(exc: ValueError, source: str) -> dict:
    """Diagnostic for a ``ValueError`` raised by the compiler or emitters.

    Many user mistakes (an unknown groove name, a beat out of range) are
    still raised as plain ``ValueError`` without a source location. The CLI
    renders those as ordinary errors, so the editor does the same rather
    than calling them internal errors.
    """
    return _error_diagnostic(
        GrooveScriptError(message=str(exc), filename=EDITOR_FILENAME), source
    )


def build(source: str, *, style: bool = True, outputs: bool = True) -> BuildResult:
    """Parse, compile and (optionally) emit ``source``.

    Args:
        source: GrooveScript text.
        style: also run the ``lint --style`` checks, reported as ``info``.
        outputs: emit MusicXML and MIDI when the chart compiles. Pass
            ``False`` for a diagnostics-only pass.
    """
    result = BuildResult()
    try:
        song = parse(source, filename=EDITOR_FILENAME)
    except GrooveScriptError as err:
        result.diagnostics.append(_error_diagnostic(err, source))
        return result
    except ValueError as exc:  # a user mistake reported without a location
        result.diagnostics.append(_plain_error(exc, source))
        return result
    except Exception as exc:  # defence-in-depth: never let a bug kill the worker
        result.diagnostics.append(_internal_error(exc, source))
        return result

    result.title = song.metadata.title
    try:
        result.symbols = chart_symbols(source)
    except Exception:  # navigation aids are optional; never block a build
        result.symbols = None

    if style:
        try:
            for w in check_style(source, song):
                result.diagnostics.append(_warning_diagnostic(w, source, "info"))
        except Exception:  # style checks are advisory; never block a build
            pass

    if not song.grooves and not song.sections:
        return result

    try:
        ir = compile_song(song) if song.sections else compile_standalone_groove(song)
    except GrooveScriptError as err:
        result.diagnostics.append(_error_diagnostic(err, source))
        return result
    except ValueError as exc:  # a user mistake reported without a location
        result.diagnostics.append(_plain_error(exc, source))
        return result
    except Exception as exc:
        result.diagnostics.append(_internal_error(exc, source))
        return result

    try:
        for w in check_notation(ir):
            result.diagnostics.append(_warning_diagnostic(w, source, "warning"))
    except Exception:  # playability hints are advisory; never block a build
        pass

    if isinstance(ir, IRSong):
        result.bar_count = len(ir.bars)
    else:  # a lone groove: IRGroove.bars is already a count
        result.bar_count = ir.bars

    if outputs:
        try:
            result.musicxml = emit_musicxml(ir).decode("utf-8")
            result.midi = emit_midi(ir)
        except GrooveScriptError as err:
            result.diagnostics.append(_error_diagnostic(err, source))
            result.musicxml = result.midi = None
        except ValueError as exc:
            result.diagnostics.append(_plain_error(exc, source))
            result.musicxml = result.midi = None
        except Exception as exc:
            result.diagnostics.append(_internal_error(exc, source))
            result.musicxml = result.midi = None

    return result


def _internal_error(exc: Exception, source: str) -> dict:
    err = GrooveScriptError(
        message=(
            f"internal error ({type(exc).__name__}: {exc}) "
            "— please report this with the offending source"
        ),
        filename=EDITOR_FILENAME,
        source=source,
    )
    return _error_diagnostic(err, source)


def build_js(source: str) -> dict:
    """:func:`build` flattened to a dict for ``pyodide``'s ``to_js``."""
    return build(source).to_dict()


def format_js(source: str) -> dict:
    """``groovescript fmt`` for the editor's Format button: never raises.

    Returns ``{"ok", "text", "diagnostics"}``; ``text`` is the formatted
    source, or ``None`` when the chart has errors (only valid charts can be
    formatted) and ``diagnostics`` says why.
    """
    try:
        return {"ok": True, "text": format_source(source), "diagnostics": []}
    except GrooveScriptError as err:
        return {"ok": False, "text": None, "diagnostics": [_error_diagnostic(err, source)]}
    except Exception as exc:  # defence-in-depth, as in build()
        return {"ok": False, "text": None, "diagnostics": [_internal_error(exc, source)]}


# ── Editor vocabulary: completion and hover data ─────────────────────────────

_DEFINITION_KINDS = {
    "groove_def": "grooves",
    "groove_placeholder_def": "grooves",
    "fill_def": "fills",
    "fill_def_bare": "fills",
    "fill_def_extend_bare": "fills",
    "variation_def": "variations",
    "section_def": "sections",
}

#: Display names for each canonical instrument (matches the DSL reference).
INSTRUMENT_NAMES: dict[str, str] = {
    "BD": "bass drum", "SN": "snare", "SCS": "snare cross stick",
    "HH": "closed hi-hat", "OH": "open hi-hat", "HF": "hi-hat foot chick",
    "RD": "ride (bow)", "RB": "ride bell", "CR": "crash", "CR2": "second crash",
    "SP": "splash", "CH": "china", "ST": "stack", "CB": "cowbell",
    "FT": "floor tom", "HT": "high tom", "MT": "mid tom",
}

#: One-line help for each modifier (from the DSL reference).
MODIFIER_DOCS: dict[str, str] = {
    "ghost": "Ghost note: parenthesised notehead, played softly.",
    "accent": "Accent: > above the note, played louder.",
    "choke": "Choke: + above a ringing cymbal, grabbed to silence it.",
    "fermata": "Fermata: hold the hit longer than written (notation only).",
    "flam": "Flam: one grace note before the hit (flam:SN puts the grace on another drum).",
    "drag": "Drag: two grace notes before the hit (drag:SN puts them on another drum).",
    "double": "Double stroke: plays a 16th slot as two 32nds (alias 32nd).",
    "32nd": "Double stroke: plays a 16th slot as two 32nds (alias of double).",
    "buzz": "Buzz roll held for a duration (buzz:4, buzz:8, buzz:4d, ...).",
}


def _definitions(source: str) -> list[tuple[str, str, int, int]]:
    """(kind, name, first_line, last_line) for each top-level definition,
    from the raw parse tree (raises on unparsable source)."""
    preprocessed, _ = _preprocess_with_map(source)
    tree = _parser.parse(preprocessed)
    out = []
    for node in tree.children:
        kind = _DEFINITION_KINDS.get(getattr(node, "data", None))
        if kind is None:
            continue
        name_token = next(
            (t for t in node.children if getattr(t, "type", None) == "ESCAPED_STRING"), None
        )
        if name_token is None:
            continue
        out.append((kind, ast.literal_eval(str(name_token)), node.meta.line, node.meta.end_line))
    return out


def chart_symbols(source: str) -> dict:
    """Names defined in ``source`` with their line ranges (1-indexed)."""
    symbols: dict[str, list[dict]] = {k: [] for k in ("grooves", "fills", "variations", "sections")}
    for kind, name, line, end_line in _definitions(source):
        symbols[kind].append({"name": name, "line": line, "end_line": end_line})
    return symbols


def _library_entries() -> dict[str, list[dict]]:
    here = Path(__file__).parent
    out: dict[str, list[dict]] = {"grooves": [], "fills": [], "variations": []}
    for filename in ("groove_library.gs", "fill_library.gs", "variation_library.gs"):
        text = (here / filename).read_text()
        lines = text.split("\n")
        for kind, name, line, end_line in _definitions(text):
            if kind in out:
                header = lines[line - 1].strip()
                body = textwrap.dedent("\n".join(lines[line:end_line])).strip("\n")
                text = header + ("\n" + textwrap.indent(body, "  ") if body else "")
                out[kind].append({"name": name, "text": text})
    return out


def _grammar_accepts_instrument(alias: str) -> bool:
    pattern = _parser.get_terminal("INSTRUMENT").pattern.to_regexp()
    return re.fullmatch(pattern, alias) is not None


def vocabulary() -> dict:
    """Static editor vocabulary: instruments (with every alias the grammar
    accepts), modifiers, and the built-in library definitions with their
    source text. Loaded once by the editor."""
    instruments = []
    for code, name in INSTRUMENT_NAMES.items():
        aliases = sorted(
            {alias for alias, canon in _INSTRUMENT_ALIASES.items() if canon == code}
            | {code},
            key=lambda a: (a != code, a.lower() == code.lower(), a),
        )
        instruments.append({
            "code": code,
            "name": name,
            "aliases": [a for a in aliases if _grammar_accepts_instrument(a)],
        })
    modifiers = [{"name": name, "doc": doc} for name, doc in MODIFIER_DOCS.items()]
    return {"instruments": instruments, "modifiers": modifiers, "library": _library_entries()}


def vocabulary_js() -> dict:
    return vocabulary()
