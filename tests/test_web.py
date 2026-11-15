"""Tests for ``groovescript.web``, the entry point the browser editor calls
through Pyodide. It must never raise: every outcome is data."""

from pathlib import Path

import pytest

from groovescript.midi import emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.compiler import compile_song
from groovescript.parser import parse
from groovescript.web import EDITOR_FILENAME, build, build_js, format_js

FIXTURES = Path(__file__).parent / "fixtures"

SONG = """\
title: "Web Test"
tempo: 120

groove "beat":
  BD: 1, 3
  SN: 2, 4
  HH: *8

section "verse":
  bars: 4
  groove: "beat"
"""


def test_successful_build_matches_cli_exports():
    result = build(SONG)
    assert result.ok
    assert result.title == "Web Test"
    assert result.bar_count == 4
    ir = compile_song(parse(SONG))
    assert result.musicxml == emit_musicxml(ir).decode("utf-8")
    assert result.midi == emit_midi(ir)
    assert [d for d in result.diagnostics if d["severity"] != "info"] == []


def test_parse_error_becomes_located_diagnostic():
    result = build('title: "x"\ngroove "a":\n  snars: 1\n')
    assert not result.ok
    assert result.musicxml is None and result.midi is None
    [diag] = result.diagnostics
    assert diag["severity"] == "error"
    assert (diag["line"], diag["column"], diag["length"]) == (3, 3, 5)
    assert "snare" in diag["hint"]
    assert f"--> {EDITOR_FILENAME}:3:3" in diag["rendered"]


def test_compile_error_carries_source_context():
    source = SONG.replace('groove: "beat"', 'groove: "nope"')
    result = build(source)
    assert not result.ok
    errors = [d for d in result.diagnostics if d["severity"] == "error"]
    assert len(errors) == 1
    assert "nope" in errors[0]["message"]
    assert errors[0]["rendered"].startswith("error:")


def test_groove_only_source_builds():
    """Regression test: a file with only a groove compiles to an IRGroove,
    whose ``bars`` is an int, not a list. ``build`` used to call ``len()``
    on it and crash the editor's compiler warm-up."""
    result = build('groove "warmup":\n  BD: 1\n')
    assert result.ok
    assert result.bar_count == 1
    assert result.midi and result.musicxml


def test_empty_source_has_no_outputs_and_no_errors():
    result = build("")
    assert result.ok
    assert result.musicxml is None and result.midi is None
    assert result.bar_count == 0


def test_style_warnings_are_info_and_do_not_block_outputs():
    source = SONG.replace('section "verse"', 'groove "unused":\n  BD: 1\n\nsection "verse"')
    result = build(source)
    assert result.ok
    infos = [d for d in result.diagnostics if d["severity"] == "info"]
    assert any("unused" in d["message"] for d in infos)
    assert result.midi is not None
    assert build(source, style=False).diagnostics == []


def test_outputs_false_skips_emitters():
    result = build(SONG, outputs=False)
    assert result.ok and result.bar_count == 4
    assert result.musicxml is None and result.midi is None


def test_build_js_is_plain_data():
    data = build_js(SONG)
    assert set(data) == {"ok", "diagnostics", "musicxml", "midi", "title", "bar_count", "symbols"}
    assert data["ok"] is True
    assert isinstance(data["midi"], bytes)


def test_every_fixture_builds_without_internal_errors():
    for path in sorted(FIXTURES.glob("*.gs")):
        result = build(path.read_text())
        internal = [d for d in result.diagnostics if "internal error" in d["message"]]
        assert not internal, f"{path.name}: {internal}"
        assert result.ok, f"{path.name}: {result.diagnostics}"


def test_groove_only_source_honours_meter_and_tempo():
    """Regression: the editor compiled a sections-less file's groove in 4/4
    at 120 regardless of ``time_signature:``/``tempo:``, so beat 6 of a 6/8
    groove was rejected as out of range."""
    result = build(
        'tempo: 90\ntime_signature: 6/8\ngroove "g":\n  BD: 1, 4\n  HH: *8\n  SN: 6\n'
    )
    assert result.ok, result.diagnostics
    assert "<beat-type>8</beat-type>" in result.musicxml
    assert "<beat-unit>eighth</beat-unit>" in result.musicxml


