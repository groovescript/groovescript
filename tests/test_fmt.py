"""Tests for ``groovescript fmt`` (groovescript.fmt.format_source + CLI)."""

import subprocess
import textwrap
import sys
from pathlib import Path

import pytest

from groovescript import fmt
from groovescript.errors import GrooveScriptError
from groovescript.fmt import FormatError, format_source

ROOT = Path(__file__).resolve().parent.parent
CORPUS = sorted(
    list((ROOT / "tests" / "fixtures").glob("*.gs"))
    + list((ROOT / "templates").glob("**/*.gs"))
    + list((ROOT / "src" / "groovescript").glob("*_library.gs"))
)


def _dedent(text: str) -> str:
    return textwrap.dedent(text).strip("\n") + "\n"


# ── Corpus: every real file formats safely and stably ───────────────────────

@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.name)
def test_corpus_formats_idempotently(path):
    """format_source's own safety net proves the compiled output is
    unchanged; formatting twice must give the same text."""
    once = format_source(path.read_text())
    assert format_source(once) == once
    assert once.endswith("\n") and not once.endswith("\n\n")
    assert all(line == line.rstrip() for line in once.split("\n"))


# ── Indentation ──────────────────────────────────────────────────────────────

def test_indentation_comes_from_structure_not_old_indent():
    src = 'title: "x"\ngroove "g":\nBD: 1, 3\n        SN: 2, 4\nsection "s":\n bars: 2\n       groove: "g"\n'
    assert format_source(src) == _dedent('''
    title: "x"

    groove "g":
      BD: 1, 3
      SN: 2, 4

    section "s":
      bars: 2
      groove: "g"
    ''')


def test_nested_blocks_indent_one_level_each():
    src = _dedent('''
    groove "g":
          bar 1:
     BD: 1
          bar 2:
              like: bar 1
    fill "f":
        count "3 e & a 4":
              3: SN
              4: BD
    section "s":
        play:
                groove "g" x2
                bar "hit":
                 CR: 1
        variation at bar 2:
         add CR at 1
        lyrics:
              bar 1: "1 3" "hey you"
        fill at bar 3:
                    SN: 1, 2
    ''')
    assert format_source(src) == _dedent('''
    groove "g":
      bar 1:
        BD: 1
      bar 2:
        like: bar 1

    fill "f":
      count "3 e & a 4":
        3: SN
        4: BD

    section "s":
      play:
        groove "g" x2
        bar "hit":
          CR: 1
      variation at bar 2:
        add CR at 1
      lyrics:
        bar 1: "1 3" "hey you"
      fill at bar 3:
        SN: 1, 2
    ''')


def test_inline_section_groove_body_is_one_level_deeper():
    src = 'section "s":\n  bars: 2\n  groove:\n      BD: 1, 3\n      SN: 2, 4\n'
    assert format_source(src) == 'section "s":\n  bars: 2\n  groove:\n    BD: 1, 3\n    SN: 2, 4\n'


def test_extend_body_stays_a_sibling_of_extend():
    src = 'groove "a":\n  BD: 1\ngroove "b":\n  extend: "a"\n      SN: 2\n'
    assert format_source(src).endswith('groove "b":\n  extend: "a"\n  SN: 2\n')


# ── Spacing ──────────────────────────────────────────────────────────────────

def test_spacing_around_colons_and_commas():
    src = 'groove "g":\n  BD :1 ,3\n  SN:2,4\n'
    assert format_source(src) == 'groove "g":\n  BD: 1, 3\n  SN: 2, 4\n'


def test_comma_free_beat_lists_keep_their_style():
    src = 'groove "g":\n  BD:   1    3\n'
    assert format_source(src) == 'groove "g":\n  BD: 1 3\n'


def test_strings_are_untouched():
    """Regression test: a final whitespace-collapsing pass also ran inside
    strings, so ``"Two  spaces"`` lost a space (the safety net caught it)."""
    src = 'title:   "Two  spaces,  and:colons"\ngroove "g":\n  BD: 1\nsection "s":\n  bars: 1\n  groove: "g"\n  cue   "a ,  b"   at bar 1\n'
    out = format_source(src)
    assert 'title: "Two  spaces,  and:colons"' in out
    assert '  cue "a ,  b" at bar 1' in out


def test_modifier_suffixes_stay_joined():
    src = 'groove "g":\n  HT: 1 flam:SN, 2 drag:SN\n  SN: 3 buzz:8\n'
    out = format_source(src)
    assert "flam:SN" in out and "drag:SN" in out and "buzz:8" in out


def test_tuplet_braces_have_no_inner_spaces():
    src = 'groove "g":\n  HH: 1, 2{ sextuplet 1 , 2 , 3 } , 3\n'
    assert format_source(src) == 'groove "g":\n  HH: 1, 2{sextuplet 1, 2, 3}, 3\n'


# ── Comments, alignment, blank lines ─────────────────────────────────────────

