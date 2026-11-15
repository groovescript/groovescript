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


_SIMPLE_GS = 'groove "g":\n  BD: 1, 3\n  SN: 2, 4\nsection "A":\n  bars: 1\n  groove: "g"\n'


def test_missing_output_directory_is_a_diagnostic_not_traceback(tmp_path: Path, capsys) -> None:
    """Regression: writing to ``-o`` in a directory that doesn't exist raised
    an uncaught FileNotFoundError traceback (and killed ``--watch``)."""
    src = tmp_path / "song.gs"
    src.write_text(_SIMPLE_GS)
    for run, ext in ((_run_compile, "ly"), (_run_midi, "mid"), (_run_musicxml, "xml")):
        assert run(str(src), str(tmp_path / "nodir" / f"out.{ext}")) == 1
        assert "error: cannot access" in capsys.readouterr().err


def test_directory_or_non_utf8_input_is_a_diagnostic(tmp_path: Path, capsys) -> None:
    """Regression: a directory or non-UTF-8 file as input raised
    IsADirectoryError / UnicodeDecodeError tracebacks."""
    from groovescript.cli import _run_lint

    assert _run_compile(str(tmp_path), str(tmp_path / "x.ly")) == 1
    assert "error: cannot access" in capsys.readouterr().err
    bad = tmp_path / "bad.gs"
    bad.write_bytes(b"\xff\xfe\x00groove")
    assert _run_lint(str(bad), False) == 1
    assert "not valid UTF-8" in capsys.readouterr().err


def test_groove_only_file_honours_meter_and_tempo(tmp_path: Path) -> None:
    """Regression: a file with grooves but no sections ignored its
    ``time_signature:``/``tempo:`` (always 4/4 at 120), so beat 6 in a 6/8
    groove was rejected as out of range."""
    src = tmp_path / "g.gs"
    src.write_text(
        'tempo: 90\ntime_signature: 6/8\n'
        'groove "g":\n  BD: 1, 4\n  HH: *8\n  SN: 6\n'
    )
    out = tmp_path / "g.ly"
    assert _run_compile(str(src), str(out)) == 0
    ly = out.read_text()
    assert "\\time 6/8" in ly and "\\tempo 8 = 90" in ly
    mid = tmp_path / "g.mid"
    assert _run_midi(str(src), str(mid)) == 0
    # 90 eighths/min = 45 quarters/min = 1 333 333 µs per quarter.
    assert b"\xFF\x51\x03" + (1_333_333).to_bytes(3, "big") in mid.read_bytes()
