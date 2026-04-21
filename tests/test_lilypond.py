from pathlib import Path

from groovescript.ast_nodes import Fill, FillBar, FillLine, FillPlaceholder, FillPlacement, Groove, Metadata, PatternLine, Section, Song, StarSpec
from groovescript.compiler import compile_groove, compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"

MONEY_BEAT = Groove(
    name="money beat",
    bars=[
        [
            PatternLine(instrument="BD", beats=["1", "3"]),
            PatternLine(instrument="SN", beats=["2", "4"]),
            PatternLine(instrument="HH", beats=StarSpec(note_value=8)),
        ]
    ],
)

MONEY_BEAT_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8
"""

ARRANGEMENT_SRC = """\
metadata:
  title: "Simple Rock"
  tempo: 120
  time_signature: 4/4

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 4
  groove: "money beat"
"""


def _emit_groove(groove: Groove) -> str:
    return emit_lilypond(compile_groove(groove))


def test_emit_lilypond_version():
    ly = _emit_groove(MONEY_BEAT)
    assert '\\version "2.24.0"' in ly


def test_emit_drumstaff():
    ly = _emit_groove(MONEY_BEAT)
    assert "DrumStaff" in ly


def test_emit_drummode():
    ly = _emit_groove(MONEY_BEAT)
    assert "\\drummode" in ly


def test_emit_money_beat_bd_hh_chord():
    ly = _emit_groove(MONEY_BEAT)
    assert "<bd hh>8" in ly


def test_emit_money_beat_sn_hh_chord():
    ly = _emit_groove(MONEY_BEAT)
    assert "<sn hh>8" in ly


def test_emit_money_beat_no_rests():
    ly = _emit_groove(MONEY_BEAT)
    assert "r8" not in ly


def test_emit_rests_when_sparse():
    groove = Groove(
        name="sparse",
        bars=[[PatternLine(instrument="BD", beats=["1"])]],
    )
    ly = _emit_groove(groove)
    assert "bd4" in ly
    assert "r4" in ly


def test_emit_16th_duration():
    groove = Groove(
        name="16th",
        bars=[[PatternLine(instrument="SN", beats=["1"])]],
    )
    ly = _emit_groove(groove)
    assert "sn4" in ly
    assert "r4" in ly


def test_full_pipeline_parse_to_lilypond():
    song = parse(MONEY_BEAT_SRC)
    ly = emit_lilypond(compile_groove(song.grooves[0]))
    assert '\\version "2.24.0"' in ly
    assert "DrumStaff" in ly
    assert "<bd hh>8" in ly
    assert "<sn hh>8" in ly


def test_emit_hihat_at_correct_staff_position():
    ly = _emit_groove(MONEY_BEAT)
    assert "(hihat cross #f 5)" in ly
    assert "(openhihat xcircle #f 5)" in ly
    # Ride cymbal: plain cross notehead on the top line of the staff
    # (position 4), one position below hihat so the two are visually
    # distinguishable when they share a bar.
    assert "(ridecymbal cross #f 4)" in ly
    # Crash cymbal: plain cross notehead one ledger above the staff,
    # distinguished from hihat by staff position rather than notehead shape.
    assert "(crashcymbal cross #f 7)" in ly
    assert "drumStyleTable" in ly


def test_emit_song_header_tempo_and_section_mark():
    song = parse(ARRANGEMENT_SRC)
    ly = emit_lilypond(compile_song(song))
    assert 'title = "Simple Rock"' in ly
    assert 'subtitle = "Tempo: 120    Time Signature: 4/4"' in ly
    # "Made with groovescript" is emitted as a page-footer markup so it
    # appears on every page, not only on the final page (which is how
    # LilyPond renders the built-in ``tagline``).
    assert "tagline = ##f" in ly
    assert 'oddFooterMarkup' in ly and '"Made with groovescript"' in ly
    assert "\\tempo 4 = 120" in ly
    assert "\\time 4/4" in ly
    assert '"INTRO: 4"' in ly


def test_emit_page_numbers_and_tighter_layout():
    song = parse(ARRANGEMENT_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "print-page-number = ##t" in ly
    assert "print-first-page-number = ##t" in ly
    assert "\\fromproperty #'page:page-number-string" in ly
    assert "\\page-ref #'lastPage" in ly
    assert "top-margin = 10\\mm" in ly
    assert "left-margin = 12\\mm" in ly
    assert "indent = 0\\mm" in ly


def test_emit_multiple_bars_for_sections():
    song = Song(
        metadata=Metadata(title="Loop Song"),
        grooves=[MONEY_BEAT],
        sections=[Section(name="intro", bars=2, groove="money beat")],
    )
    ly = emit_lilypond(compile_song(song))
    assert "\\repeat volta 2" in ly


def test_emit_fill_cymc_in_output():
    """A fill bar with CR should produce 'cymc' in the LilyPond output."""
    fill = Fill(
        name="crash fill",
        bars=[
            FillBar(
                label="4",
                lines=[FillLine(beat="4", instruments=["BD", "CR"])],
            )
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[fill],
        sections=[
            Section(
                name="intro",
                bars=2,
                groove="money beat",
                fills=[FillPlacement(fill_name="crash fill", bar=2)],
            )
        ],
    )
    ly = emit_lilypond(compile_song(song))
    assert "cymc" in ly


def test_emit_fill_uses_16th_duration_when_needed():
    """A fill with 16th-note positions should use duration 16."""
    fill = Fill(
        name="16th fill",
        bars=[
            FillBar(
                label="3e",
                lines=[FillLine(beat="3e", instruments=["SN"])],
            )
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[fill],
        sections=[
            Section(
                name="intro",
                bars=2,
                groove="money beat",
                fills=[FillPlacement(fill_name="16th fill", bar=2)],
            )
        ],
    )
    ly = emit_lilypond(compile_song(song))
    assert "16" in ly


def test_emit_fill_parsed_end_to_end():
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "bar 4 fill":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "bar 4 fill" at bar 4 beat 3
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert "cymc" in ly
    assert "sn" in ly


# --- Iteration 4: ghost and accent dynamics ---

from groovescript.ast_nodes import Variation, VariationAction


def test_emit_ghost_note_uses_parenthesize():
    variation = Variation(
        name="ghost",
        bars=[1],
        actions=[VariationAction(action="add", instrument="SN", beats=["2&"], modifiers=["ghost"])],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=1, groove="money beat", variations=[variation])],
    )
    ly = emit_lilypond(compile_song(song))
    assert "\\parenthesize" in ly


def test_emit_accent_note_uses_arrow():
    variation = Variation(
        name="accent",
        bars=[1],
        actions=[VariationAction(action="add", instrument="SN", beats=["1"], modifiers=["accent"])],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=1, groove="money beat", variations=[variation])],
    )
    ly = emit_lilypond(compile_song(song))
    assert "->" in ly


def test_emit_ghost_note_parsed_end_to_end():
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "chorus":
  bars: 2
  groove: "money beat"
  variation "lift" at bar 2:
    add SN ghost at 2&
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert "\\parenthesize" in ly


def test_emit_like_section_repeats_content():
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 2
  groove: "money beat"

section "verse 2":
  like "verse"
"""
    song = parse(src)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    # 4 bars total (2 + 2), each section is a 2-bar repeat
    assert ly.count("\\repeat volta 2") >= 2
    assert '"VERSE: 2"' in ly
    assert '"VERSE 2: 2"' in ly