def test_comments_are_kept_and_indented_like_the_code_below():
    src = _dedent('''
    # Grooves
    groove "g":
    # the backbeat
            SN: 2, 4   // snare
          BD: 1 # kick
    ''')
    assert format_source(src) == _dedent('''
    # Grooves
    groove "g":
      # the backbeat
      SN: 2, 4   // snare
      BD: 1 # kick
    ''')


def test_pattern_values_align_within_a_run():
    src = 'groove "g":\n  kick: 1, 3\n  snare: 2, 4\n  HH: *8\n'
    assert format_source(src) == 'groove "g":\n  kick:  1, 3\n  snare: 2, 4\n  HH:    *8\n'


def test_settings_lines_are_not_aligned_as_patterns():
    src = 'section "s":\n  bars: 2\n  groove: "rock"\n'
    assert format_source(src) == src


def test_blank_lines_collapse_and_separate_top_level_blocks():
    src = '\n\ntitle: "x"\ngroove "a":\n  BD: 1\n\n\n\n# about b\ngroove "b":\n  BD: 1\n\n\n'
    assert format_source(src) == 'title: "x"\n\ngroove "a":\n  BD: 1\n\n# about b\ngroove "b":\n  BD: 1\n'


def test_crlf_input_becomes_lf():
    src = 'groove "g":\r\n  BD: 1\r\n'
    assert format_source(src) == 'groove "g":\n  BD: 1\n'


# ── Safety ───────────────────────────────────────────────────────────────────

def test_invalid_chart_is_an_error_not_a_guess():
    with pytest.raises(GrooveScriptError) as exc:
        format_source('groove "g":\n  snars: 1\n')
    assert "snars" in exc.value.message


def test_safety_net_refuses_output_that_changes_the_chart(monkeypatch):
    """If a formatting bug ever altered meaning, nothing is returned."""
    monkeypatch.setattr(fmt, "_respace", lambda code: code.replace("3", "4"))
    with pytest.raises(FormatError):
        format_source('groove "g":\n  BD: 1, 3\n')


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "groovescript.cli", "fmt", *args],
        input=stdin, capture_output=True, text=True, cwd=ROOT,
    )


def test_cli_formats_in_place_and_check_passes_after(tmp_path):
    path = tmp_path / "song.gs"
    path.write_text('groove "g":\nBD:1\n')
    check = _cli("--check", str(path))
    assert check.returncode == 1 and "would reformat" in check.stdout
    assert path.read_text() == 'groove "g":\nBD:1\n'  # --check changes nothing
    done = _cli(str(path))
    assert done.returncode == 0
    assert path.read_text() == 'groove "g":\n  BD: 1\n'
    assert _cli("--check", str(path)).returncode == 0


def test_cli_diff_and_stdin(tmp_path):
    path = tmp_path / "song.gs"
    path.write_text('groove "g":\nBD:1\n')
    diff = _cli("--diff", str(path))
    assert diff.returncode == 1
    assert "-BD:1" in diff.stdout and "+  BD: 1" in diff.stdout
    piped = _cli("-", stdin='groove "g":\nBD:1\n')
    assert piped.returncode == 0 and piped.stdout == 'groove "g":\n  BD: 1\n'


def test_cli_reports_errors_with_location(tmp_path):
    path = tmp_path / "bad.gs"
    path.write_text('groove "g":\n  snars: 1\n')
    result = _cli(str(path))
    assert result.returncode == 1
    assert f"{path}:2:3" in result.stderr
    assert path.read_text() == 'groove "g":\n  snars: 1\n'


def test_cli_reports_unreadable_input_without_traceback(tmp_path):
    """Non-UTF-8 input and directories get a diagnostic, like the other
    subcommands (main's CLI hardening), not a Python traceback."""
    binary = tmp_path / "binary.gs"
    binary.write_bytes(b"\xff\xfe\x00 not text")
    result = _cli(str(binary), str(tmp_path))
    assert result.returncode == 1
    assert "not valid UTF-8" in result.stderr
    assert "cannot read input file" in result.stderr
    assert "Traceback" not in result.stderr


def test_lyrics_entries_align_count_and_words_columns():
    """Regression test: fmt collapsed the hand-aligned gap between a lyrics
    entry's count and words strings, which the lyrics docs encourage."""
    src = _dedent('''
    groove "g":
      BD: 1
    section "s":
      bars: 4
      groove: "g"
      lyrics:
        bar 1: "1 2& 3 4" "When the night falls"
        bar 2:   "1 3"  "_ down"
        bars 3-4: "1 | 1 3" "hey you ,"
    ''')
    out = format_source(src)
    assert out.endswith(
        '  lyrics:\n'
        '    bar 1:    "1 2& 3 4" "When the night falls"\n'
        '    bar 2:    "1 3"      "_ down"\n'
        '    bars 3-4: "1 | 1 3"  "hey you ,"\n'
    )
