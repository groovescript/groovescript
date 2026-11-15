"""Tests for ``groovescript.web``, the entry point the browser editor calls
through Pyodide. It must never raise: every outcome is data."""

from pathlib import Path

from groovescript.midi import emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.compiler import compile_song
from groovescript.parser import parse
from groovescript.web import EDITOR_FILENAME, build, build_js

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
    assert set(data) == {"ok", "diagnostics", "musicxml", "midi", "title", "bar_count"}
    assert data["ok"] is True
    assert isinstance(data["midi"], bytes)


def test_every_fixture_builds_without_internal_errors():
    for path in sorted(FIXTURES.glob("*.gs")):
        result = build(path.read_text())
        internal = [d for d in result.diagnostics if "internal error" in d["message"]]
        assert not internal, f"{path.name}: {internal}"
        assert result.ok, f"{path.name}: {result.diagnostics}"
