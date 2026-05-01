"""CLI-level tests for argument handling that lives outside the parser."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from groovescript.cli import _run_compile, _run_midi, _run_musicxml, main

_SRC = (
    'groove "g":\n'
    "  HH: 1\n"
    'section "a":\n'
    "  bars: 1\n"
    '  groove: "g"\n'
)

_LONG_RUN_SRC = (
    'groove "money beat":\n'
    "  BD: 1, 3\n"
    "  SN: 2, 4\n"
    "  HH: *8\n"
    'section "verse":\n'
    "  bars: 12\n"
    '  groove: "money beat"\n'
)


def test_compile_refuses_to_overwrite_input(tmp_path: Path, capsys) -> None:
    """Regression: `compile foo.gs -o foo.gs` used to silently replace the
    source file with LilyPond output, destroying the user's work."""
    src = tmp_path / "song.gs"
    src.write_text(_SRC)
    rc = _run_compile(str(src), str(src))
    assert rc == 1
    assert src.read_text() == _SRC
    assert "refusing to overwrite" in capsys.readouterr().err


def test_midi_refuses_to_overwrite_input(tmp_path: Path, capsys) -> None:
    src = tmp_path / "song.gs"
    src.write_text(_SRC)
    rc = _run_midi(str(src), str(src))
    assert rc == 1
    assert src.read_text() == _SRC
    assert "refusing to overwrite" in capsys.readouterr().err


def test_musicxml_refuses_to_overwrite_input(tmp_path: Path, capsys) -> None:
    src = tmp_path / "song.gs"
    src.write_text(_SRC)
    rc = _run_musicxml(str(src), str(src))
    assert rc == 1
    assert src.read_text() == _SRC
    assert "refusing to overwrite" in capsys.readouterr().err


def test_compile_allows_different_output_path(tmp_path: Path) -> None:
    src = tmp_path / "song.gs"
    out = tmp_path / "song.ly"
    src.write_text(_SRC)
    rc = _run_compile(str(src), str(out))
    assert rc == 0
    assert out.exists()
    assert src.read_text() == _SRC


def _invoke_compile(monkeypatch, src_path: Path, out_path: Path, *extra: str) -> None:
    argv = ["groovescript", "compile", str(src_path), "-o", str(out_path), *extra]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0


def test_compile_defaults_to_compact(tmp_path: Path, monkeypatch) -> None:
    """Regression: `compile` without --compact must collapse 12 identical
    bars into one Play 12x block (compact mode is the new default)."""
    src = tmp_path / "song.gs"
    out = tmp_path / "song.ly"
    src.write_text(_LONG_RUN_SRC)
    _invoke_compile(monkeypatch, src, out)
    ly = out.read_text()
    assert "\\repeat volta 12" in ly
    assert '"Play 12x"' in ly
    assert "\\repeat volta 4" not in ly


def test_compile_no_compact_disables_default(tmp_path: Path, monkeypatch) -> None:
    """Regression: `--no-compact` opts out of the default compact mode and
    falls back to implicit 4-bar phrase chunking."""
    src = tmp_path / "song.gs"
    out = tmp_path / "song.ly"
    src.write_text(_LONG_RUN_SRC)
    _invoke_compile(monkeypatch, src, out, "--no-compact")
    ly = out.read_text()
    assert ly.count("\\repeat volta 4") == 3
    assert "\\repeat volta 12" not in ly


def test_compile_explicit_compact_still_accepted(tmp_path: Path, monkeypatch) -> None:
    """Regression: keep `--compact` working for backwards compatibility even
    though it is now the default."""
    src = tmp_path / "song.gs"
    out = tmp_path / "song.ly"
    src.write_text(_LONG_RUN_SRC)
    _invoke_compile(monkeypatch, src, out, "--compact")
    ly = out.read_text()
    assert "\\repeat volta 12" in ly
    assert '"Play 12x"' in ly
