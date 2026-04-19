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


def test_hi_hat_with_hyphen_suggests_hihat() -> None:
    """Regression: 'hi-hat' is not in the grammar INSTRUMENT terminal (intentionally
    excluded; use 'hihat'). The hint must not suggest 'hi-hat' back to the user."""
    err = _err(
        'groove "x":\n'
        "    hi-hat: *8\n"
    )
    assert err.hint is not None
    # The suggestion must be 'hihat', not 'hi-hat' again.
    assert err.hint.endswith("'hihat'?")


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


# ── Compile-time diagnostics carry line numbers ──────────────────────────
#
# Compile errors that originate from a specific AST node (variation action,
# pattern line, buzz event) must surface the line where the user wrote the
# offending construct. Without the line the diagnostic is a flat string
# that forces the user to grep their chart for the cited bar number.


def _compile_err(src: str) -> GrooveScriptError:
    song = parse(src, filename="song.gs")
    with pytest.raises(GrooveScriptError) as excinfo:
        if song.sections:
            compile_song(song)
        else:
            compile_groove(song.grooves[0])
    err = excinfo.value
    # Mirror what the CLI does so render() produces the full visual output.
    if err.source is None:
        err.source = src
    if err.filename is None:
        err.filename = "song.gs"
    return err


def test_variation_replace_stacking_reports_line() -> None:
    """Regression: a ``replace X with Y`` action that would stack two Y
    notes must cite the variation's source line, not just the bar number.
    Guards against the einstein-on-the-beach debugging experience where the
    user had to grep to find which ``replace`` line was at fault.
    """
    src = (
        'groove "money":\n'
        "  HH: *8\n"
        "  BD: 1, 3\n"
        "  SN: 2, 4\n"
        "\n"
        'section "bridge":\n'
        "  bars: 2\n"
        '  groove: "money"\n'
        "\n"
        '  variation "stack" at bar 2:\n'
        "    add CR at 1\n"
        "    replace HH with CR at 1\n"
    )
    err = _compile_err(src)
    assert err.line == 12, f"expected line 12 (the replace action), got {err.line}"
    assert "already present" in err.message
    rendered = err.render()
    assert "replace HH with CR at 1" in rendered


def test_variation_add_stacking_reports_line() -> None:
    """Regression: an ``add`` action that duplicates an existing hit must
    cite the variation's source line.
    """
    src = (
        'groove "money":\n'
        "  HH: *8\n"
        "  BD: 1, 3\n"
        "  SN: 2, 4\n"
        "\n"
        'section "verse":\n'
        "  bars: 1\n"
        '  groove: "money"\n'
        "\n"
        '  variation "dup" at bar 1:\n'
        "    add BD at 1\n"
    )
    err = _compile_err(src)
    assert err.line == 11, f"expected line 11 (the add action), got {err.line}"
    assert "already present" in err.message


def test_variation_substitute_count_notes_mismatch_reports_line() -> None:
    """Regression: a ``substitute`` whose count/notes lengths differ must
    cite the substitute line, not surface as an unlocated diagnostic.
    """
    src = (
        'groove "g":\n'
        "  BD: 1, 2, 3, 4\n"
        "\n"
        'section "s":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
        "\n"
        '  variation "sub" at bar 1:\n'
        "    count: 1 2\n"
        "    notes: BD, SN, SN\n"
    )
    err = _compile_err(src)
    # The substitute action spans the count/notes pair; parser attaches it
    # at the ``count:`` line.
    assert err.line == 9, f"expected line 9 (the substitute), got {err.line}"


def test_variation_add_flam_on_hihat_reports_line() -> None:
    """Regression: a ``flam`` modifier on an instrument that does not
    support it (e.g. HH) must cite the variation line.
    """
    src = (
        'groove "g":\n'
        "  BD: 1, 3\n"
        "\n"
        'section "s":\n'
        "  bars: 1\n"
        '  groove: "g"\n'
        "\n"
        '  variation "bad" at bar 1:\n'
        "    add HH flam at 2\n"
    )
    err = _compile_err(src)
    assert err.line == 9, f"expected line 9 (the add), got {err.line}"
    assert "flam" in err.message


def test_pattern_line_buzz_on_non_snare_reports_line() -> None:
    """Regression: a ``buzz`` modifier on anything other than the snare
    must cite the pattern line that declared the hit.
    """
    src = (
        'groove "g":\n'
        "  BD: 1\n"
        "  HH: 2 buzz:4\n"
    )
    err = _compile_err(src)
    assert err.line == 3, f"expected line 3 (the HH line), got {err.line}"
    assert "buzz" in err.message


def test_buzz_overlap_with_hand_played_reports_line() -> None:
    """Regression: a snare buzz span that overlaps a hand-played hit
    (e.g. HH) must cite the offending hand-played hit's pattern line.
    """
    src = (
        'groove "g":\n'
        "  SN: 1 buzz:2\n"
        "  HH: 1, 2\n"
    )
    err = _compile_err(src)
    # The overlap error is attributed to the HH line (the thing that
    # conflicts with the pre-existing buzz span), so it should point at
    # line 3, not line 2.
    assert err.line == 3, f"expected line 3 (the HH line), got {err.line}"
    assert "overlap" in err.message
