"""Committed ``.ly`` files must match what the compiler currently emits.

Fixtures and templates are compiled and rendered by hand, so they drift
silently when the emitter or the LilyPond template changes. Several went
stale that way and one hid a real emitter bug (invalid ``r6.`` durations
under a fill over a triplet groove). Recompile with
``uv run groovescript compile <file>.gs -o <file>.ly`` and re-render the
PDF when this fails.
"""

from pathlib import Path

import pytest

from groovescript.compiler import compile_groove, compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse_file

ROOT = Path(__file__).resolve().parents[1]
_SOURCES = sorted(
    gs
    for pattern in ("tests/fixtures/*.gs", "templates/*.gs", "charts/*.gs")
    for gs in ROOT.glob(pattern)
    if gs.with_suffix(".ly").exists()
)


@pytest.mark.parametrize("gs", _SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_committed_ly_is_fresh(gs: Path) -> None:
    song = parse_file(str(gs))
    ir = compile_song(song) if song.sections else compile_groove(song.grooves[0])
    # compact=True matches the `compile` CLI default.
    assert emit_lilypond(ir, compact=True) == gs.with_suffix(".ly").read_text(), (
        f"{gs.relative_to(ROOT)}: committed .ly is stale; recompile and re-render it"
    )
