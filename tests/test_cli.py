"""CLI-level tests for argument handling that lives outside the parser."""

from __future__ import annotations

from pathlib import Path

from groovescript.cli import _run_compile, _run_midi, _run_musicxml

_SRC = (
    'groove "g":\n'
    "  HH: 1\n"
    'section "a":\n'
    "  bars: 1\n"
    '  groove: "g"\n'
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