# --- Ghost note and Consolidation Fixes ---

from fractions import Fraction
from groovescript.compiler import Event
from groovescript.lilypond import _drum_measure


def test_ghost_in_chord():
    # BD and SN at same position, SN is ghost
    events = [
        Event(bar=1, beat_position=Fraction(0), instrument="BD"),
        Event(
            bar=1, beat_position=Fraction(0), instrument="SN", modifiers=["ghost"]
        ),
    ]
    # subdivision 4 (quarter notes)
    ly = _drum_measure(events, 4)
    # Expected: <bd \parenthesize sn>4 r4 r4 r4
    assert "<bd \\parenthesize sn>4" in ly
    assert "\\parenthesize <" not in ly


def test_ghost_and_accent():
    # SN with both ghost and accent
    events = [
        Event(
            bar=1,
            beat_position=Fraction(0),
            instrument="SN",
            modifiers=["ghost", "accent"],
        )
    ]
    ly = _drum_measure(events, 4)
    # Expected: \parenthesize sn4-> r4 r4 r4
    assert "\\parenthesize sn4->" in ly


def test_rest_consolidation():
    # SN on 1, followed by silence in a 16th note grid
    events = [Event(bar=1, beat_position=Fraction(0), instrument="SN")]
    ly = _drum_measure(events, 16)
    assert "sn4" in ly
    assert "r4" in ly


def test_no_consolidation_unaligned():
    # SN on 1e (1/16) should NOT be consolidated to 8th because it starts on 16th boundary
    events = [Event(bar=1, beat_position=Fraction(1, 16), instrument="SN")]
    ly = _drum_measure(events, 16)
    # Expected: r16 sn16 r8 r4 r2
    assert "sn16" in ly
    assert "r16" in ly


def test_emit_repeat_play_x_markup():
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 8
  groove: "money beat"
  repeat: 4
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert '\\repeat volta 4' in ly
    # Section box and "Play 4x" are stacked in a single \column mark at staff-bar
    assert '"VERSE: 8"' in ly
    assert '"Play 4x"' in ly
    assert "break-align-symbols = #'(staff-bar)" in ly


def test_emit_implicit_single_bar_repeat():
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 4
  groove: "money beat"
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    # 4 identical bars should be collapsed into a repeat
    assert '\\repeat volta 4' in ly


def test_emit_repeat_respects_phrase_boundaries():
    src = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "turnaround":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 8
  groove: "money beat"
  fill "turnaround" at bar 8 beat 3
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    # Bars 1-4 should be \repeat volta 4
    # Bars 5-7 should be \repeat volta 3
    # Bar 8 is the fill
    assert '\\repeat volta 4' in ly
    assert '\\repeat volta 3' in ly
    assert '"Play 4x"' in ly
    assert '"Play 3x"' in ly


