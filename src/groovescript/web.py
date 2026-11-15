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

from dataclasses import dataclass, field

from .compiler import IRSong, compile_groove, compile_song
from .errors import GrooveScriptError
from .lint import StyleWarning, check_notation, check_style
from .midi import emit_midi
from .musicxml import emit_musicxml
from .parser import parse

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
    except Exception as exc:  # defence-in-depth: never let a bug kill the worker
        result.diagnostics.append(_internal_error(exc, source))
        return result

    result.title = song.metadata.title

    if style:
        try:
            for w in check_style(source, song):
                result.diagnostics.append(_warning_diagnostic(w, source, "info"))
        except Exception:  # style checks are advisory; never block a build
            pass

    if not song.grooves and not song.sections:
        return result

    try:
        ir = compile_song(song) if song.sections else compile_groove(song.grooves[0])
    except GrooveScriptError as err:
        result.diagnostics.append(_error_diagnostic(err, source))
        return result
    except Exception as exc:
        result.diagnostics.append(_internal_error(exc, source))
        return result

    for w in check_notation(ir):
        result.diagnostics.append(_warning_diagnostic(w, source, "warning"))

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
