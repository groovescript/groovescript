from fractions import Fraction
from pathlib import Path

from groovescript.compiler import compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_fixture_library_fills():
    """End-to-end: library_fills.gs references several built-in library fills
    without defining them locally; they should all resolve from the built-in
    fill library at compile time."""
    song = parse_file(str(FIXTURES / "library_fills.gs"))
    assert song.metadata.title == "Library Fills"
    # No fills defined in the fixture — all references come from the library.
    assert len(song.fills) == 0
    referenced = {p.fill_name for s in song.sections for p in s.fills}
    # Fixture exercises a broad cross-section of the library; any new
    # fill added to the fixture should appear here.
    assert referenced == {
        "crash",
        "crash-4",
        "snare-roll",
        "snare-roll-half",
        "snare-roll-beat",
        "snare-roll-trip",
        "snare-roll-trip-half",
        "buzz-roll",
        "buzz-roll-half",
        "buzz-roll-beat",
        "tom-roll",
        "tom-roll-half",
        "tom-roll-up",
        "tom-roll-trip",
        "snare-tom-half",
        "around-kit",
        "around-kit-16ths",
        "flam-fill",
        "linear-half",
    }
    ir = compile_song(song)
    assert len(ir.bars) == sum(s.bars for s in song.sections)
    ly = emit_lilypond(ir)
    assert "drummode" in ly


def test_library_contains_expected_fills():
    """The library should expose a stable set of named fills. Renames or
    removals must update this list — regressions here mean a published
    name has silently disappeared."""
    from groovescript.library import get_library_fills

    names = set(get_library_fills().keys())
    assert names == {
        "crash", "crash-4",
        "snare-roll", "snare-roll-half", "snare-roll-beat",
        "snare-roll-trip", "snare-roll-trip-half",
        "buzz-roll", "buzz-roll-half", "buzz-roll-beat",
        "tom-roll", "tom-roll-half", "tom-roll-up", "tom-roll-trip",
        "snare-tom-half", "around-kit", "around-kit-16ths",
        "flam-fill", "linear-half",
    }


def test_library_every_fill_compiles_in_a_section():
    """Every library fill must compile cleanly when placed into a
    section — guards against syntax errors, unparseable count tokens,
    or grid mismatches slipping into the library file."""
    from groovescript.library import get_library_fills

    for name in get_library_fills():
        src = f"""
        section "s":
            bars: 1
            groove: "rock"
            fill "{name}" at bar 1
        """
        ir = compile_song(parse(src))
        assert len(ir.bars) == 1, f"fill {name!r} did not produce one bar"
        assert ir.bars[0].events, f"fill {name!r} produced zero events"


def test_library_fill_crash():
    source = """
    section "verse":
        bars: 2
        groove: "rock"
        fill "crash" at bar 2
    """
    song = parse(source)
    ir = compile_song(song)

    assert len(ir.bars) == 2
    # Bar 2 should contain BD + CR on beat 1 (overlaying the rock groove).
    bar2 = ir.bars[1]
    assert any(e.instrument == "BD" and e.beat_position == 0 for e in bar2.events)
    assert any(e.instrument == "CR" and e.beat_position == 0 for e in bar2.events)