def test_forced_opening_repeat():
    # Case 1: Song starts with a repeat
    src = """groove "m":
    BD: 1
section "i":
  bars: 2
  groove: "m"
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert '\\bar ".|:"' in ly

    # Case 2: Song starts with a single bar (no repeat)
    src = """groove "m":
    BD: 1
section "i":
  bars: 1
  groove: "m"
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert '\\bar ".|:"' not in ly


def test_label_order_in_column():
    src = """groove "m":
    BD: 1
section "verse":
  bars: 8
  groove: "m"
  repeat: 4
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    # Section box and "Play 4x" are in a single \column; box appears first in the string
    assert '"VERSE: 8"' in ly
    assert '"Play 4x"' in ly
    box_pos = ly.index('"VERSE: 8"')
    play_pos = ly.index('"Play 4x"')
    assert box_pos < play_pos, "Section box should come before Play Nx in the markup"


# --- Iteration 6: flam / drag / open hi-hat ---

from groovescript.ast_nodes import BeatHit, InstrumentHit
from groovescript.compiler import compile_fill_bar
from groovescript.lilypond import _drum_measure, _is_triplet_only


def test_emit_flam_grace_note():
    """A SN flam should emit \\slashedGrace sn16 before the main note.

    Regression test: previously emitted \\acciaccatura, which auto-adds a slur
    from the grace note to the main note. When the grace pitch matched a pitch
    in the main chord (e.g. snare flam into a snare+hat chord), the slur
    rendered as a spurious tie. \\slashedGrace gives a slashed grace head with
    no slur.
    """
    events = [
        Event(bar=1, beat_position=Fraction(0), instrument="SN", modifiers=["flam"]),
    ]
    ly = _drum_measure(events, 8)
    assert "\\slashedGrace sn16" in ly
    assert "\\acciaccatura" not in ly


def test_emit_flam_on_toms():
    """Regression: flam is supported on all toms (FT, HT, MT), not only SN.

    Each tom flam should emit \\slashedGrace <ly_name>16 before the main note.
    """
    for instrument, ly_name in (("FT", "tomfh"), ("HT", "tomh"), ("MT", "tommh")):
        events = [
            Event(bar=1, beat_position=Fraction(0), instrument=instrument, modifiers=["flam"]),
        ]
        ly = _drum_measure(events, 4)
        assert f"\\slashedGrace {ly_name}16" in ly, f"{instrument} flam should produce grace note"


def test_emit_drag_grace_cluster():
    """A SN with drag modifier should emit \\grace { sn16 sn16 } before the main note."""
    events = [
        Event(bar=1, beat_position=Fraction(0), instrument="SN", modifiers=["drag"]),
    ]
    ly = _drum_measure(events, 8)
    assert "\\grace { sn16 sn16 }" in ly


def test_emit_open_hihat_uses_hho():
    """OH should map to 'hho' (LilyPond open hi-hat note name)."""
    events = [Event(bar=1, beat_position=Fraction(0), instrument="OH")]
    ly = _drum_measure(events, 8)
    assert "hho" in ly




def test_emit_flam_on_groove_end_to_end():
    src = """\
groove "flam groove":
    SN: 1 flam, 3
    BD: 2, 4
    HH: *8

section "intro":
  bars: 2
  groove: "flam groove"
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert "\\slashedGrace sn16" in ly


