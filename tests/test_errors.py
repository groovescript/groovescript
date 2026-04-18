"""Tests for GrooveScript's friendly error reporting.

These cover the end-to-end parser path: malformed source text is expected
to raise :class:`GrooveScriptError` with a usable location and, where
reasonable, a hint explaining how to fix the problem.
"""

from __future__ import annotations

import pytest

from groovescript.compiler import compile_groove, compile_song
from groovescript.errors import GrooveScriptError
from groovescript.parser import parse


def _err(src: str) -> GrooveScriptError:
    with pytest.raises(GrooveScriptError) as excinfo:
        parse(src, filename="song.gs")
    return excinfo.value


# ── Keyword misspellings ─────────────────────────────────────────────────


def test_misspelled_top_level_keyword_gets_hint() -> None:
    err = _err("tempos: 120\n")
    assert err.line == 1
    assert err.hint is not None
    assert "tempo" in err.hint


def test_render_includes_filename_line_column_and_caret() -> None:
    err = _err(
        'groove "x":\n'
        "  paattern:\n"
        "    BD: 1\n"
    )
    rendered = err.render()
    assert "error: " in rendered
    assert "song.gs:2:3" in rendered
    assert "paattern" in rendered
    assert "^" in rendered
    assert "hint:" in rendered


# ── Instrument typos ─────────────────────────────────────────────────────


def test_misspelled_instrument_name_suggests_alternative() -> None:
    err = _err(
        'groove "x":\n'
        "    snars: 1, 3\n"
    )
    assert err.line == 2
    assert err.hint is not None
    assert "snare" in err.hint


def test_completely_unknown_word_lists_expected_content() -> None:
    err = _err(
        'groove "x":\n'
        "    xyzzy: 1, 3\n"
    )
    assert err.line == 2
    assert err.hint is not None
    # Should describe expected content — instrument or beat number.
    assert "instrument" in err.hint or "beat" in err.hint


# ── Modifier typos inside beat lists ─────────────────────────────────────


def test_misspelled_modifier_in_beat_list_suggests_real_modifier() -> None:
    err = _err(
        'groove "x":\n'
        "    BD: 1 accnt, 3\n"
    )
    assert err.hint is not None
    assert "accent" in err.hint


# ── Structural mistakes ──────────────────────────────────────────────────


def test_bad_time_signature_format_describes_expected_shape() -> None:
    err = _err("time_signature: 4-4\n")
    assert err.hint is not None
    assert "4/4" in err.hint


def test_eof_in_middle_of_block_reports_location() -> None:
    err = _err('groove "x":\n  BD:\n')
    assert err.line is not None
    # Parser should tell us what kind of thing it wanted next.
    assert err.hint is not None


def test_zero_tempo_is_rejected_at_parse_time() -> None:
    """Regression: tempo=0 used to reach midi.py and crash with a raw
    ZeroDivisionError traceback instead of GrooveScriptError."""
    err = _err("metadata:\n  tempo: 0\n")
    assert "tempo" in err.message
    assert err.line == 2


def test_zero_section_tempo_is_rejected_at_parse_time() -> None:
    """Regression: per-section tempo override must also be > 0."""
    src = (
        'groove "g":\n'
        "  HH: 1\n"
        'section "a":\n'
        "  bars: 1\n"
        "  tempo: 0\n"
        '  groove: "g"\n'
    )
    err = _err(src)
    assert "tempo" in err.message


# ── Compile-time errors still surface as GrooveScriptError ───────────────


def test_count_notes_mismatch_in_fill_is_friendly() -> None:
    # Count/notes mismatches are raised from the transformer as ValueError
    # and must be translated to GrooveScriptError with source context.
    src = 'fill "f":\n  count: "1 e & a 2" notes: "BD SN"\n'
    with pytest.raises(GrooveScriptError) as excinfo:
        parse(src, filename="song.gs")
    err = excinfo.value
    assert err.line is not None
    assert "5 slot" in err.message and "2 slot" in err.message