def test_library_fill_snare_roll_half():
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "snare-roll-half" at bar 1 beat 3
    """
    song = parse(source)
    ir = compile_song(song)

    assert len(ir.bars) == 1
    bar = ir.bars[0]
    # Eight 16th-note snare hits across beats 3 and 4 (groove SN before
    # beat 3 is preserved; the fill replaces only beats 3 onward).
    snare_positions = sorted(
        e.beat_position for e in bar.events
        if e.instrument == "SN" and e.beat_position >= Fraction(1, 2)
    )
    expected = [Fraction(2, 4) + Fraction(i, 16) for i in range(8)]
    assert snare_positions == expected
    # Bar must use 16th-note resolution to fit the roll.
    assert bar.subdivision >= 16


def test_library_fill_override():
    """A user-defined fill with the same name as a library fill takes precedence."""
    source = """
    fill "crash":
      count "1":
        1: SN

    section "verse":
        bars: 1
        groove: "rock"
        fill "crash" at bar 1
    """
    song = parse(source)
    ir = compile_song(song)

    assert len(ir.bars) == 1
    # The override puts a single SN at beat 1; no BD or CR from the library
    # version should land on beat 1 from the fill.
    bar = ir.bars[0]
    on_beat_one = [e for e in bar.events if e.beat_position == 0]
    instruments = {e.instrument for e in on_beat_one}
    assert "SN" in instruments
    assert "CR" not in instruments


def test_library_fill_tom_roll_subdivisions():
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "tom-roll" at bar 1
    """
    song = parse(source)
    ir = compile_song(song)

    bar = ir.bars[0]
    assert bar.subdivision >= 16
    # FT, MT, HT all appear in the bar.
    instruments = {e.instrument for e in bar.events}
    assert {"HT", "MT", "FT"}.issubset(instruments)


def test_library_fill_buzz_roll_whole_bar():
    """`buzz-roll` places a single SN event with the buzz modifier and a
    whole-note duration, rendering as a sustained buzz across the bar."""
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "buzz-roll" at bar 1
    """
    ir = compile_song(parse(source))
    bar = ir.bars[0]
    buzz_events = [e for e in bar.events if "buzz" in e.modifiers]
    assert len(buzz_events) == 1
    assert buzz_events[0].instrument == "SN"
    assert buzz_events[0].beat_position == 0
    assert buzz_events[0].buzz_duration == "1"


def test_library_fill_tom_roll_up_is_ascending():
    """`tom-roll-up` reverses the default descending order: FT → MT → HT."""
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "tom-roll-up" at bar 1
    """
    ir = compile_song(parse(source))
    bar = ir.bars[0]
    # Earliest FT event must precede the earliest HT event.
    ft_first = min(e.beat_position for e in bar.events if e.instrument == "FT")
    ht_first = min(e.beat_position for e in bar.events if e.instrument == "HT")
    assert ft_first < ht_first


def test_library_fill_triplet_tokens_infer_triplet_subdivision():
    """Triplet-grid fills (`snare-roll-trip*`, `tom-roll-trip`) force the
    bar's subdivision up to 12 even when the underlying groove is 8ths."""
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "snare-roll-trip" at bar 1
    """
    ir = compile_song(parse(source))
    assert ir.bars[0].subdivision == 12


def test_library_fill_around_kit_16ths():
    """Each beat of the bar is a different drum: SN, HT, MT, FT."""
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "around-kit-16ths" at bar 1
    """
    ir = compile_song(parse(source))
    bar = ir.bars[0]
    # All four drums should appear, each with four 16th-note hits.
    for inst, start_beat in [("SN", 0), ("HT", 1), ("MT", 2), ("FT", 3)]:
        positions = sorted(
            e.beat_position for e in bar.events if e.instrument == inst
        )
        expected = [Fraction(start_beat, 4) + Fraction(i, 16) for i in range(4)]
        # Around-kit-16ths fill-only positions should equal expected; the
        # `rock` groove also adds SN on beat 2 (pre-fill), but the fill
        # replaces it.
        assert expected[0] in positions, f"{inst} missing expected start"
        assert expected[-1] in positions, f"{inst} missing expected end"


def test_library_fill_linear_half_has_no_simultaneous_hits():
    """A linear fill never doubles two instruments on the same beat
    position within the fill region (beats 3-4)."""
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "linear-half" at bar 1 beat 3
    """
    ir = compile_song(parse(source))
    bar = ir.bars[0]
    half = Fraction(1, 2)
    positions = [e.beat_position for e in bar.events if e.beat_position >= half]
    # Seven distinct 16th-note positions across beats 3-4 (8 16ths - the
    # last 4a slot is FT only, so we still expect eight events across
    # eight distinct positions).
    assert len(positions) == len(set(positions))


def test_library_fill_flam_fill_has_flams():
    """`flam-fill` places flam modifiers on the downbeats of 3 and 4."""
    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "flam-fill" at bar 1 beat 3
    """
    ir = compile_song(parse(source))
    bar = ir.bars[0]
    flammed = [e for e in bar.events if "flam" in e.modifiers]
    flammed_positions = sorted(e.beat_position for e in flammed)
    assert flammed_positions == [Fraction(1, 2), Fraction(3, 4)]
    assert all(e.instrument == "SN" for e in flammed)