def test_format_js_formats_valid_source():
    result = format_js('groove "g":\nBD:1\n')
    assert result == {"ok": True, "text": 'groove "g":\n  BD: 1\n', "diagnostics": []}


def test_format_js_reports_errors_instead_of_raising():
    result = format_js('groove "g":\n  snars: 1\n')
    assert result["ok"] is False and result["text"] is None
    [diag] = result["diagnostics"]
    assert diag["severity"] == "error" and diag["line"] == 2


# ── Editor vocabulary and symbols ────────────────────────────────────────────

from groovescript.library import get_library_fills, get_library_grooves, get_library_variations
from groovescript.midi import _NOTE
from groovescript.parser import parse as _parse
from groovescript.web import INSTRUMENT_NAMES, MODIFIER_DOCS, chart_symbols, vocabulary


def test_build_reports_symbols_with_line_ranges():
    source = (FIXTURES / "full_song_example.gs").read_text()
    symbols = build(source).symbols
    lines = source.split("\n")
    for kind, keyword in (("grooves", "groove"), ("fills", "fill"), ("sections", "section")):
        assert symbols[kind], kind
        for entry in symbols[kind]:
            header = lines[entry["line"] - 1]
            assert header.lstrip().startswith(f'{keyword} "{entry["name"]}"')
            assert entry["end_line"] >= entry["line"]


def test_symbols_are_none_when_source_does_not_parse():
    assert build('groove "g":\n  snars: 1\n').symbols is None


def test_chart_symbols_cover_every_definition_kind():
    source = SONG.replace(
        'section "verse"',
        'fill "f":\n  SN: 4\n\nvariation "v":\n  add CR at 1\n\nsection "verse"',
    )
    symbols = chart_symbols(source)
    assert [s["name"] for s in symbols["grooves"]] == ["beat"]
    assert [s["name"] for s in symbols["fills"]] == ["f"]
    assert [s["name"] for s in symbols["variations"]] == ["v"]
    assert [s["name"] for s in symbols["sections"]] == ["verse"]


def test_vocabulary_names_every_instrument_the_exporters_know():
    """Drift guard: a new instrument needs a display name for the editor."""
    assert set(INSTRUMENT_NAMES) == set(_NOTE)


def test_vocabulary_aliases_all_parse():
    for inst in vocabulary()["instruments"]:
        assert inst["aliases"][0] == inst["code"]
        for alias in inst["aliases"]:
            song = _parse(f'groove "g":\n  {alias}: 1\n')
            assert song.grooves, alias


def test_vocabulary_documents_every_modifier_in_the_grammar():
    """Drift guard: every MODIFIER alternative in grammar.lark has help."""
    grammar = (Path(__file__).parent.parent / "src" / "groovescript" / "grammar.lark").read_text()
    line = next(l for l in grammar.splitlines() if l.startswith("MODIFIER:"))
    import re as _re
    names = set(_re.findall(r'"([a-z0-9]+)"', line)) | set(_re.findall(r"/([a-z]+)\(", line))
    assert names <= set(MODIFIER_DOCS)
    assert "32nd" in MODIFIER_DOCS  # alias handled by the transformer


def test_vocabulary_library_matches_the_compiler_libraries():
    library = vocabulary()["library"]
    assert {e["name"] for e in library["grooves"]} == set(get_library_grooves())
    assert {e["name"] for e in library["fills"]} == set(get_library_fills())
    assert {e["name"] for e in library["variations"]} == set(get_library_variations())
    rock = next(e for e in library["grooves"] if e["name"] == "rock")
    assert rock["text"].startswith('groove "rock":\n  ')


@pytest.mark.parametrize("src, message", [
    ('section "v":\n  bars: 2\n  groove: "nope"\n', "unknown groove 'nope'"),
    ('groove "g":\n  BD: 1, 9\nsection "a":\n  bars: 1\n  groove: "g"\n',
     "Beat number 9 is out of range"),
])
def test_plain_value_errors_are_user_errors_not_internal(src, message):
    """Regression: ordinary mistakes raised by the compiler as plain
    ``ValueError`` were reported as "internal error ... please report this"
    in the editor, while the CLI shows them as normal errors."""
    result = build(src)
    errors = [d for d in result.diagnostics if d["severity"] == "error"]
    assert len(errors) == 1
    assert message in errors[0]["message"]
    assert "internal error" not in errors[0]["message"]