def test_emit_flam_on_fill_end_to_end():
    src = """\
groove "beat":
    HH: *8

fill "flam fill":
  count "3 e & a 4":
    3: SN flam
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 2
  groove: "beat"
  fill "flam fill" at bar 2 beat 3
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert "\\slashedGrace sn16" in ly


def test_emit_fixture_modifiers():
    """modifiers_and_srs.gs should compile to LilyPond with grace notes and accents."""
    song = parse_file(str(FIXTURES / "modifiers_and_srs.gs"))
    ly = emit_lilypond(compile_song(song))
    assert "\\slashedGrace sn16" in ly
    assert "\\grace { sn16 sn16 }" in ly
    assert "->" in ly   # accent on SN backbeat and OH


# --- Iteration 7: triplet notation ---

def test_is_triplet_only():
    assert not _is_triplet_only(Fraction(0))         # beat 1 — on both grids
    assert _is_triplet_only(Fraction(1, 12))          # triplet position
    assert _is_triplet_only(Fraction(7, 12))          # beat 3t
    assert not _is_triplet_only(Fraction(1, 2))       # beat 3 — on both grids
    assert not _is_triplet_only(Fraction(3, 4))       # beat 4 — on both grids


def test_emit_triplet_fill_uses_tuplet():
    """A bar with a triplet fill should have \\tuplet 3/2 in the output."""
    events = [
        # Straight groove beats 1-2
        Event(bar=4, beat_position=Fraction(0), instrument="BD"),
        Event(bar=4, beat_position=Fraction(0), instrument="HH"),
        Event(bar=4, beat_position=Fraction(1, 8), instrument="HH"),
        Event(bar=4, beat_position=Fraction(1, 4), instrument="SN"),
        Event(bar=4, beat_position=Fraction(1, 4), instrument="HH"),
        Event(bar=4, beat_position=Fraction(3, 8), instrument="HH"),
        # Triplet fill on beat 3
        Event(bar=4, beat_position=Fraction(1, 2), instrument="SN"),
        Event(bar=4, beat_position=Fraction(7, 12), instrument="SN"),
        Event(bar=4, beat_position=Fraction(2, 3), instrument="SN"),
        # Straight beat 4
        Event(bar=4, beat_position=Fraction(3, 4), instrument="BD"),
    ]
    ly = _drum_measure(events, 12)
    assert "\\tuplet 3/2 {" in ly
    # Straight notes before beat 3 use 8th durations
    assert "<bd hh>8" in ly
    # Quarter note at beat 4
    assert "bd4" in ly


def test_emit_triplet_fill_fills_bar():
    """The mixed bar should fill exactly 4/4."""
    events = [
        Event(bar=4, beat_position=Fraction(0), instrument="BD"),
        Event(bar=4, beat_position=Fraction(0), instrument="HH"),
        Event(bar=4, beat_position=Fraction(1, 8), instrument="HH"),
        Event(bar=4, beat_position=Fraction(1, 4), instrument="SN"),
        Event(bar=4, beat_position=Fraction(1, 4), instrument="HH"),
        Event(bar=4, beat_position=Fraction(3, 8), instrument="HH"),
        Event(bar=4, beat_position=Fraction(1, 2), instrument="SN"),
        Event(bar=4, beat_position=Fraction(7, 12), instrument="SN"),
        Event(bar=4, beat_position=Fraction(2, 3), instrument="SN"),
        Event(bar=4, beat_position=Fraction(3, 4), instrument="BD"),
    ]
    ly = _drum_measure(events, 12)
    # Should have exactly the expected pattern
    assert ly == "<bd hh>8 hh8 <sn hh>8 hh8 \\tuplet 3/2 { sn8 sn8 sn8 } bd4"


def test_emit_fixture_iteration7():
    """triplets.gs should emit \\tuplet 3/2 for the triplet fill bar."""
    song = parse_file(str(FIXTURES / "triplets.gs"))
    ly = emit_lilypond(compile_song(song))
    assert "\\tuplet 3/2 {" in ly
    # The non-fill bars are straight 8th notes
    assert "<bd hh>8" in ly


# ---------------------------------------------------------------------------
# Iteration 8 — Additional time signatures
# ---------------------------------------------------------------------------

THREE_FOUR_SRC = """\
title: "Waltz"
tempo: 120
time_signature: 3/4

groove "waltz":
    BD: 1
    SN: 2, 3
    HH: *8

section "A":
  bars: 4
  groove: "waltz"
"""

SIX_EIGHT_SRC = """\
title: "Compound"
tempo: 80
time_signature: 6/8

groove "compound":
    BD: 1, 4
    SN: 3, 6
    HH: *8

section "A":
  bars: 4
  groove: "compound"
"""


def test_emit_3_4_time_signature():
    """\\time 3/4 should appear in the LilyPond output."""
    song = parse(THREE_FOUR_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "\\time 3/4" in ly


def test_emit_3_4_tempo_uses_quarter():
    """\\tempo 4 = N for 3/4 (quarter-note beat)."""
    song = parse(THREE_FOUR_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "\\tempo 4 = 120" in ly


def test_emit_3_4_bd_quarter():
    """BD alone on beat 1 of 3/4 (no HH) should consolidate to a quarter note (bd4)."""
    src = """\
title: "Waltz No HH"
tempo: 120
time_signature: 3/4

groove "waltz no hh":
    BD: 1
    SN: 2, 3

section "A":
  bars: 4
  groove: "waltz no hh"
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert "bd4" in ly