def test_count_notes_mismatch_shows_aligned_diagnostic() -> None:
    """Regression: count+notes mismatches must render a column-aligned
    diagnostic that stacks the two strings and underlines the first
    orphan slot, so the author can see exactly where the counts diverge.
    """
    src = 'fill "f":\n  count: "1 e & a 2" notes: "BD SN SN BD"\n'
    with pytest.raises(GrooveScriptError) as excinfo:
        parse(src, filename="song.gs")
    msg = excinfo.value.message
    # The context phrase identifies the construct.
    assert "fill block" in msg
    # Both strings appear in the message, stacked and labelled.
    assert "count: 1 e & a 2" in msg
    assert "notes: BD SN SN BD" in msg
    # A caret underlines the first orphan slot in the longer string.
    assert "^" in msg


def test_count_notes_mismatch_with_extra_notes_points_at_notes() -> None:
    """Regression: when the notes string is the longer side, the caret
    must appear under the notes line, not the count line.
    """
    src = 'fill "f":\n  count: "1 2" notes: "BD SN SN BD"\n'
    with pytest.raises(GrooveScriptError) as excinfo:
        parse(src, filename="song.gs")
    msg = excinfo.value.message
    # Every line after the count line — including the caret — must come
    # after the "notes:" line in the rendered message, which is only the
    # case when the caret is placed under the notes row.
    notes_idx = msg.index("notes: BD SN SN BD")
    caret_idx = msg.index("^")
    assert caret_idx > notes_idx


def test_beat_out_of_range_in_compile_is_friendly() -> None:
    src = (
        'groove "x":\n'
        "    BD: 5\n"
    )
    song = parse(src, filename="song.gs")
    with pytest.raises(ValueError) as excinfo:
        compile_groove(song.grooves[0])
    # compile_groove still raises plain ValueError; the CLI wraps it.
    assert "out of range" in str(excinfo.value)


def test_section_missing_required_fields_reports_clean_message() -> None:
    # A section without bars/groove/like/play is a compile-time error when no
    # metadata defaults are set.
    from groovescript.compiler import compile_song

    src = 'groove "g":\n    BD: 1\nsection "s":\n  repeat: 2\n'
    song = parse(src, filename="song.gs")
    with pytest.raises(ValueError, match="bars|groove"):
        compile_song(song)


# ── Preprocessor location mapping ────────────────────────────────────────
#
# The preprocessors (`_quote_unquoted_count_notes`, `_preprocess_commas`)
# rewrite the source text before Lark sees it — inserting commas, wrapping
# count/notes values in quotes, etc. Lark reports error columns against the
# rewritten text, so without a column map the reported column can point
# past what the author actually wrote. These tests are regressions for
# that bug.


def test_error_column_maps_back_through_comma_insertion() -> None:
    """Regression: comma-insertion preprocessor must not misreport error columns.

    The source ``BD: 1 snares 3`` is rewritten to ``BD: 1, snares, 3`` before
    parsing. Without the column map, Lark's error on ``snares`` would be
    reported at column 12 (in the rewritten text) instead of column 11 where
    the author actually typed it.
    """
    src = 'groove "x":\n    BD: 1 snares 3\n'
    err = _err(src)
    assert err.line == 2
    # 'snares' starts at column 11 in the original source:
    #     "    BD: 1 snares 3"
    #      1234567890123456
    assert err.column == 11, (
        f"expected column 11 (original position of 'snares'), got {err.column}"
    )
    # The rendered diagnostic must also show the original source line,
    # not the preprocessed (commafied) one.
    rendered = err.render()
    assert "BD: 1 snares 3" in rendered
    assert "BD: 1, snares, 3" not in rendered


def test_count_notes_mismatch_shows_original_unquoted_source() -> None:
    """Regression: unquoted ``count:``/``notes:`` lines must not leak quotes
    into the rendered diagnostic.

    The ``_quote_unquoted_count_notes`` preprocessor wraps bare values in
    double quotes so the grammar accepts them. Previously the error carried
    the preprocessed source, so users saw ``count: "1 e & a 2"`` in the
    diagnostic even though they had written ``count: 1 e & a 2``.
    """
    src = 'fill "f":\n    count: 1 e & a 2\n    notes: BD SN\n'
    with pytest.raises(GrooveScriptError) as excinfo:
        parse(src, filename="song.gs")
    rendered = excinfo.value.render()
    assert "count: 1 e & a 2" in rendered
    assert 'count: "1 e & a 2"' not in rendered