def test_library_fill_unknown_still_errors():
    """A reference to a fill that is neither user-defined nor in the library
    must still raise a clear unknown-fill error."""
    import pytest

    source = """
    section "verse":
        bars: 1
        groove: "rock"
        fill "definitely-not-a-real-fill" at bar 1
    """
    song = parse(source)
    with pytest.raises(ValueError, match="unknown fill"):
        compile_song(song)


# ----- Fill extension tests -----


def test_fill_extend_bare_body_no_count_block():
    """The bare-count form (no ``count "..."`` wrapper) also accepts
    ``extend:`` — convenient for the common case of layering one voice
    onto a library fill."""
    source = """
    fill "snare-roll+kick":
      extend: "snare-roll"
      BD: 1, 2, 3, 4

    section "s":
        bars: 1
        groove: "rock"
        fill "snare-roll+kick" at bar 1
    """
    ir = compile_song(parse(source))
    bar = ir.bars[0]
    bd = sorted(e.beat_position for e in bar.events if e.instrument == "BD")
    assert bd == [Fraction(i, 4) for i in range(4)]
    sn = [e for e in bar.events if e.instrument == "SN"]
    assert len(sn) == 16  # snare-roll preserved


def test_fill_extend_library_adds_bass_drum_layer():
    """Extending a library fill adds the extension's events without
    removing any of the base's events — the core layering use case."""
    source = """
    fill "snare-roll+kick":
      extend: "snare-roll"
      count "1 2 3 4":
        BD: 1, 2, 3, 4

    section "s":
        bars: 1
        groove: "rock"
        fill "snare-roll+kick" at bar 1
    """
    ir = compile_song(parse(source))
    bar = ir.bars[0]
    # Base snare-roll contributes 16 SN events; none should be lost.
    sn = [e for e in bar.events if e.instrument == "SN"]
    assert len(sn) == 16
    # Extension adds BD on beats 1-4.
    bd_positions = sorted(
        e.beat_position for e in bar.events if e.instrument == "BD"
    )
    assert bd_positions == [Fraction(i, 4) for i in range(4)]


def test_fill_extend_only_alias():
    """`extend: "base"` with no body is a pure alias — the extending fill
    compiles to exactly the base fill's events."""
    source = """
    fill "big hit":
      extend: "crash"

    section "s":
        bars: 1
        groove: "rock"
        fill "big hit" at bar 1
    """
    ir = compile_song(parse(source))
    on_beat_one = sorted(
        e.instrument for e in ir.bars[0].events if e.beat_position == 0
    )
    # Library "crash" is BD + CR on beat 1.
    assert "BD" in on_beat_one and "CR" in on_beat_one


def test_fill_extend_broadcast_over_multi_bar_base():
    """A single-bar extension broadcasts to every bar of a multi-bar base
    (same semantics as groove `extend:`)."""
    source = """
    fill "two bar base":
      count "3 e & a 4 e & a":
        SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a
      count "1 2 3 4":
        1: BD, CR
        2: BD
        3: BD
        4: BD

    fill "two bar + hat":
      extend: "two bar base"
      count "1 2 3 4":
        HH: *4

    section "s":
        bars: 2
        groove: "rock"
        fill "two bar + hat" at bar 1
    """
    ir = compile_song(parse(source))
    # Both bars should have four HH hits from the broadcast extension.
    for i, bar in enumerate(ir.bars):
        hh = [e for e in bar.events if e.instrument == "HH"]
        assert len(hh) == 4, f"bar {i+1} should have 4 HH from broadcast"


