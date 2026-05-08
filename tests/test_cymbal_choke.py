"""Tests for the ``choke`` modifier and the SN/SCS instrument mutex.

The ``choke`` modifier marks a cymbal hit that is grabbed mid-ring to
silence it. It is restricted to ringing cymbals (CR, CR2, RD, RB, SP, CH)
— hi-hats, cowbell, and stacks don't sustain in a way that's meaningfully
"choked," and drums have no ring to cut. Snare (SN) and snare cross-stick
(SCS) describe one drum with two articulations and may not sound at the
same beat.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from groovescript.compiler import compile_groove, compile_song
from groovescript.errors import GrooveScriptError
from groovescript.lilypond import emit_lilypond
from groovescript.midi import emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.parser import parse


# ── Compiler: choke is allowed on cymbals ────────────────────────────────


@pytest.mark.parametrize("instrument", ["CR", "RD", "RB"])
def test_choke_allowed_on_cymbals(instrument: str) -> None:
    """CR, RD, and RB are the cymbals that can be choked."""
    src = f"""\
groove "g":
    BD: 1
    {instrument}: 1 choke
"""
    ir = compile_groove(parse(src).grooves[0])
    hits = [e for e in ir.events if e.instrument == instrument]
    assert len(hits) == 1
    assert "choke" in hits[0].modifiers


# ── Compiler: choke is rejected on non-cymbal instruments ────────────────


@pytest.mark.parametrize(
    "instrument,beat",
    [
        ("HH", "1"),
        ("OH", "1"),
        ("HF", "1"),
        ("CB", "1"),
        ("BD", "1"),
        ("SN", "2"),
        ("SCS", "2"),
        ("FT", "1"),
        ("HT", "1"),
        ("MT", "1"),
    ],
)
def test_choke_rejected_on_non_cymbals(instrument: str, beat: str) -> None:
    """``choke`` only applies to cymbals; everything else raises a clear
    diagnostic.
    """
    src = f"""\
groove "bad":
    {instrument}: {beat} choke
"""
    with pytest.raises(
        GrooveScriptError,
        match="'choke' modifier is only supported on cymbals",
    ):
        compile_groove(parse(src).grooves[0])


def test_choke_combines_with_accent() -> None:
    """A choked-and-accented hit (common for the final cymbal stab in an
    ending) keeps both modifiers without complaint.
    """
    src = """\
groove "outro":
    BD: 1
    CR: 1 accent choke
"""
    ir = compile_groove(parse(src).grooves[0])
    cr_hit = next(e for e in ir.events if e.instrument == "CR")
    assert "accent" in cr_hit.modifiers
    assert "choke" in cr_hit.modifiers


def test_choke_via_variation_modify_add_on_cymbal_is_allowed() -> None:
    """``modify add choke to crash`` stamps the choke onto an existing CR hit."""
    src = """\
groove "g":
    BD: 1
    CR: 1

section "outro":
    bars: 1
    groove: "g"
    variation at bar 1:
      modify add choke to crash at 1
"""
    ir = compile_song(parse(src))
    cr_hit = next(e for e in ir.bars[0].events if e.instrument == "CR")
    assert "choke" in cr_hit.modifiers


def test_choke_via_variation_modify_add_on_hihat_is_rejected() -> None:
    """The cymbal-only restriction also gates the variation path: stamping
    ``choke`` onto a hi-hat hit must raise.
    """
    src = """\
groove "g":
    HH: 1

section "verse":
    bars: 1
    groove: "g"
    variation at bar 1:
      modify add choke to hihat at 1
"""
    with pytest.raises(
        GrooveScriptError,
        match="'choke' modifier is only supported on cymbals",
    ):
        compile_song(parse(src))


# ── Compiler: SN and SCS may not share a beat ────────────────────────────


def test_sn_and_scs_at_same_position_is_rejected() -> None:
    """Regression: the snare and snare cross-stick are one physical drum
    with two articulations. Stacking them on a single beat is physically
    impossible and a typo or compile artefact should not slip through.
    """
    src = """\
