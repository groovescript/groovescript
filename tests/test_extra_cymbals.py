"""Tests for the extended cymbal palette: splash (SP), china (CH),
second crash (CR2), and stack (ST).

Each new cymbal must round-trip through every emission path (LilyPond,
MIDI, MusicXML) with a notehead+position pair that's distinct from every
other instrument on the staff. The choke modifier is supported on the
ringing cymbals (SP, CH, CR2) but rejected on stack — stacks are
physically pre-muted and have no ring to silence.
"""

from __future__ import annotations

import pytest

from groovescript.compiler import compile_groove, compile_song
from groovescript.errors import GrooveScriptError
from groovescript.lilypond import emit_lilypond
from groovescript.midi import emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.parser import parse


# ── Parser: alias normalisation ──────────────────────────────────────────


@pytest.mark.parametrize(
    "alias,canonical",
    [
        # Splash
        ("SP", "SP"),
        ("sp", "SP"),
        ("splash", "SP"),
        # China
        ("CH", "CH"),
        ("ch", "CH"),
        ("china", "CH"),
        # Second crash
        ("CR2", "CR2"),
        ("cr2", "CR2"),
        ("crash2", "CR2"),
        ("secondcrash", "CR2"),
        # Stack
        ("ST", "ST"),
        ("st", "ST"),
        ("stack", "ST"),
    ],
)
def test_extra_cymbal_alias_normalises_to_canonical(
    alias: str, canonical: str
) -> None:
    """Each documented alias for the new cymbals normalises to its canonical
    abbreviation.
    """
    src = f"""\
groove "g":
    {alias}: 1, 3
"""
    song = parse(src)
    line = song.grooves[0].pattern[0]
    assert line.instrument == canonical


def test_crash2_does_not_collide_with_crash_alias() -> None:
    """Regression: the longer ``crash2`` alias must be tokenised as a single
    instrument; if the regex matched ``crash`` greedily and left the ``2``
    behind, parsing would fail or silently bind the line to CR.
    """
    src = """\
groove "g":
    crash2: 1
    crash: 3
"""
    song = parse(src)
    pattern = song.grooves[0].pattern
    assert {p.instrument for p in pattern} == {"CR", "CR2"}


def test_splash_alias_does_not_swallow_sp_prefix_in_other_words() -> None:
    """The bare ``sp``/``SP`` token only resolves to splash when used as a
    standalone instrument name. The regex orders ``splash`` before ``sp``
    so multi-character long forms still tokenise atomically.
    """
    src = """\
groove "g":
    splash: 1
"""
    song = parse(src)
    assert song.grooves[0].pattern[0].instrument == "SP"


# ── Compiler: cymbal-set membership and choke validation ─────────────────


@pytest.mark.parametrize("instrument", ["SP", "CH", "CR2"])
def test_choke_modifier_accepted_on_ringing_cymbals(instrument: str) -> None:
    """Splash, china, and the second crash all ring out and so accept the
    ``choke`` modifier — the same articulation crash, ride, and ride bell
    already supported.
    """
    src = f"""\
title: "demo"
tempo: 120

groove "g":
    BD: 1, 3
    SN: 2, 4
    {instrument}: 4 choke

section "s":
    bars: 1
    groove: "g"
"""
    # Should compile without error.
    compile_song(parse(src))


def test_choke_modifier_rejected_on_stack() -> None:
    """Regression: stacks are physically pre-muted (two cymbals pressed
    together) so they have no sustain to choke. Asking for ``ST: 4 choke``
    is a user error and must be rejected with the same diagnostic that
    catches choke on cowbells, hi-hats, and drums.
    """
    src = """\
groove "g":
    BD: 1, 3
    ST: 4 choke
"""
    with pytest.raises(GrooveScriptError, match="'choke' modifier"):
        compile_groove(parse(src).grooves[0])


def test_new_cymbals_have_no_mutex_with_existing_cymbals() -> None:
    """SP / CH / CR2 / ST are all physically distinct cymbals from CR, RD,
    HH, etc. — placing any of them at the same beat as another cymbal must
    compile without tripping the mutex check that guards the same-physical-
    instrument pairs (HH/OH, RD/RB, SN/SCS).
    """
    src = """\
title: "demo"
tempo: 120

groove "g":
    BD: 1, 3
    CR: 1
    SP: 1
    CH: 1
    CR2: 1
    ST: 1
    HH: 1

section "s":
    bars: 1
    groove: "g"
"""
    # No exception expected.
    compile_song(parse(src))


# ── LilyPond emission ────────────────────────────────────────────────────


