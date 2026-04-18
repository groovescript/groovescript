"""Public parser entry points.

``parse()`` and ``parse_file()`` are the only intended external API. The
heavy lifting lives in sibling modules:
  * :mod:`parser_preprocess`   — source-level rewrites + column mapping
  * :mod:`parser_notation`     — instrument/beat/count/notes tokenisation
  * :mod:`parser_transformer`  — Lark grammar load + ``Transformer`` walk
  * :mod:`parser_errors`       — Lark exception → :class:`GrooveScriptError`

A handful of ``_``-prefixed names are re-exported below because
``compiler`` and the test suite reach into them directly.
"""

from pathlib import Path

from lark.exceptions import UnexpectedInput, VisitError

from .ast_nodes import Song
from .errors import GrooveScriptError
from .parser_errors import (
    _location_from_tree,
    _translate_lark_error,
)
from .parser_notation import (
    _format_count_notes_mismatch,
    _normalize_instrument,
    _parse_count_tokens,
    _parse_notes_tokens,
)
from .parser_preprocess import (
    _preprocess_commas,
    _preprocess_with_map,
    _remap_location,
)
from .parser_transformer import _GrooveScriptTransformer, _parser

__all__ = [
    "CURRENT_DSL_VERSION",
    "parse",
    "parse_file",
    # Re-exported for compiler.py and the test suite.
    "_format_count_notes_mismatch",
    "_normalize_instrument",
    "_parse_count_tokens",
    "_parse_notes_tokens",
    "_preprocess_commas",
]


#: Current GrooveScript DSL version. Bump on breaking DSL changes and
#: document the change in the release notes. Files that declare
#: ``dsl_version: N`` with N different from this value will fail to parse.
CURRENT_DSL_VERSION = 1


def parse(source: str, *, filename: str | None = None) -> Song:
    """Parse GrooveScript source text into a Song AST node.

    Raises:
        GrooveScriptError: if the source cannot be parsed. The error carries
            a human-readable message, a source excerpt, and (where possible)
            a hint for how to fix the problem.
    """
    preprocessed, col_maps = _preprocess_with_map(source)
    try:
        tree = _parser.parse(preprocessed)
    except UnexpectedInput as exc:
        raise _translate_lark_error(
            exc, preprocessed, source, col_maps, filename
        ) from None

    try:
        song = _GrooveScriptTransformer().transform(tree)
    except VisitError as exc:
        inner = exc.orig_exc
        if isinstance(inner, GrooveScriptError):
            # Fill in missing context from the tree node, if we have it.
            if inner.source is None:
                inner.source = source
            if inner.filename is None:
                inner.filename = filename
            if inner.line is not None:
                inner.line, inner.column = _remap_location(
                    inner.line, inner.column, col_maps
                )
            raise inner from None
        if isinstance(inner, ValueError):
            line, column = _location_from_tree(exc.obj)
            line, column = _remap_location(line, column, col_maps)
            raise GrooveScriptError(
                message=str(inner),
                filename=filename,
                source=source,
                line=line,
                column=column,
                length=1,
            ) from None
        raise

    # DSL version gate: a file may omit dsl_version (treated as "current"),
    # but if it declares a version it must match CURRENT_DSL_VERSION exactly.
    declared = song.metadata.dsl_version
    if declared is not None and declared != CURRENT_DSL_VERSION:
        raise GrooveScriptError(
            message=(
                f"dsl_version {declared} is not supported by this groovescript "
                f"(current version is {CURRENT_DSL_VERSION})"
            ),
            filename=filename,
            source=source,
            hint=(
                "update the file to the current DSL version, or use an older "
                "groovescript release that targets this version"
            ),
        )
    return song


def parse_file(path: str) -> Song:
    """Parse a GrooveScript file into a Song AST node."""
    return parse(Path(path).read_text(), filename=path)
