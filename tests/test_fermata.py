"""Tests for the ``fermata`` modifier.

A fermata (𝄐) marks a hit the player should sustain longer than written;
it is most commonly used on the final note of a section or piece. It is
purely notational — it appears in LilyPond and MusicXML output but does
not change MIDI playback. Unlike ``choke`` it has no instrument
restrictions, and unlike ``buzz`` / ``flam`` / ``drag`` it composes with
every other modifier.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from groovescript.compiler import compile_groove, compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.midi import emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.parser import parse


# ── Compiler: fermata is allowed on every instrument ─────────────────────


@pytest.mark.parametrize(
    "instrument", ["BD", "SN", "HH", "OH", "RD", "RB", "CR", "CB", "FT", "HT", "MT", "HF", "SCS"]
)
def test_fermata_allowed_on_every_instrument(instrument: str) -> None:
    """``fermata`` is an unrestricted articulation: any drum or cymbal can
    be held under a fermata regardless of whether it sustains naturally.
    """
    src = f"""\
groove "g":
    {instrument}: 1 fermata
"""
    ir = compile_groove(parse(src).grooves[0])
    hits = [e for e in ir.events if e.instrument == instrument]
    assert len(hits) == 1
    assert "fermata" in hits[0].modifiers


def test_fermata_combines_with_accent_and_choke() -> None:
    """A held, accented, choked crash (a common dramatic ending) keeps
    every modifier through compilation.
    """
    src = """\
groove "ending":
    BD: 1
    CR: 1 accent choke fermata
"""
    ir = compile_groove(parse(src).grooves[0])
    cr_hit = next(e for e in ir.events if e.instrument == "CR")
    assert {"accent", "choke", "fermata"}.issubset(cr_hit.modifiers)


def test_fermata_combines_with_flam() -> None:
    """A flammed snare under a fermata: grace stroke plus a held main hit."""
    src = """\
groove "ending":
    SN: 4 flam fermata
"""
    ir = compile_groove(parse(src).grooves[0])
    sn_hit = next(e for e in ir.events if e.instrument == "SN")
    assert "flam" in sn_hit.modifiers
    assert "fermata" in sn_hit.modifiers


def test_fermata_combines_with_buzz() -> None:
    """A buzz roll terminated by a fermata is a standard ending; the buzz
    modifier-compatibility check must not reject this combination.
    """
    src = """\
groove "roll-out":
    BD: 1
    SN: 4 buzz fermata
"""
    ir = compile_groove(parse(src).grooves[0])
    sn_hit = next(e for e in ir.events if e.instrument == "SN")
    assert "buzz" in sn_hit.modifiers
    assert "fermata" in sn_hit.modifiers


def test_fermata_via_variation_modify_add() -> None:
    """``modify add fermata to crash`` stamps the fermata onto an existing
    CR hit at the named beat without re-stating instrument or position.
    """
    src = """\
groove "g":
    BD: 1
    CR: 1

section "end":
    bars: 1
    groove: "g"
    variation at bar 1:
      modify add fermata to crash at 1
"""
    ir = compile_song(parse(src))
    cr_hit = next(e for e in ir.bars[0].events if e.instrument == "CR")
    assert "fermata" in cr_hit.modifiers


# ── LilyPond emission ────────────────────────────────────────────────────


def test_lilypond_renders_fermata_articulation() -> None:
    """A held crash renders with the LilyPond ``\\fermata`` articulation,
    which prints as the standard fermata symbol above the note.
    """
    src = """\
title: "demo"
tempo: 120

groove "end":
    BD: 1
    CR: 1 fermata

section "end":
    bars: 1
    groove: "end"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "\\fermata" in ly
    # BD + CR share beat 1, so they form a chord with fermata after.
    assert "<bd cymc>4\\fermata" in ly


def test_lilypond_fermata_after_accent() -> None:
    """Articulation ordering: ``\\fermata`` follows the accent marker so a
    note carrying both reads ``->\\fermata``.
    """
    src = """\
title: "demo"
tempo: 120

groove "end":
    SN: 4 accent fermata

section "end":
    bars: 1
    groove: "end"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "->\\fermata" in ly


def test_lilypond_fermata_on_buzz_roll() -> None:
    """A buzz roll under a fermata: the ``\\fermata`` token attaches to
    the buzz token after the ``:32`` tremolo marker.
    """
    src = """\
title: "demo"
tempo: 120

groove "roll-end":
    SN: 1 buzz fermata

section "end":
    bars: 1
    groove: "roll-end"
"""
    ly = emit_lilypond(compile_song(parse(src)))
    assert "sn4:32\\fermata" in ly


# ── MIDI emission: fermata is notation-only ──────────────────────────────


def test_midi_fermata_does_not_change_output() -> None:
    """Regression: ``fermata`` is a purely visual articulation. The MIDI
    bytes for a chart with a fermata-marked note must equal those for the
    same chart with the fermata removed.
    """
    src_with = """\
title: "demo"
tempo: 120

groove "end":
    BD: 1
    CR: 1 fermata

section "end":
    bars: 1
    groove: "end"
"""
    src_without = src_with.replace("CR: 1 fermata", "CR: 1")
    midi_with = emit_midi(compile_song(parse(src_with)))
    midi_without = emit_midi(compile_song(parse(src_without)))
    assert midi_with == midi_without


# ── MusicXML emission ────────────────────────────────────────────────────


def test_musicxml_emits_fermata_notation() -> None:
    """MusicXML's ``<fermata/>`` is a top-level notation (sibling of
    ``<articulations>``) — XML readers display it as the fermata symbol
    above the notehead, matching the LilyPond engraving.
    """
    src = """\
title: "demo"
tempo: 120

groove "end":
    BD: 1
    CR: 1 fermata

section "end":
    bars: 1
    groove: "end"
"""
    xml = emit_musicxml(compile_song(parse(src))).decode()
    assert "<fermata />" in xml or "<fermata/>" in xml


# ── Beat positions and modifiers survive parsing intact ──────────────────


def test_fermata_preserved_at_correct_beat_position() -> None:
    """A fermata on a 16th-note offbeat keeps its modifier through the
    parser → AST → IR pipeline at the exact subdivided beat position.
    """
    src = """\
groove "g":
    BD: 1, 3
    SN: 2, 4
    HH: 1, 1e fermata, 1&, 1a, 2, 2e, 2&, 2a, 3, 3e, 3&, 3a, 4, 4e, 4&, 4a
"""
    ir = compile_groove(parse(src).grooves[0])
    fermata_hits = [e for e in ir.events if "fermata" in e.modifiers]
    assert len(fermata_hits) == 1
    assert fermata_hits[0].instrument == "HH"
    assert fermata_hits[0].beat_position == Fraction(1, 16)