def test_fill_extend_per_bar_targeting():
    """When the extension has N bars matching the base's N, merges bar-by-bar
    (not broadcast)."""
    source = """
    fill "two-bar base":
      count "3 e & a 4 e & a":
        SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a
      count "1 2 3 4":
        1: BD

    fill "per-bar extend":
      extend: "two-bar base"
      count "3 4":
        HH: 3, 4
      count "1 2 3 4":
        CR: 1

    section "s":
        bars: 2
        groove: "rock"
        fill "per-bar extend" at bar 1
    """
    ir = compile_song(parse(source))
    # Bar 1 has HH additions; bar 2 has CR.
    bar1_insts = {e.instrument for e in ir.bars[0].events}
    bar2_insts = {e.instrument for e in ir.bars[1].events}
    assert "HH" in bar1_insts
    assert "CR" in bar2_insts
    assert "CR" not in bar1_insts
    assert "HH" not in {e.instrument for e in ir.bars[1].events if e.beat_position > 0}


def test_fill_extend_transitive_chain():
    """An extension can chain: C extends B extends A resolves all three."""
    source = """
    fill "a":
      count "1 2 3 4":
        SN: *16

    fill "b":
      extend: "a"
      count "1 2 3 4":
        BD: 1, 3

    fill "c":
      extend: "b"
      count "1 2 3 4":
        CR: 1

    section "s":
        bars: 1
        groove: "rock"
        fill "c" at bar 1
    """
    ir = compile_song(parse(source))
    insts = {e.instrument for e in ir.bars[0].events}
    assert {"SN", "BD", "CR"}.issubset(insts)


def test_fill_extend_unknown_base_raises():
    import pytest

    source = """
    fill "x":
      extend: "no-such-fill"
      count "1":
        1: BD

    section "s":
        bars: 1
        groove: "rock"
        fill "x" at bar 1
    """
    with pytest.raises(ValueError, match="unknown fill 'no-such-fill'"):
        compile_song(parse(source))


def test_fill_extend_cycle_raises():
    import pytest

    source = """
    fill "a":
      extend: "b"

    fill "b":
      extend: "a"

    section "s":
        bars: 1
        groove: "rock"
        fill "a" at bar 1
    """
    with pytest.raises(ValueError, match="Circular extend"):
        compile_song(parse(source))


def test_fill_extend_cannot_lengthen_base():
    """An extension with more bars than the base is rejected — extension is
    layering, not fill-lengthening."""
    import pytest

    source = """
    fill "single":
      count "1":
        1: SN

    fill "too long":
      extend: "single"
      count "1":
        BD: 1
      count "2":
        BD: 2

    section "s":
        bars: 1
        groove: "rock"
        fill "too long" at bar 1
    """
    with pytest.raises(ValueError, match="cannot lengthen"):
        compile_song(parse(source))


def test_fill_extend_base_preserved_unchanged():
    """Extending a fill must not mutate the base — referencing the base
    elsewhere still gives the original events."""
    source = """
    fill "base":
      count "1 2 3 4":
        SN: *16

    fill "derived":
      extend: "base"
      count "1 2 3 4":
        BD: 1, 3

    section "base-only":
        bars: 1
        groove: "rock"
        fill "base" at bar 1

    section "derived":
        bars: 1
        groove: "rock"
        fill "derived" at bar 1
    """
    ir = compile_song(parse(source))
    # Bar 1 uses the base fill (SN roll), replacing the whole rock bar.
    # Base has no BD, so no BD should appear in bar 1.
    bar1_bd = [e for e in ir.bars[0].events if e.instrument == "BD"]
    assert bar1_bd == []
    # Bar 2 uses the derived fill — extension adds BD on 1 and 3.
    bar2_bd = sorted(
        e.beat_position for e in ir.bars[1].events if e.instrument == "BD"
    )
    assert bar2_bd == [Fraction(0), Fraction(1, 2)]