def test_emit_3_4_hh_eighth():
    """HH * in 3/4 sub=6 means 6 eighth notes — at least hh8 should appear."""
    song = parse(THREE_FOUR_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "hh8" in ly


def test_emit_6_8_time_signature():
    song = parse(SIX_EIGHT_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "\\time 6/8" in ly


def test_emit_6_8_tempo_uses_eighth():
    """\\tempo 8 = N for 6/8 (eighth-note beat)."""
    song = parse(SIX_EIGHT_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "\\tempo 8 = 80" in ly


# ---------------------------------------------------------------------------
# Iteration 9 — Cue markup
# ---------------------------------------------------------------------------

CUE_SRC = """\
title: "Cue Song"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 8
  groove: "money beat"
  cue "Vocals in" at bar 1
  cue "Bridge" at bar 5 beat 1
"""

BAR_TEXT_SRC = """\
title: "Bar Text Song"
tempo: 100

groove "annotated":
    bar 1:
      text: "Feel it"
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 2&, 4
      SN: 2, 4
      HH: *8

section "A":
  bars: 4
  groove: "annotated"
"""


def test_emit_cue_markup_in_output():
    """Cue text should appear in the LilyPond output."""
    song = parse(CUE_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "Vocals in" in ly


def test_emit_cue_markup_is_italic():
    """Cues should be rendered with \\italic markup."""
    song = parse(CUE_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "\\italic" in ly


def test_emit_cue_beat_placement():
    """Cue 'Bridge' at bar 5 beat 1 should be placed as inline markup."""
    song = parse(CUE_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "Bridge" in ly


def test_emit_bar_text_markup():
    """bar_text annotation should appear in LilyPond output as a \\mark."""
    song = parse(BAR_TEXT_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "Feel it" in ly


def test_emit_bar_text_merged_into_section_mark():
    """When bar_text lands on the first bar of a section, both the section box
    and the bar_text must be merged into a single \\mark command to avoid
    LilyPond's 'conflicting ad-hoc-mark-event' warning (regression test)."""
    song = parse(BAR_TEXT_SRC)
    ly = emit_lilypond(compile_song(song))
    # Find the section mark line — it must contain both the section box and
    # the bar_text in a single \mark \markup \column.
    mark_lines = [
        line.strip()
        for line in ly.splitlines()
        if line.strip().startswith(r"\mark")
    ]
    # The first \mark should be the merged section mark containing both "A: 4"
    # (the section box) and "Feel it" (the bar_text).
    section_marks = [m for m in mark_lines if "A: 4" in m]
    assert len(section_marks) == 1, f"Expected exactly one section mark, got: {section_marks}"
    merged = section_marks[0]
    assert "Feel it" in merged, (
        f"bar_text 'Feel it' should be merged into the section mark, got: {merged}"
    )
    assert merged.count(r"\mark ") == 1, (
        f"Section mark line should contain exactly one \\mark command, got: {merged}"
    )


# ---------------------------------------------------------------------------
# Iteration 11 — Per-section tempo changes
# ---------------------------------------------------------------------------

SECTION_TEMPO_SRC = """\
title: "Tempo Changes"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 4
  groove: "money beat"

section "breakdown":
  bars: 4
  groove: "money beat"
  tempo: 80

section "outro":
  bars: 4
  groove: "money beat"
"""


def test_emit_global_tempo_in_first_section_mark():
    """Global tempo should appear in the first section's mark."""
    song = parse(SECTION_TEMPO_SRC)
    ly = emit_lilypond(compile_song(song))
    assert '"INTRO: 4"' in ly
    assert "= 120" in ly


def test_emit_section_tempo_change_emits_new_tempo_command():
    """A section with a different tempo should emit a \\tempo command."""
    song = parse(SECTION_TEMPO_SRC)
    ly = emit_lilypond(compile_song(song))
    assert "\\tempo 4 = 80" in ly


def test_emit_section_tempo_shown_in_section_mark():
    """The new tempo should be displayed in the breakdown section's mark."""
    song = parse(SECTION_TEMPO_SRC)
    ly = emit_lilypond(compile_song(song))
    breakdown_pos = ly.index('"BREAKDOWN: 4"')
    # The tempo "= 80" should appear near the breakdown section mark
    tempo_80_pos = ly.index("= 80")
    assert abs(breakdown_pos - tempo_80_pos) < 500


def test_emit_section_tempo_restored_emits_new_tempo():
    """When outro reverts to global tempo (120), a \\tempo 4 = 120 should be emitted."""
    song = parse(SECTION_TEMPO_SRC)
    ly = emit_lilypond(compile_song(song))
    # There should be two \tempo 4 = 120 occurrences: one in prelude, one at outro
    assert ly.count("\\tempo 4 = 120") >= 2


def test_emit_section_same_tempo_no_duplicate_tempo_cmd():
    """Consecutive sections with the same tempo should not emit a duplicate \\tempo."""
    src = """\
title: "Same Tempo"
tempo: 120

groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 2
  groove: "beat"

section "verse":
  bars: 2
  groove: "beat"
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    # Only one \\tempo 4 = 120 should be emitted (in the prelude)
    assert ly.count("\\tempo 4 = 120") == 1


def test_emit_section_tempo_without_global_tempo():
    """A section tempo should be emitted even when there is no global tempo."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 2
  groove: "beat"
  tempo: 95
"""
    song = parse(src)
    ly = emit_lilypond(compile_song(song))
    assert "\\tempo 4 = 95" in ly
    assert "\\omit Score.MetronomeMark" in ly


def test_emit_all_supported_instruments():
    """Verify every instrument in the grammar is mapped to a valid LilyPond note."""
    from groovescript.lilypond import _INSTRUMENT_TO_LY
    # Instruments from grammar.lark: BD, SN, SCS, HH, OH, RD, CR, FT, HT, MT, HF
    instruments = ["BD", "SN", "SCS", "HH", "OH", "RD", "CR", "FT", "HT", "MT", "HF"]

    for inst in instruments:
        assert inst in _INSTRUMENT_TO_LY, f"Instrument {inst} not found in _INSTRUMENT_TO_LY"

        # Create a minimal groove with this instrument
        groove = Groove(
            name=f"test_{inst}",
            bars=[[PatternLine(instrument=inst, beats=["1"])]],
        )
        ly = _emit_groove(groove)
        ly_note = _INSTRUMENT_TO_LY[inst]
        assert ly_note in ly, f"LilyPond note '{ly_note}' for instrument {inst} not found in output"


# ---------------------------------------------------------------------------
# Section arrangement: play: block — LilyPond tests
# ---------------------------------------------------------------------------

from fractions import Fraction as _Frac

from groovescript.ast_nodes import PlayBar, PlayGroove, PlayRest
from groovescript.compiler import IRBar


def _make_ir_bar(number, events, subdivision=8, is_rest=False, section_name=None, section_bars=None):
    return IRBar(
        number=number,
        subdivision=subdivision,
        events=events,
        section_name=section_name,
        section_bars=section_bars,
        is_rest=is_rest,
    )


PLAY_BLOCK_SONG_SRC = """\
title: "Play Block Test"
tempo: 120
time_signature: 4/4

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "crash":
  count "4":
    4: BD, CR

section "verse":
  play:
    groove "money beat" x2
    bar "fill bar":
      BD: 1, 3
      SN: 4
      CR: 1
    rest x1
    groove "money beat" x2
    bar "fill bar" x1
  fill "crash" at bar 3
"""


def test_emit_play_block_song_parses_and_compiles():
    from groovescript.parser import parse
    song = parse(PLAY_BLOCK_SONG_SRC)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert '\\version "2.24.0"' in ly
    assert len(ir.bars) == 7  # 2 + 1 + 1 + 2 + 1


def test_emit_whole_bar_rest_renders_R1_in_4_4():
    from groovescript.parser import parse
    song = parse(PLAY_BLOCK_SONG_SRC)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "R1" in ly


def test_emit_play_block_song_section_mark_present():
    from groovescript.parser import parse
    song = parse(PLAY_BLOCK_SONG_SRC)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "VERSE" in ly


def test_emit_rest_bar_not_merged_with_groove_bars():
    """A rest bar should never be merged into a \repeat block with non-rest bars."""
    from groovescript.compiler import Event
    from groovescript.compiler import IRSong, IRSection
    from groovescript.ast_nodes import Metadata

    groove_events = [
        Event(bar=1, beat_position=_Frac(0), instrument="BD"),
        Event(bar=1, beat_position=_Frac(1, 4), instrument="HH"),
    ]
    bars = [
        _make_ir_bar(1, groove_events, section_name="verse", section_bars=3),
        _make_ir_bar(2, [], is_rest=True),
        _make_ir_bar(3, groove_events),
    ]
    ir = IRSong(metadata=Metadata(time_signature="4/4"), bars=bars, sections=[])
    ly = emit_lilypond(ir)
    assert "R1" in ly
    # The groove bars before and after the rest must not be collapsed into one repeat
    assert ly.count("R1") == 1


def test_emit_fixture_play_block():
    """play_block.gs fixture compiles and emits valid LilyPond."""
    from groovescript.parser import parse_file
    song = parse_file(str(FIXTURES / "play_block.gs"))
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "R1" in ly
    assert "VERSE" in ly.upper()


def test_emit_fixture_play_inline_groove():
    """play_inline_groove.gs exercises single-bar, multi-bar, and extend: inline grooves."""
    from groovescript.parser import parse_file
    song = parse_file(str(FIXTURES / "play_inline_groove.gs"))
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\score" in ly
    # Section has: "verse" x2 (1 bar) + inline x2 (1 bar) + inline x1 (1 bar)
    # + multi-bar inline x2 (2 bars) + extend inline x2 (1 bar)
    # + named inline "tom groove" x1 (1 bar) + named ref x2 (1 bar) + rest x1
    # = 2 + 2 + 1 + 4 + 2 + 1 + 2 + 1 = 15 bars
    assert len(ir.bars) == 15


# ── Fill placeholder rendering tests ────────────────────────────────────────

def _make_placeholder_song(placeholder: FillPlaceholder, bars: int = 4) -> Song:
    return Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[
            Section(
                name="verse",
                bars=bars,
                groove="money beat",
                fill_placeholders=[placeholder],
            )
        ],
    )


def test_placeholder_label_appears_in_output():
    """The placeholder label text should appear somewhere in the LilyPond output."""
    song = _make_placeholder_song(FillPlaceholder(label="fill", bar=1))
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert '"fill"' in ly


def test_placeholder_uses_box_markup():
    """Placeholder annotations use \\box markup, not \\italic."""
    song = _make_placeholder_song(FillPlaceholder(label="fill", bar=1))
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\box" in ly


def test_placeholder_custom_label_appears():
    song = _make_placeholder_song(FillPlaceholder(label="big build", bar=2))
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert '"big build"' in ly


def test_placeholder_does_not_suppress_events():
    """Groove events should still be present in the measure containing the placeholder."""
    song = _make_placeholder_song(FillPlaceholder(label="fill", bar=1))
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    # HH on every 8th means 'hh' appears; BD and SN also rendered
    assert "hh" in ly
    assert "bd" in ly


def test_placeholder_groove_still_rendered_not_replaced():
    """Unlike a real fill, a placeholder must NOT remove groove events from the bar."""
    song_with_placeholder = _make_placeholder_song(FillPlaceholder(label="fill", bar=1))
    song_without = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=4, groove="money beat")],
    )
    ir_ph = compile_song(song_with_placeholder)
    ir_no = compile_song(song_without)
    # The event count for bar 1 should be identical
    assert len(ir_ph.bars[0].events) == len(ir_no.bars[0].events)


def test_placeholder_from_source_round_trip():
    """Parse a source string with a fill placeholder and verify the label renders."""
    from groovescript.parser import parse
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 4
  groove: "beat"
  fill placeholder "build" at bar 4
"""
    ir = compile_song(parse(src))
    ly = emit_lilypond(ir)
    assert '"build"' in ly
    assert "\\box" in ly


# ── 12/8 emission ─────────────────────────────────────────────────────────


TWELVE_EIGHT_LY_SRC = """\
title: "12/8"
tempo: 100
time_signature: 12/8

groove "shuffle":
    BD: 1, 7
    SN: 4, 10
    HH: *8

section "A":
  bars: 2
  groove: "shuffle"
"""


def test_emit_12_8_time_signature():
    ly = emit_lilypond(compile_song(parse(TWELVE_EIGHT_LY_SRC)))
    assert "\\time 12/8" in ly


def test_emit_12_8_tempo_on_eighth_note():
    """A 12/8 song's tempo line uses the eighth-note beat unit."""
    ly = emit_lilypond(compile_song(parse(TWELVE_EIGHT_LY_SRC)))
    assert "\\tempo 8 = 100" in ly


def test_emit_12_8_whole_bar_rest_uses_generic_form():
    """A whole-bar rest in 12/8 emits R8*12, not R1 or R2."""
    from groovescript.lilypond import _whole_bar_rest
    assert _whole_bar_rest(12, 8) == "R8*12"
    # 10/8 → R8*10, 11/8 → R8*11
    assert _whole_bar_rest(10, 8) == "R8*10"
    assert _whole_bar_rest(11, 8) == "R8*11"
    # Common meters still use the compact form.
    assert _whole_bar_rest(4, 4) == "R1"
    assert _whole_bar_rest(3, 4) == "R2."
    assert _whole_bar_rest(6, 8) == "R2."


# ── mid-staff time signature changes ──────────────────────────────────────


MIXED_METER_SRC = """\
title: "Mixed"
tempo: 120
time_signature: 4/4

groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "waltz":
    BD: 1
    SN: 2, 3
    HH: *8

section "verse":
  bars: 2
  groove: "rock"

section "outro":
  bars: 2
  groove: "waltz"
  time_signature: 3/4
"""


def test_emit_mid_staff_time_change_emits_new_time_command():
    ly = emit_lilypond(compile_song(parse(MIXED_METER_SRC)))
    # Both the initial 4/4 and the mid-staff 3/4 should appear.
    assert "\\time 4/4" in ly
    assert "\\time 3/4" in ly
    # The 3/4 command should be emitted after the verse (later in the text).
    idx_44 = ly.index("\\time 4/4")
    idx_34 = ly.index("\\time 3/4")
    assert idx_34 > idx_44


def test_emit_mid_staff_time_change_retriggers_tempo_denominator():
    """When the meter changes to 3/4, the re-emitted \\tempo command must use
    the new beat unit (quarter-note) rather than the old one."""
    # Use different per-section tempos so the \tempo commands are actually emitted.
    src = MIXED_METER_SRC.replace(
        "section \"outro\":\n  bars: 2\n  groove: \"waltz\"\n  time_signature: 3/4",
        "section \"outro\":\n  bars: 2\n  groove: \"waltz\"\n  tempo: 90\n  time_signature: 3/4",
    )
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\tempo 4 = 120" in ly
    assert "\\tempo 4 = 90" in ly


def test_parse_file_fixture_mixed_meter():
    song = parse_file(str(FIXTURES / "mixed_meter.gs"))
    assert song.sections[1].time_signature == "7/8"
    assert song.sections[2].time_signature == "3/4"


# ---------------------------------------------------------------------------
# Mixed subdivision (triplet + straight) LilyPond emission
# ---------------------------------------------------------------------------


def test_emit_mixed_triplet_and_eighth():
    """Regression test: a bar with both triplet and 8th-note content emits valid LilyPond.

    Beats 1-2 use straight 8ths, beats 3-4 use triplets.
    """
    src = """\
groove "mixed":
    BD: 1, 3
    HH: 1&, 2&
    SN: 3t, 3l, 4t, 4l
"""
    ir = compile_groove(parse(src).grooves[0])
    ly = emit_lilypond(ir)
    # The bar should use the mixed emitter with \tuplet 3/2 for triplet beats
    assert "\\tuplet 3/2" in ly
    # Straight beats should still appear
    assert "bd" in ly


def test_emit_mixed_triplet_and_sixteenth():
    """Regression test: a bar with both triplet and 16th-note content emits valid LilyPond.

    Beat 1 has 16th notes, beat 3 has triplets.
    """
    src = """\
groove "mixed16":
    BD: 1, 1e, 1&, 1a
    SN: 3t, 3l
"""
    ir = compile_groove(parse(src).grooves[0])
    ly = emit_lilypond(ir)
    # 16th notes in straight beats
    assert "16" in ly
    # Triplet beats
    assert "\\tuplet 3/2" in ly


def test_emit_mixed_subdivision_full_song():
    """End-to-end: a song with mixed-subdivision groove compiles to valid LilyPond."""
    src = """\
metadata:
  title: "Mixed Test"
  tempo: 120

groove "mixed":
    BD: 1, 3
    SN: 2, 4
    HH: 1, 1&, 2, 2&
    SN: 3t, 3l, 4t, 4l

section "verse":
  bars: 2
  groove: "mixed"
"""
    song = parse(src)
    ir = compile_song(song)
    ly = emit_lilypond(ir)
    assert "\\tuplet 3/2" in ly
    # Should compile without errors and contain valid structure
    assert "\\drummode" in ly


# ── Security regression: LilyPond string-breakout / Scheme injection ─────────
#
# User-supplied metadata / cue / bar-text / fill-placeholder / section-name
# strings are interpolated into LilyPond ``"..."`` literals in the emitted
# ``.ly``. LilyPond has no sandbox, so an unescaped ``"`` or ``\`` lets the
# user close the string and run arbitrary LilyPond — including Scheme
# ``#(system ...)`` — at render time. The emitter must escape backslash
# and double-quote in every interpolated user string.


def _header_title_line(ly: str) -> str:
    for line in ly.splitlines():
        stripped = line.strip()
        if stripped.startswith("title ="):
            return stripped
    raise AssertionError("no title line in emitted LilyPond")


def test_title_escapes_backslash_and_quote_to_block_scheme_injection():
    """Regression: a malicious title cannot break out of the LilyPond string.

    Before the fix, ``title = "{title}"`` was emitted with no escaping at
    all — a ``"`` in the user string closed the LilyPond header and the
    remainder was parsed as LilyPond (and Scheme), giving full RCE when
    the user ran ``lilypond`` on the output.
    """
    src = (
        'title: "evil\\" } #(system \\"touch /tmp/pwned\\") \\\\header { x = \\""\n'
        '\n'
        'groove "g":\n'
        '    BD: 1, 3\n'
        '    SN: 2, 4\n'
        '\n'
        'section "s":\n'
        '  bars: 1\n'
        '  groove: "g"\n'
    )
    ir = compile_song(parse(src))
    ly = emit_lilypond(ir)
    title_line = _header_title_line(ly)
    # The emitted title must still be a single, well-formed LilyPond string
    # literal: it starts and ends with ``"``, and every interior ``"`` is
    # escaped with a backslash (and every ``\`` is itself escaped). Walking
    # the body left-to-right and stepping over ``\x`` escape pairs, no raw
    # ``"`` may appear — if one did, an attacker string could close the
    # literal and the remainder would be parsed as LilyPond/Scheme.
    inner = title_line[len('title ='):].strip()
    assert inner.startswith('"') and inner.endswith('"'), title_line
    body = inner[1:-1]
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            assert i + 1 < len(body), f"trailing backslash in {title_line!r}"
            i += 2
            continue
        assert c != '"', f"unescaped quote in {title_line!r}"
        i += 1


def test_cue_bar_text_and_placeholder_escape_backslash_and_quote():
    """Regression: cue / bar-text / fill-placeholder text can't break out either.

    These sites previously used ``.replace('"', '\\"')`` only, which is
    unsafe when the user string contains a ``\\``: a trailing ``\\`` turns
    the emitter's ``\\"`` into an escaped-quote inside the LilyPond string,
    so the string runs until the next ``"`` in the template.
    """
    src = (
        'groove "g":\n'
        '    bar 1:\n'
        '      BD: 1, 3\n'
        '      SN: 2, 4\n'
        '      text: "bt\\\\x\\"y"\n'
        '\n'
        'section "s":\n'
        '  bars: 1\n'
        '  groove: "g"\n'
        '  cue "ev\\\\il\\"cue" at bar 1\n'
        '  fill placeholder "ph\\\\l\\"q" at bar 1\n'
    )
    ir = compile_song(parse(src))
    ly = emit_lilypond(ir)
    # The raw (unescaped) payload strings carry a literal ``\`` followed by a
    # character the user controls. After a correct escape, every ``\`` in the
    # user text is doubled to ``\\``, so the raw payload substring never
    # appears verbatim in the emitted .ly. Before the fix, ``\`` wasn't
    # escaped and these substrings appeared directly.
    for payload in ("ev\\il", "bt\\x", "ph\\l"):
        assert payload not in ly, f"unescaped payload {payload!r} leaked into .ly"


def test_section_name_escapes_special_characters():
    """Regression: section name is uppercased and pasted into a rehearsal-mark
    string. It must be escaped the same way as other user strings."""
    src = (
        'groove "g":\n'
        '    BD: 1, 3\n'
        '    SN: 2, 4\n'
        '\n'
        'section "a\\\\b\\"c":\n'
        '  bars: 1\n'
        '  groove: "g"\n'
    )
    ir = compile_song(parse(src))
    ly = emit_lilypond(ir)
    # Raw (unescaped) backslash-quote pattern from the section name must not
    # appear in the rehearsal-mark string.
    assert 'A\\B"C' not in ly