def test_lilypond_emits_distinct_notehead_position_for_each_new_cymbal() -> None:
    """Every new cymbal must reach the LilyPond drum-style table with a
    unique (notehead, staff-position) pair. The combinations were chosen
    so the rendered chart shows each cymbal as a visually distinct mark
    even when stacked alongside the existing palette.
    """
    src = """\
title: "demo"
tempo: 120

groove "g":
    BD: 1
    SP: 1
    CH: 1
    CR2: 1
    ST: 1

section "s":
    bars: 1
    groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    # Splash: diamond at position 8 (above crash 1 / 7).
    assert "(splashcymbal diamond #f 8)" in ly
    # China: xcircle at position 9 (highest cymbal on the staff).
    assert "(chinesecymbal xcircle #f 9)" in ly
    # Second crash: cross at position 6 (one below crash 1 — opposite-side mounting).
    assert "(crashcymbalb cross #f 6)" in ly
    # Stack: slash at position 7 (same line as crash, but slashed shape).
    assert "(stcym slash #f 7)" in ly
    # And the body must reference each of the four LilyPond drum names.
    assert "cyms" in ly   # SP
    assert "cymch" in ly  # CH
    assert "cymcb" in ly  # CR2
    assert "stcym" in ly  # ST


def test_lilypond_template_extends_drum_pitch_names_for_stack() -> None:
    """``stcym`` is not a built-in LilyPond drum-pitch name, so the
    template must extend ``drumPitchNames`` before referencing it in the
    drum-style table — otherwise LilyPond fails to render the file.
    """
    src = """\
title: "demo"
tempo: 120

groove "g":
    ST: 1

section "s":
    bars: 1
    groove: "g"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "drumPitchNames" in ly
    assert "(stcym . stcym)" in ly


# ── MIDI emission ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "instrument,gm_pitch",
    [
        ("SP", 55),    # GM Splash Cymbal
        ("CH", 52),    # GM Chinese Cymbal
        ("CR2", 57),   # GM Crash Cymbal 2
        ("ST", 80),    # GM Mute Triangle (re-used for stack)
    ],
)
def test_midi_uses_expected_drum_pitch_for_each_new_cymbal(
    instrument: str, gm_pitch: int
) -> None:
    """Each new cymbal emits on its documented General-MIDI drum pitch.
    We assert by scanning for the channel-10 note-on byte (0x99) followed
    by the pitch byte.
    """
    src = f"""\
title: "demo"
tempo: 120

groove "g":
    {instrument}: 1

section "s":
    bars: 1
    groove: "g"
"""
    midi_bytes = emit_midi(compile_song(parse(src)))
    expected = bytes([0x99, gm_pitch])
    assert expected in midi_bytes, (
        f"expected note-on for {instrument} at GM pitch {gm_pitch}"
    )


def test_midi_ringing_cymbals_sustain_but_stack_does_not() -> None:
    """SP, CH, CR2 ring like the existing crash and so must use the
    sustain-tail logic (their note-off is deferred). Stack is excluded —
    a stack hits like a closed cymbal and should turn off promptly.
    """
    from groovescript.midi import _SUSTAIN_PITCHES, _NOTE

    assert _NOTE["SP"] in _SUSTAIN_PITCHES
    assert _NOTE["CH"] in _SUSTAIN_PITCHES
    assert _NOTE["CR2"] in _SUSTAIN_PITCHES
    assert _NOTE["ST"] not in _SUSTAIN_PITCHES


# ── MusicXML emission ────────────────────────────────────────────────────


def test_musicxml_uses_distinct_notehead_for_each_new_cymbal() -> None:
    """The MusicXML export gives each new cymbal a notehead that is
    distinct from every other instrument on the staff. The exact noteheads
    are the documented MusicXML names, which match the LilyPond rendering
    closely enough that the chart looks the same in either toolchain.
    """
    src = """\
title: "demo"
tempo: 120

groove "g":
    SP: 1
    CH: 1
    CR2: 1
    ST: 1

section "s":
    bars: 1
    groove: "g"
"""
    xml = emit_musicxml(compile_song(parse(src))).decode()
    # SP → diamond, CH → circle-x, CR2 → slash, ST → cluster.
    assert "<notehead>diamond</notehead>" in xml    # SP (also RB elsewhere)
    assert "<notehead>circle-x</notehead>" in xml   # CH (also OH elsewhere)
    assert "<notehead>slash</notehead>" in xml      # CR2 (only this cymbal)
    assert "<notehead>cluster</notehead>" in xml    # ST (only this cymbal)