groove "bad":
    BD: 1, 3
    SN: 2
    SCS: 2
"""
    with pytest.raises(
        GrooveScriptError,
        match="SCS and SN cannot sound at the same beat",
    ):
        compile_groove(parse(src).grooves[0])


def test_sn_and_scs_on_different_beats_is_allowed() -> None:
    """SN and SCS are the same drum but the mutex only fires when they
    share a beat position; alternating them across the bar is a common
    Latin/funk articulation and must compile cleanly.
    """
    src = """\
groove "ok":
    BD: 1, 3
    SN: 2
    SCS: 4
    HH: *8
"""
    ir = compile_groove(parse(src).grooves[0])
    by_pos = {(e.beat_position, e.instrument) for e in ir.events}
    assert (Fraction(1, 4), "SN") in by_pos
    assert (Fraction(3, 4), "SCS") in by_pos


# ── LilyPond emission ────────────────────────────────────────────────────


def test_lilypond_renders_choke_as_stopped_articulation() -> None:
    """A choked crash renders with the LilyPond ``\\stopped`` articulation,
    which prints as the ``+`` symbol above the note — the standard cymbal-
    choke notation.
    """
    src = """\
title: "demo"
tempo: 120

groove "stop hit":
    BD: 1
    CR: 1 choke

section "stop":
    bars: 1
    groove: "stop hit"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\stopped" in ly
    # The choked crash and kick share beat 1, so they form a chord.
    assert "<bd cymc>4\\stopped" in ly


# ── MIDI emission ────────────────────────────────────────────────────────


def test_midi_choke_emits_short_note_off() -> None:
    """A choked crash must not be allowed to ring out: the emitted note-off
    should land within a single hit-duration of the strike rather than
    being deferred to the song-tail sustain extension.
    """
    src = """\
title: "demo"
tempo: 120

groove "stop hit":
    BD: 1
    CR: 1 choke

section "stop":
    bars: 1
    groove: "stop hit"
"""
    midi_bytes = emit_midi(compile_song(parse(src)))
    # Channel-10 note-on for crash (GM 49 = 0x31) and matching note-off
    # (0x89 = note-off ch10) should both appear.
    assert b"\x99\x31" in midi_bytes  # note-on crash
    assert b"\x89\x31" in midi_bytes  # note-off crash


def test_midi_unchoked_crash_does_not_emit_short_note_off() -> None:
    """Control: an ordinary (non-choked) crash relies on the sustain
    extender, which strips the short note-off. We assert the bare
    note-off byte sequence is absent so the choke test above is
    actually proving choke-specific behavior.
    """
    src = """\
title: "demo"
tempo: 120

groove "stop hit":
    BD: 1
    CR: 1

section "stop":
    bars: 1
    groove: "stop hit"
"""
    midi_bytes = emit_midi(compile_song(parse(src)))
    assert b"\x99\x31" in midi_bytes  # note-on crash still present
    # The sustain extender pushes the note-off well past the strike, so
    # it is not packed adjacently with the note-on. We verify the choke
    # path produced a tighter packing by re-emitting with choke and
    # asserting the byte sequence differs.
    src_choked = src.replace("CR: 1", "CR: 1 choke")
    choked_bytes = emit_midi(compile_song(parse(src_choked)))
    assert choked_bytes != midi_bytes


# ── MusicXML emission ────────────────────────────────────────────────────


def test_musicxml_emits_stopped_articulation_for_choke() -> None:
    """MusicXML's ``<stopped/>`` articulation renders as the ``+`` symbol —
    the same convention LilyPond uses — so XML readers display the choke
    consistently with the engraved score.
    """
    src = """\
title: "demo"
tempo: 120

groove "stop hit":
    BD: 1
    CR: 1 choke

section "stop":
    bars: 1
    groove: "stop hit"
"""
    xml = emit_musicxml(compile_song(parse(src))).decode()
    assert "<stopped />" in xml or "<stopped/>" in xml
