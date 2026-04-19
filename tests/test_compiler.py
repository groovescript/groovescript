from fractions import Fraction

import pytest

from groovescript.ast_nodes import Fill, FillBar, FillLine, FillPlaceholder, FillPlacement, Groove, InheritSpec, Metadata, PatternLine, Section, Song, StarSpec
from groovescript.compiler import IRFillBar, IRGroove, IRSong, compile_fill_bar, compile_groove, compile_song

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

TWO_BAR = Groove(
    name="two bar",
    bars=[
        [
            PatternLine(instrument="BD", beats=["1", "3"]),
            PatternLine(instrument="SN", beats=["2", "4"]),
            PatternLine(instrument="HH", beats=StarSpec(note_value=8)),
        ],
        [
            PatternLine(instrument="BD", beats=["1", "2&", "4"]),
            PatternLine(instrument="SN", beats=["2", "4"]),
            PatternLine(instrument="HH", beats=StarSpec(note_value=8)),
        ],
    ],
)


def test_compile_song_inline_fill_replaces_bar():
    """A fill defined inline inside a section is registered and applied."""
    from groovescript.parser import parse
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 4
  groove: "beat"
  fill at bar 4 beat 3:
    count "3 e & a 4":
      3: SN
      3e: SN
      3&: SN
      3a: SN
      4: BD, CR
"""
    song = parse(src)
    ir = compile_song(song)
    bar4 = ir.bars[3]
    # Fill CR should be present on bar 4
    assert any(e.instrument == "CR" for e in bar4.events)
    # Bar 4's first two beats should still contain groove HH events
    early_hh = [e for e in bar4.events if e.instrument == "HH" and e.beat_position < Fraction(1, 2)]
    assert early_hh


def test_compile_returns_ir_groove():
    ir = compile_groove(MONEY_BEAT)
    assert isinstance(ir, IRGroove)


def test_compile_ir_metadata():
    ir = compile_groove(MONEY_BEAT)
    assert ir.name == "money beat"
    assert ir.subdivision == 8
    assert ir.bars == 1


def test_compile_bd_positions():
    ir = compile_groove(MONEY_BEAT)
    bd_positions = {e.beat_position for e in ir.events if e.instrument == "BD"}
    assert bd_positions == {Fraction(0), Fraction(1, 2)}


def test_compile_sn_positions():
    ir = compile_groove(MONEY_BEAT)
    sn_positions = {e.beat_position for e in ir.events if e.instrument == "SN"}
    assert sn_positions == {Fraction(1, 4), Fraction(3, 4)}


def test_compile_hh_star_expands_to_all_positions():
    ir = compile_groove(MONEY_BEAT)
    hh_positions = sorted(e.beat_position for e in ir.events if e.instrument == "HH")
    assert hh_positions == [Fraction(i, 8) for i in range(8)]


def test_compile_events_sorted_by_position():
    ir = compile_groove(MONEY_BEAT)
    positions = [(e.bar, e.beat_position) for e in ir.events]
    assert positions == sorted(positions)


def test_compile_multi_bar_groove():
    ir = compile_groove(TWO_BAR)
    assert ir.bars == 2
    second_bar_bd_positions = {
        e.beat_position for e in ir.events if e.bar == 2 and e.instrument == "BD"
    }
    assert second_bar_bd_positions == {Fraction(0), Fraction(3, 8), Fraction(3, 4)}


def test_compile_16th_beat_labels():
    groove = Groove(
        name="16th",
        bars=[[PatternLine(instrument="SN", beats=["1e", "2&", "3a"])]],
    )
    ir = compile_groove(groove)
    sn_positions = {e.beat_position for e in ir.events if e.instrument == "SN"}
    assert Fraction(1, 16) in sn_positions
    assert Fraction(6, 16) in sn_positions
    assert Fraction(11, 16) in sn_positions


def test_compile_song_loops_multi_bar_groove_within_section():
    song = Song(
        metadata=Metadata(title="Song", tempo=120),
        grooves=[MONEY_BEAT, TWO_BAR],
        sections=[
            Section(name="intro", bars=2, groove="money beat"),
            Section(name="verse", bars=3, groove="two bar"),
        ],
    )

    ir = compile_song(song)

    assert isinstance(ir, IRSong)
    assert len(ir.bars) == 5
    assert ir.sections[0].start_bar == 1
    assert ir.sections[1].start_bar == 3

    verse_bar_1 = ir.bars[2]
    verse_bar_2 = ir.bars[3]
    verse_bar_3 = ir.bars[4]

    assert verse_bar_1.section_name == "verse"
    assert {e.instrument for e in verse_bar_2.events if e.beat_position == Fraction(3, 8)} == {
        "BD",
        "HH",
    }
    assert {e.instrument for e in verse_bar_3.events if e.beat_position == Fraction(1, 2)} == {
        "BD",
        "HH",
    }


def test_compile_song_rejects_unknown_groove():
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="oops", bars=1, groove="missing")],
    )

    with pytest.raises(ValueError, match="unknown groove"):
        compile_song(song)


# --- Fill compilation tests ---

BAR_4_FILL = Fill(
    name="bar 4 fill",
    bars=[
        FillBar(
            label="3 e & a 4",
            lines=[
                FillLine(beat="3", instruments=["SN"]),
                FillLine(beat="3e", instruments=["SN"]),
                FillLine(beat="3&", instruments=["SN"]),
                FillLine(beat="3a", instruments=["SN"]),
                FillLine(beat="4", instruments=["BD", "CR"]),
            ],
        )
    ],
)


def test_compile_fill_bar_16th_structure():
    """A 16th-grid fill bar compiles to IRFillBar with correct subdivision, positions, and chord."""
    ir = compile_fill_bar(BAR_4_FILL.bars[0])
    assert isinstance(ir, IRFillBar)
    assert ir.subdivision == 16
    positions = {e.beat_position for e in ir.events}
    assert positions >= {
        Fraction(8, 16),   # beat 3
        Fraction(9, 16),   # beat 3e
        Fraction(10, 16),  # beat 3&
        Fraction(11, 16),  # beat 3a
        Fraction(12, 16),  # beat 4
    }
    beat4_instruments = {e.instrument for e in ir.events if e.beat_position == Fraction(12, 16)}
    assert beat4_instruments == {"BD", "CR"}


def test_compile_fill_bar_8th_subdivision():
    fill_bar = FillBar(
        label="1 2 3 4",
        lines=[
            FillLine(beat="1", instruments=["SN"]),
            FillLine(beat="2&", instruments=["BD"]),
        ],
    )
    ir = compile_fill_bar(fill_bar)
    assert ir.subdivision == 8
    positions = {e.beat_position for e in ir.events}
    assert Fraction(0, 8) in positions
    assert Fraction(3, 8) in positions


def test_compile_fill_bar_star_syntax():
    """Regression: fill bars with *N star syntax expand to correct events."""
    fill_bar = FillBar(
        label="1 2 3 4",
        lines=[],
        pattern_lines=[PatternLine(instrument="FT", beats=StarSpec(note_value=8))],
    )
    ir = compile_fill_bar(fill_bar)
    assert ir.subdivision == 8
    ft_events = [e for e in ir.events if e.instrument == "FT"]
    assert len(ft_events) == 8


def test_compile_fill_bar_star_except_syntax():
    """Regression: fill bars with *N except beat_list exclude specified beats."""
    fill_bar = FillBar(
        label="1 2 3 4",
        lines=[],
        pattern_lines=[PatternLine(instrument="FT", beats=StarSpec(note_value=8, except_beats=("4&",)))],
    )
    ir = compile_fill_bar(fill_bar)
    assert ir.subdivision == 8
    ft_events = [e for e in ir.events if e.instrument == "FT"]
    # *8 = 8 hits, except 4& = 7 hits
    assert len(ft_events) == 7
    excluded_pos = Fraction(7, 8)  # beat 4& = position 7/8
    assert all(e.beat_position != excluded_pos for e in ft_events)


def test_compile_fill_bar_star_mixed_with_fill_lines():
    """Fill bars can mix star-spec pattern lines with explicit FillLines."""
    fill_bar = FillBar(
        label="1 2 3 4",
        lines=[FillLine(beat="4", instruments=["CR"])],
        pattern_lines=[PatternLine(instrument="FT", beats=StarSpec(note_value=8, except_beats=("4&",)))],
    )
    ir = compile_fill_bar(fill_bar)
    assert ir.subdivision == 8
    ft_events = [e for e in ir.events if e.instrument == "FT"]
    cr_events = [e for e in ir.events if e.instrument == "CR"]
    assert len(ft_events) == 7
    assert len(cr_events) == 1


def test_compile_song_fill_replaces_whole_bar():
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[BAR_4_FILL],
        sections=[
            Section(
                name="intro",
                bars=4,
                groove="money beat",
                fills=[FillPlacement(fill_name="bar 4 fill", bar=4)],
            )
        ],
    )
    ir = compile_song(song)
    bar4 = ir.bars[3]
    instruments_in_bar4 = {e.instrument for e in bar4.events}
    # Fill events should include SN, BD, CR at fill positions
    assert "CR" in instruments_in_bar4
    # Groove HH events should be gone (fill replaced whole bar starting at 0)
    assert "HH" not in instruments_in_bar4


def test_compile_song_fill_with_beat_preserves_early_groove_events():
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[BAR_4_FILL],
        sections=[
            Section(
                name="intro",
                bars=4,
                groove="money beat",
                fills=[FillPlacement(fill_name="bar 4 fill", bar=4, beat="3")],
            )
        ],
    )
    ir = compile_song(song)
    bar4 = ir.bars[3]
    # HH events before beat 3 (positions 0,1/8,2/8 = 0,1/8,1/4) should be kept
    early_hh = [e for e in bar4.events if e.instrument == "HH" and e.beat_position < Fraction(1, 2)]
    assert len(early_hh) > 0
    # CR from fill should be present
    assert any(e.instrument == "CR" for e in bar4.events)


def test_compile_song_fill_uses_max_subdivision():
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[BAR_4_FILL],
        sections=[
            Section(
                name="intro",
                bars=4,
                groove="money beat",
                fills=[FillPlacement(fill_name="bar 4 fill", bar=4)],
            )
        ],
    )
    ir = compile_song(song)
    bar4 = ir.bars[3]
    assert bar4.subdivision == 16  # max(8, 16)


def test_compile_song_rejects_unknown_fill():
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[],
        sections=[
            Section(
                name="oops",
                bars=1,
                groove="money beat",
                fills=[FillPlacement(fill_name="nonexistent", bar=1)],
            )
        ],
    )
    with pytest.raises(ValueError, match="unknown fill"):
        compile_song(song)


def test_compile_song_multi_bar_fill():
    two_bar_fill = Fill(
        name="two bar fill",
        bars=[
            FillBar(
                label="bar 3",
                lines=[FillLine(beat="3", instruments=["SN"]), FillLine(beat="4", instruments=["CR"])],
            ),
            FillBar(
                label="bar 4",
                lines=[FillLine(beat="1", instruments=["BD"]), FillLine(beat="4", instruments=["CR"])],
            ),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[two_bar_fill],
        sections=[
            Section(
                name="verse",
                bars=4,
                groove="money beat",
                fills=[FillPlacement(fill_name="two bar fill", bar=3)],
            )
        ],
    )
    ir = compile_song(song)
    bar3 = ir.bars[2]
    bar4 = ir.bars[3]
    # bar3 fill replaced whole bar — no HH
    assert "HH" not in {e.instrument for e in bar3.events}
    assert "CR" in {e.instrument for e in bar3.events}
    # bar4 fill replaced whole bar — no HH
    assert "HH" not in {e.instrument for e in bar4.events}
    assert "BD" in {e.instrument for e in bar4.events}


# --- Iteration 4: variations and section inheritance ---

from groovescript.ast_nodes import Variation, VariationAction
from groovescript.compiler import _resolve_inheritance


def test_resolve_like_copies_bars_and_groove():
    sections = [
        Section(name="verse", bars=8, groove="money beat"),
        Section(name="verse 2", bars=None, groove=None, inherit=InheritSpec(parent="verse")),
    ]
    resolved = _resolve_inheritance(sections)
    assert resolved[1].bars == 8
    assert resolved[1].groove == "money beat"
    assert resolved[1].inherit is None


def test_resolve_like_preserves_name():
    sections = [
        Section(name="verse", bars=4, groove="money beat"),
        Section(name="verse 2", bars=None, groove=None, inherit=InheritSpec(parent="verse")),
    ]
    resolved = _resolve_inheritance(sections)
    assert resolved[1].name == "verse 2"


def test_resolve_like_with_fills_copies_fills():
    fp = FillPlacement(fill_name="fill", bar=4)
    sections = [
        Section(name="verse", bars=4, groove="money beat", fills=[fp]),
        Section(
            name="verse 2",
            bars=None,
            groove=None,
            inherit=InheritSpec(parent="verse", categories=frozenset({"fills"})),
        ),
    ]
    resolved = _resolve_inheritance(sections)
    assert len(resolved[1].fills) == 1
    assert resolved[1].fills[0].fill_name == "fill"


def test_resolve_bare_like_drops_fills():
    """Bare ``like`` inherits structure only — fills stay with the parent."""
    fp = FillPlacement(fill_name="fill", bar=4)
    sections = [
        Section(name="verse", bars=4, groove="money beat", fills=[fp]),
        Section(name="verse 2", bars=None, groove=None, inherit=InheritSpec(parent="verse")),
    ]
    resolved = _resolve_inheritance(sections)
    assert resolved[1].fills == []


def test_resolve_like_unknown_section_raises():
    import pytest
    sections = [
        Section(
            name="chorus",
            bars=4,
            groove="money beat",
            inherit=InheritSpec(parent="missing"),
        ),
    ]
    with pytest.raises(ValueError, match="unknown section"):
        _resolve_inheritance(sections)


def test_compile_song_like_inherits_groove():
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[
            Section(name="verse", bars=2, groove="money beat"),
            Section(name="verse 2", bars=None, groove=None, inherit=InheritSpec(parent="verse")),
        ],
    )
    ir = compile_song(song)
    assert len(ir.bars) == 4
    # verse 2 bars should have same events as verse bars
    assert {e.instrument for e in ir.bars[0].events} == {e.instrument for e in ir.bars[2].events}


def test_resolve_like_chained():
    """Regression: chained like (C likes B, B likes A) should resolve correctly."""
    sections = [
        Section(name="verse", bars=8, groove="money beat"),
        Section(name="verse 2", bars=None, groove=None, inherit=InheritSpec(parent="verse")),
        Section(name="verse 3", bars=None, groove=None, inherit=InheritSpec(parent="verse 2")),
    ]
    resolved = _resolve_inheritance(sections)
    assert resolved[2].bars == 8
    assert resolved[2].groove == "money beat"
    assert resolved[2].inherit is None


def test_resolve_like_chained_with_override():
    """Regression: chained like with scalar overrides propagated correctly."""
    sections = [
        Section(name="verse", bars=8, groove="money beat"),
        Section(name="verse 2", bars=4, groove=None, inherit=InheritSpec(parent="verse")),
        Section(name="verse 3", bars=None, groove=None, inherit=InheritSpec(parent="verse 2")),
    ]
    resolved = _resolve_inheritance(sections)
    # verse 2 overrides bars to 4, verse 3 inherits that override
    assert resolved[1].bars == 4
    assert resolved[1].groove == "money beat"
    assert resolved[2].bars == 4
    assert resolved[2].groove == "money beat"


def test_resolve_like_circular_raises():
    """Regression: circular like references should raise an error."""
    import pytest
    sections = [
        Section(name="A", bars=None, groove=None, inherit=InheritSpec(parent="B")),
        Section(name="B", bars=None, groove=None, inherit=InheritSpec(parent="A")),
    ]
    with pytest.raises(ValueError, match="Circular like"):
        _resolve_inheritance(sections)


def test_compile_variation_replace_removes_and_adds():
    variation = Variation(
        name="lift",
        bars=[2],
        actions=[
            VariationAction(action="replace", instrument="HH", target_instrument="CR", beats=["1"]),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[
            Section(name="verse", bars=2, groove="money beat", variations=[variation]),
        ],
    )
    ir = compile_song(song)
    bar2 = ir.bars[1]
    instruments_at_beat1 = {e.instrument for e in bar2.events if e.beat_position == Fraction(0)}
    assert "CR" in instruments_at_beat1
    assert "HH" not in instruments_at_beat1


def test_compile_variation_remove():
    variation = Variation(
        name="no bd",
        bars=[1],
        actions=[
            VariationAction(action="remove", instrument="BD", beats=["1", "3"]),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=1, groove="money beat", variations=[variation])],
    )
    ir = compile_song(song)
    bar1_instruments = {e.instrument for e in ir.bars[0].events}
    assert "BD" not in bar1_instruments


def test_compile_variation_add_rejects_stacking_on_existing_note():
    """Regression: `add` must error when the target position already has a note
    for that instrument, instead of silently stacking two noteheads. Guards
    against the bridge-section bug in charts/einstein-on-the-beach.gs where
    `add kick at 1` duplicated the kick already present in the groove.
    """
    variation = Variation(
        name="stack",
        bars=[1],
        actions=[
            VariationAction(action="add", instrument="BD", beats=["1"]),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=1, groove="money beat", variations=[variation])],
    )
    with pytest.raises(ValueError, match="already present"):
        compile_song(song)


def test_compile_variation_replace_rejects_stacking_target():
    """Regression: `replace X with Y` must error when Y already exists at the
    target position, instead of stacking a second Y notehead.
    """
    variation = Variation(
        name="stack crash",
        bars=[1],
        actions=[
            VariationAction(action="add", instrument="CR", beats=["1"]),
            VariationAction(action="replace", instrument="HH", target_instrument="CR", beats=["1"]),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=1, groove="money beat", variations=[variation])],
    )
    with pytest.raises(ValueError, match="already present"):
        compile_song(song)


def test_compile_variation_add_with_ghost_modifier():
    variation = Variation(
        name="ghost sn",
        bars=[1],
        actions=[
            VariationAction(action="add", instrument="SN", beats=["2&"], modifiers=["ghost"]),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=1, groove="money beat", variations=[variation])],
    )
    ir = compile_song(song)
    bar1 = ir.bars[0]
    ghost_sn = [e for e in bar1.events if e.instrument == "SN" and "ghost" in e.modifiers]
    assert len(ghost_sn) == 1
    assert ghost_sn[0].beat_position == Fraction(3, 8)


def test_compile_variation_star_beats():
    variation = Variation(
        name="swap hh",
        bars=[1],
        actions=[
            VariationAction(action="replace", instrument="HH", target_instrument="OH", beats="*"),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=1, groove="money beat", variations=[variation])],
    )
    ir = compile_song(song)
    bar1_instruments = {e.instrument for e in ir.bars[0].events}
    assert "HH" not in bar1_instruments
    assert "OH" in bar1_instruments


def test_compile_variation_only_applies_to_target_bar():
    variation = Variation(
        name="last bar only",
        bars=[2],
        actions=[
            VariationAction(action="remove", instrument="HH", beats="*"),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=2, groove="money beat", variations=[variation])],
    )
    ir = compile_song(song)
    # bar 1 should still have HH
    assert any(e.instrument == "HH" for e in ir.bars[0].events)
    # bar 2 should have no HH
    assert not any(e.instrument == "HH" for e in ir.bars[1].events)


def test_compile_variation_at_multiple_bars():
    """Regression: 'variation at bars 4, 8:' applies actions to all listed bars."""
    variation = Variation(
        name="crashes",
        bars=[2, 4],
        actions=[
            VariationAction(action="replace", instrument="HH", beats="*", target_instrument="CR"),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[
            Section(name="chorus", bars=4, groove="money beat", variations=[variation]),
        ],
    )
    ir = compile_song(song)
    # Bars 2 and 4 should have CR instead of HH
    for bar_idx in [1, 3]:  # 0-indexed
        instruments = {e.instrument for e in ir.bars[bar_idx].events}
        assert "CR" in instruments, f"bar {bar_idx+1} missing CR"
        assert "HH" not in instruments, f"bar {bar_idx+1} still has HH"
    # Bars 1 and 3 should keep HH
    for bar_idx in [0, 2]:  # 0-indexed
        instruments = {e.instrument for e in ir.bars[bar_idx].events}
        assert "HH" in instruments, f"bar {bar_idx+1} missing HH"
        assert "CR" not in instruments, f"bar {bar_idx+1} unexpectedly has CR"


def test_compile_variation_modify_add_flam_attaches_to_existing_hits():
    """``modify add flam to snare at 2`` stamps ``flam`` on the snare hit at
    beat 2, leaving events on other beats and modifiers on other events
    untouched.
    """
    snare_groove = Groove(
        name="snare groove",
        bars=[[
            PatternLine(instrument="BD", beats=["1", "3"]),
            PatternLine(instrument="SN", beats=["2", "4"]),
        ]],
    )
    variation = Variation(
        name="flam 2",
        bars=[1],
        actions=[
            VariationAction(
                action="modify_add",
                instrument="SN",
                modifiers=["flam"],
                beats=["2"],
            ),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[snare_groove],
        sections=[Section(name="verse", bars=1, groove="snare groove", variations=[variation])],
    )
    ir = compile_song(song)
    bar1 = ir.bars[0]
    events_on_2 = [e for e in bar1.events if e.beat_position == Fraction(1, 4)]
    assert events_on_2, "no events landed on beat 2"
    for event in events_on_2:
        assert "flam" in event.modifiers
    # Beat 1 events remain unchanged (no flam was requested there).
    events_on_1 = [e for e in bar1.events if e.beat_position == Fraction(0)]
    assert events_on_1
    for event in events_on_1:
        assert "flam" not in event.modifiers


def test_compile_variation_modify_remove_strips_modifier_from_existing_hits():
    """``modify remove accent from bass at 1`` drops only the named modifier
    from the named instrument's hit, leaving the event itself (and any other
    modifiers it carries) in place."""
    from groovescript.ast_nodes import BeatHit as _BeatHit

    # Custom groove with an accented bass on beat 1.
    accented_groove = Groove(
        name="accented",
        bars=[[
            PatternLine(
                instrument="BD",
                beats=[_BeatHit("1", modifiers=["accent"]), _BeatHit("3")],
            ),
        ]],
    )
    variation = Variation(
        name="calm",
        bars=[1],
        actions=[
            VariationAction(
                action="modify_remove",
                instrument="BD",
                modifiers=["accent"],
                beats=["1"],
            ),
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[accented_groove],
        sections=[Section(name="verse", bars=1, groove="accented", variations=[variation])],
    )
    ir = compile_song(song)
    bar1 = ir.bars[0]
    bd_on_1 = [
        e for e in bar1.events
        if e.instrument == "BD" and e.beat_position == Fraction(0)
    ]
    assert len(bd_on_1) == 1, "the bass hit should still be there"
    assert "accent" not in bd_on_1[0].modifiers


# --- Section Numbering and Repeats ---


def test_automatic_section_numbering():
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[
            Section(name="verse", bars=1, groove="money beat"),
            Section(name="chorus", bars=1, groove="money beat"),
            Section(name="verse", bars=1, groove="money beat"),
        ],
    )
    ir = compile_song(song)
    assert ir.bars[0].section_name == "verse 1"
    assert ir.bars[1].section_name == "chorus"
    assert ir.bars[2].section_name == "verse 2"


def test_explicit_repeat_ir():
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[
            Section(name="verse", bars=4, groove="money beat", repeat=2),
        ],
    )
    ir = compile_song(song)
    # 4 bars total, repeated twice => phrase length = 2 bars
    assert ir.bars[0].repeat_times == 2
    assert ir.bars[0].repeat_index == 1
    assert ir.bars[1].repeat_times is None
    assert ir.bars[1].repeat_index == 1
    assert ir.bars[2].repeat_times == 2
    assert ir.bars[2].repeat_index == 2
    assert ir.bars[3].repeat_times is None
    assert ir.bars[3].repeat_index == 2


# --- Iteration 6: flam/drag modifiers on groove and fill events ---

from groovescript.ast_nodes import BeatHit, InstrumentHit


def test_compile_groove_beat_flam_propagates_to_event():
    groove = Groove(
        name="flam",
        bars=[[PatternLine(instrument="SN", beats=[BeatHit("1", ["flam"]), BeatHit("3")])]],
    )
    ir = compile_groove(groove)
    beat1 = [e for e in ir.events if e.instrument == "SN" and e.beat_position == Fraction(0)]
    assert len(beat1) == 1
    assert beat1[0].modifiers == ["flam"]

    beat3 = [e for e in ir.events if e.instrument == "SN" and e.beat_position == Fraction(1, 2)]
    assert len(beat3) == 1
    assert beat3[0].modifiers == []


def test_compile_flam_on_unsupported_instrument_raises():
    """Regression: flam is only supported on snare and toms — other instruments must be rejected."""
    for instrument in ("BD", "HH", "OH", "RD", "CR", "HF", "SCS"):
        groove = Groove(
            name="bad flam",
            bars=[[PatternLine(instrument=instrument, beats=[BeatHit("1", ["flam"])])]],
        )
        with pytest.raises((ValueError, Exception), match="flam"):
            compile_groove(groove)


def test_compile_fill_instrument_drag_propagates_to_event():
    fill_bar = FillBar(
        label="3 drag",
        lines=[FillLine(beat="3", instruments=[InstrumentHit("SN", ["drag"])])],
    )
    ir = compile_fill_bar(fill_bar)
    assert len(ir.events) == 1
    assert ir.events[0].modifiers == ["drag"]


def test_compile_fill_infers_triplet_subdivision():
    fill_bar = FillBar(
        label="3 trip let",
        lines=[
            FillLine(beat="3", instruments=["SN"]),
            FillLine(beat="3t", instruments=["SN"]),
            FillLine(beat="3l", instruments=["SN"]),
        ],
    )
    ir = compile_fill_bar(fill_bar)
    assert ir.subdivision == 12


def test_compile_triplet_positions():
    fill_bar = FillBar(
        label="3 trip let",
        lines=[
            FillLine(beat="3", instruments=["SN"]),
            FillLine(beat="3t", instruments=["SN"]),
            FillLine(beat="3l", instruments=["SN"]),
        ],
    )
    ir = compile_fill_bar(fill_bar)
    positions = {e.beat_position for e in ir.events}
    assert Fraction(6, 12) in positions   # beat 3
    assert Fraction(7, 12) in positions   # 3t (trip)
    assert Fraction(8, 12) in positions   # 3l (let)


def test_compile_song_triplet_fill_bar_subdivision():
    """A bar with a triplet fill should have subdivision 12."""
    triplet_fill = Fill(
        name="triplet",
        bars=[
            FillBar(
                label="3 trip let",
                lines=[
                    FillLine(beat="3", instruments=["SN"]),
                    FillLine(beat="3t", instruments=["SN"]),
                    FillLine(beat="3l", instruments=["SN"]),
                ],
            )
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[triplet_fill],
        sections=[
            Section(
                name="intro",
                bars=4,
                groove="money beat",
                fills=[FillPlacement(fill_name="triplet", bar=4, beat="3")],
            )
        ],
    )
    ir = compile_song(song)
    bar4 = ir.bars[3]
    assert bar4.subdivision == 12


def test_compile_song_triplet_fill_preserves_straight_groove():
    """Groove events before the triplet fill beat should be kept."""
    triplet_fill = Fill(
        name="triplet",
        bars=[
            FillBar(
                label="3 trip let",
                lines=[
                    FillLine(beat="3", instruments=["SN"]),
                    FillLine(beat="3t", instruments=["SN"]),
                    FillLine(beat="3l", instruments=["SN"]),
                ],
            )
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[triplet_fill],
        sections=[
            Section(
                name="intro",
                bars=4,
                groove="money beat",
                fills=[FillPlacement(fill_name="triplet", bar=4, beat="3")],
            )
        ],
    )
    ir = compile_song(song)
    bar4 = ir.bars[3]
    # HH events at beats 1 and 2 (positions 0, 1/8, 1/4, 3/8) should still be there
    hh_before_3 = [e for e in bar4.events if e.instrument == "HH" and e.beat_position < Fraction(1, 2)]
    assert len(hh_before_3) == 4


# ---------------------------------------------------------------------------
# Iteration 8 — Additional time signatures
# ---------------------------------------------------------------------------

THREE_FOUR_WALTZ = Groove(
    name="waltz",
    bars=[
        [
            PatternLine(instrument="BD", beats=["1"]),
            PatternLine(instrument="SN", beats=["2", "3"]),
            PatternLine(instrument="HH", beats=StarSpec(note_value=8)),
        ]
    ],
)

SIX_EIGHT_GROOVE = Groove(
    name="compound",
    bars=[
        [
            PatternLine(instrument="BD", beats=["1", "4"]),
            PatternLine(instrument="HH", beats=StarSpec(note_value=8)),
            PatternLine(instrument="SN", beats=["3", "6"]),
        ]
    ],
)


def test_compile_3_4_bd_beat1():
    """In 3/4 with beat 1 is at position 0."""
    ir = compile_groove(THREE_FOUR_WALTZ, beats_per_bar=3)
    bd = [e for e in ir.events if e.instrument == "BD"]
    assert len(bd) == 1
    assert bd[0].beat_position == Fraction(0)


def test_compile_3_4_sn_beats():
    """In 3/4 beat 2 = 2/6 = 1/3, beat 3 = 4/6 = 2/3."""
    ir = compile_groove(THREE_FOUR_WALTZ, beats_per_bar=3)
    sn = sorted(e.beat_position for e in ir.events if e.instrument == "SN")
    assert sn == [Fraction(2, 6), Fraction(4, 6)]


def test_compile_3_4_hh_star_six_slots():
    """HH * in 3/4 subdivision=6 expands to 6 slots (not 8)."""
    ir = compile_groove(THREE_FOUR_WALTZ, beats_per_bar=3)
    hh = sorted(e.beat_position for e in ir.events if e.instrument == "HH")
    assert len(hh) == 6
    assert hh == [Fraction(i, 6) for i in range(6)]


def test_compile_6_8_beat4_position():
    """In 6/8 beat 4 = position 3/6 = 1/2."""
    ir = compile_groove(SIX_EIGHT_GROOVE, beats_per_bar=6)
    bd = sorted(e.beat_position for e in ir.events if e.instrument == "BD")
    assert Fraction(3, 6) in bd


def test_compile_beat_out_of_range_raises():
    """Beat 4 in a 3/4 groove should raise ValueError."""
    groove = Groove(
        name="bad",
        bars=[[PatternLine(instrument="BD", beats=["4"])]],
    )
    import pytest
    with pytest.raises(ValueError, match="out of range"):
        compile_groove(groove, beats_per_bar=3)


def test_compile_song_3_4_uses_bpb():
    """compile_song with 3/4 time signature uses beats_per_bar=3."""
    song = Song(
        metadata=Metadata(time_signature="3/4"),
        grooves=[THREE_FOUR_WALTZ],
        sections=[Section(name="A", bars=4, groove="waltz")],
    )
    ir = compile_song(song)
    # BD at beat 1 of each bar = position 0
    bar1_bd = [e for e in ir.bars[0].events if e.instrument == "BD"]
    assert bar1_bd[0].beat_position == Fraction(0)


# ---------------------------------------------------------------------------
# Iteration 9 — Cues and bar-level text annotations
# ---------------------------------------------------------------------------

def test_compile_song_cue_attached_to_bar():
    """A cue at bar 1 with no beat should produce a Fraction(0) entry in bar 1 cues."""
    from groovescript.ast_nodes import Cue
    groove = Groove(
        name="g",
        bars=[[PatternLine(instrument="BD", beats=["1", "3"]),
               PatternLine(instrument="SN", beats=["2", "4"]),
               PatternLine(instrument="HH", beats=StarSpec(note_value=8))]],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[groove],
        sections=[
            Section(
                name="verse",
                bars=4,
                groove="g",
                cues=[Cue(text="Vocals in", bar=1)],
            )
        ],
    )
    ir = compile_song(song)
    bar1 = ir.bars[0]
    assert len(bar1.cues) == 1
    assert bar1.cues[0] == (Fraction(0), "Vocals in")


def test_compile_song_cue_with_beat():
    """A cue at bar 3 beat 3 should be placed at Fraction(1, 2) in bar 3."""
    from groovescript.ast_nodes import Cue
    groove = Groove(
        name="g",
        bars=[[PatternLine(instrument="BD", beats=["1", "3"]),
               PatternLine(instrument="SN", beats=["2", "4"]),
               PatternLine(instrument="HH", beats=StarSpec(note_value=8))]],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[groove],
        sections=[
            Section(
                name="chorus",
                bars=4,
                groove="g",
                cues=[Cue(text="Chorus!", bar=3, beat="3")],
            )
        ],
    )
    ir = compile_song(song)
    bar3 = ir.bars[2]
    assert len(bar3.cues) == 1
    cue_pos, cue_text = bar3.cues[0]
    assert cue_pos == Fraction(1, 2)  # beat 3 of 4/4 with subdivision=8
    assert cue_text == "Chorus!"


def test_compile_song_bar_text_from_groove():
    """A groove bar_texts entry should appear in the IRBar.bar_text."""
    groove = Groove(
        name="g",
        bars=[[PatternLine(instrument="BD", beats=["1", "3"]),
               PatternLine(instrument="SN", beats=["2", "4"]),
               PatternLine(instrument="HH", beats=StarSpec(note_value=8))]],
        bar_texts={1: "Verse feel"},
    )
    song = Song(
        metadata=Metadata(),
        grooves=[groove],
        sections=[Section(name="verse", bars=4, groove="g")],
    )
    ir = compile_song(song)
    # bar_text loops with groove, so all bars in section should have it
    assert ir.bars[0].bar_text == "Verse feel"


# ---------------------------------------------------------------------------
# Iteration 10 — Dual notation style (compiler-level)
# ---------------------------------------------------------------------------

from groovescript.parser import parse


def test_compile_groove_pos_style_events():
    """A groove written in position→instruments style compiles to the same
    events as the equivalent instrument→positions groove."""
    # Classic style: BD at 1,3  SN at 2,4  HH at *
    classic = parse("""\
groove "classic":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "v":
  bars: 1
  groove: "classic"
""")
    # Pos style: same beats, written as position→instruments
    pos = parse("""\
groove "pos":
    1: BD, HH
    1&: HH
    2: SN, HH
    2&: HH
    3: BD, HH
    3&: HH
    4: SN, HH
    4&: HH

section "v":
  bars: 1
  groove: "pos"
""")
    ir_classic = compile_song(classic)
    ir_pos = compile_song(pos)

    def events_key(e):
        return (e.beat_position, e.instrument)

    classic_events = sorted(ir_classic.bars[0].events, key=events_key)
    pos_events = sorted(ir_pos.bars[0].events, key=events_key)

    assert [(e.beat_position, e.instrument) for e in classic_events] == \
           [(e.beat_position, e.instrument) for e in pos_events]


def test_compile_fill_instr_style_events():
    """A fill written in instrument→positions style compiles to correct events."""
    song = parse("""\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "kick crash":
  count "4":
    BD: 4
    CR: 4

section "intro":
  bars: 4
  groove: "beat"
  fill "kick crash" at bar 4
""")
    ir = compile_song(song)
    bar4 = ir.bars[3]
    instruments_at_beat4 = {
        e.instrument for e in bar4.events if e.beat_position == Fraction(3, 4)
    }
    assert "BD" in instruments_at_beat4
    assert "CR" in instruments_at_beat4


def test_compile_fill_mixed_notation_events():
    """A fill with mixed notation: instr→pos for the run, pos→instr for the finish."""
    song = parse("""\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "snare run":
  count "3 e & a 4":
    SN: 3, 3e, 3&, 3a
    4: BD, CR

section "intro":
  bars: 4
  groove: "beat"
  fill "snare run" at bar 4 beat 3
""")
    ir = compile_song(song)
    bar4 = ir.bars[3]
    # SN should be present at 3, 3e, 3&, 3a
    sn_positions = {e.beat_position for e in bar4.events if e.instrument == "SN"}
    assert Fraction(8, 16) in sn_positions   # beat 3
    assert Fraction(9, 16) in sn_positions   # beat 3e
    assert Fraction(10, 16) in sn_positions  # beat 3&
    assert Fraction(11, 16) in sn_positions  # beat 3a
    # BD and CR at beat 4
    beat4_instruments = {e.instrument for e in bar4.events if e.beat_position == Fraction(12, 16)}
    assert "BD" in beat4_instruments
    assert "CR" in beat4_instruments


# ---------------------------------------------------------------------------
# Per-section tempo changes
# ---------------------------------------------------------------------------

def test_compile_section_tempo_override():
    """A section with an explicit tempo overrides the global tempo in IRBar."""
    song = Song(
        metadata=Metadata(tempo=120),
        grooves=[MONEY_BEAT],
        sections=[
            Section(name="intro", bars=2, groove="money beat"),
            Section(name="breakdown", bars=2, groove="money beat", tempo=80),
        ],
    )
    ir = compile_song(song)
    # Intro bars use global tempo
    assert ir.bars[0].tempo == 120
    assert ir.bars[1].tempo == 120
    # Breakdown bars use section tempo
    assert ir.bars[2].tempo == 80
    assert ir.bars[3].tempo == 80


def test_compile_section_tempo_stored_on_irsection():
    """Effective tempo is stored on IRSection too."""
    song = Song(
        metadata=Metadata(tempo=120),
        grooves=[MONEY_BEAT],
        sections=[
            Section(name="intro", bars=1, groove="money beat"),
            Section(name="breakdown", bars=1, groove="money beat", tempo=60),
        ],
    )
    ir = compile_song(song)
    assert ir.sections[0].tempo == 120
    assert ir.sections[1].tempo == 60


def test_compile_global_tempo_used_when_no_section_override():
    """When no section tempo is set, global metadata tempo is used."""
    song = Song(
        metadata=Metadata(tempo=100),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=2, groove="money beat")],
    )
    ir = compile_song(song)
    for bar in ir.bars:
        assert bar.tempo == 100


def test_compile_no_tempo_gives_none():
    """When neither global nor section tempo is set, IRBar.tempo is None."""
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[Section(name="verse", bars=2, groove="money beat")],
    )
    ir = compile_song(song)
    for bar in ir.bars:
        assert bar.tempo is None


def test_compile_like_section_inherits_tempo():
    """A section using `like` inherits the original section's tempo override."""
    song = Song(
        metadata=Metadata(tempo=120),
        grooves=[MONEY_BEAT],
        sections=[
            Section(name="verse", bars=2, groove="money beat", tempo=90),
            Section(name="verse 2", bars=None, groove=None, inherit=InheritSpec(parent="verse")),
        ],
    )
    ir = compile_song(song)
    # verse 2 bars should use tempo=90 (inherited from verse)
    assert ir.bars[2].tempo == 90
    assert ir.bars[3].tempo == 90


# ---------------------------------------------------------------------------
# Section arrangement: play: block — compiler tests
# ---------------------------------------------------------------------------

from groovescript.ast_nodes import PlayBar, PlayGroove, PlayRest


def _make_play_song(play_items, fills=None, variations=None, tempo=120):
    """Minimal Song with a single play: section."""
    return Song(
        metadata=Metadata(tempo=tempo),
        grooves=[MONEY_BEAT],
        fills=fills or [],
        sections=[
            Section(
                name="verse",
                bars=None,
                groove=None,
                play=play_items,
                fills=fills or [],
                variations=variations or [],
            )
        ],
    )


def test_compile_play_groove_expands_bars():
    song = _make_play_song([PlayGroove(groove_name="money beat", repeat=4)])
    ir = compile_song(song)
    assert len(ir.bars) == 4


def test_compile_play_groove_multi_bar_tiling():
    """A multi-bar groove repeated twice yields 4 bars total."""
    two_bar = Groove(
        name="two bar",
        bars=[
            [PatternLine("BD", ["1", "3"]), PatternLine("SN", ["2", "4"]), PatternLine("HH", StarSpec(note_value=8))],
            [PatternLine("BD", ["1", "2&"]), PatternLine("SN", ["2", "4"]), PatternLine("HH", StarSpec(note_value=8))],
        ],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[two_bar],
        fills=[],
        sections=[
            Section(name="v", bars=None, groove=None, play=[PlayGroove("two bar", repeat=2)])
        ],
    )
    ir = compile_song(song)
    assert len(ir.bars) == 4  # 2 groove bars × 2 repeats


def test_compile_play_rest_is_empty_and_flagged():
    song = _make_play_song([PlayGroove("money beat", 2), PlayRest(repeat=2)])
    ir = compile_song(song)
    assert len(ir.bars) == 4
    assert ir.bars[0].is_rest is False
    assert ir.bars[1].is_rest is False
    assert ir.bars[2].is_rest is True
    assert ir.bars[3].is_rest is True
    assert ir.bars[2].events == []
    assert ir.bars[3].events == []


def test_compile_play_bar_definition_events():
    bar_item = PlayBar(
        name="setup",
        pattern=[
            PatternLine("BD", ["1"]),
            PatternLine("CR", ["1"]),
        ],
        repeat=1,
    )
    song = _make_play_song([PlayGroove("money beat", 1), bar_item])
    ir = compile_song(song)
    assert len(ir.bars) == 2
    bar2 = ir.bars[1]
    instruments = {e.instrument for e in bar2.events}
    assert "BD" in instruments
    assert "CR" in instruments
    assert bar2.is_rest is False


def test_compile_play_bar_reference_shares_events():
    bar_item = PlayBar(
        name="setup",
        pattern=[PatternLine("CR", ["1"])],
        repeat=1,
    )
    ref_item = PlayBar(name="setup", pattern=None, repeat=1)
    song = _make_play_song([bar_item, ref_item])
    ir = compile_song(song)
    assert len(ir.bars) == 2
    # Both bars should have CR at beat 1 (position 0)
    for bar in ir.bars:
        cr_events = [e for e in bar.events if e.instrument == "CR"]
        assert len(cr_events) == 1
        assert cr_events[0].beat_position == Fraction(0)


def test_compile_play_total_bars_matches_expansion():
    play_items = [
        PlayGroove("money beat", repeat=4),
        PlayBar("b", [PatternLine("BD", ["1"])], repeat=1),
        PlayRest(repeat=2),
        PlayGroove("money beat", repeat=4),
        PlayBar("b", None, repeat=1),  # reference
    ]
    song = _make_play_song(play_items)
    ir = compile_song(song)
    assert len(ir.bars) == 4 + 1 + 2 + 4 + 1


def test_compile_play_section_bar_numbers_are_sequential():
    song = _make_play_song([PlayGroove("money beat", 3), PlayRest(2)])
    ir = compile_song(song)
    numbers = [bar.number for bar in ir.bars]
    assert numbers == list(range(1, 6))


def test_compile_play_section_mark_on_first_bar_only():
    song = _make_play_song([PlayGroove("money beat", 3)])
    ir = compile_song(song)
    assert ir.bars[0].section_name == "verse"
    assert ir.bars[1].section_name is None
    assert ir.bars[2].section_name is None


def test_compile_play_section_bars_on_first_bar():
    song = _make_play_song([PlayGroove("money beat", 3), PlayRest(2)])
    ir = compile_song(song)
    assert ir.bars[0].section_bars == 5
    for bar in ir.bars[1:]:
        assert bar.section_bars is None


def test_compile_play_fill_resolves_to_correct_bar():
    fill = Fill(
        name="crash",
        bars=[FillBar("4", [FillLine("4", ["CR"])])],
    )
    bar_item = PlayBar("setup", [PatternLine("BD", ["1"])], repeat=1)
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[fill],
        sections=[
            Section(
                name="verse",
                bars=None,
                groove=None,
                play=[PlayGroove("money beat", 3), bar_item],
                fills=[FillPlacement(fill_name="crash", bar=4)],
            )
        ],
    )
    ir = compile_song(song)
    assert len(ir.bars) == 4
    bar4 = ir.bars[3]
    assert any(e.instrument == "CR" for e in bar4.events)


def test_compile_play_fill_replaces_rest_bar():
    fill = Fill(
        name="crash",
        bars=[FillBar("4", [FillLine("4", ["CR"])])],
    )
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        fills=[fill],
        sections=[
            Section(
                name="verse",
                bars=None,
                groove=None,
                play=[PlayGroove("money beat", 1), PlayRest(2)],
                fills=[FillPlacement(fill_name="crash", bar=2)],
            )
        ],
    )
    ir = compile_song(song)
    # Bar 2 was a rest but the fill replaced it; is_rest should be False
    assert ir.bars[1].is_rest is False
    assert any(e.instrument == "CR" for e in ir.bars[1].events)
    # Bar 3 remains a rest
    assert ir.bars[2].is_rest is True


def test_compile_play_bar_subdivision_inherits_last_groove():
    """A play bar without explicit subdivision inherits from the preceding groove."""
    bar_item = PlayBar("b", [PatternLine("BD", ["1"])], repeat=1)
    song = _make_play_song([PlayGroove("money beat", 1), bar_item])
    ir = compile_song(song)
    # money beat has subdivision=8; inherited
    assert ir.bars[1].subdivision == 8


def test_compile_play_unknown_groove_raises():
    song = _make_play_song([PlayGroove("no such groove", 1)])
    with pytest.raises(ValueError, match="unknown groove"):
        compile_song(song)


def test_compile_play_unknown_bar_reference_raises():
    song = _make_play_song([PlayBar("ghost", None, repeat=1)])
    with pytest.raises(ValueError, match="referenced before it was defined"):
        compile_song(song)


def test_compile_play_duplicate_bar_name_raises():
    bar1 = PlayBar("dup", [PatternLine("BD", ["1"])], repeat=1)
    bar2 = PlayBar("dup", [PatternLine("SN", ["2"])], repeat=1)
    song = _make_play_song([bar1, bar2])
    with pytest.raises(ValueError, match="duplicate bar name"):
        compile_song(song)


# ── Fill placeholder tests ──────────────────────────────────────────────────

def _make_placeholder_song(placeholders: list[FillPlaceholder], bars: int = 4) -> Song:
    return Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[
            Section(
                name="verse",
                bars=bars,
                groove="money beat",
                fill_placeholders=placeholders,
            )
        ],
    )


def test_compile_placeholder_attached_to_bar():
    """A placeholder at bar 2 with no beat should appear in bar 2's fill_placeholders."""
    song = _make_placeholder_song([FillPlaceholder(label="fill", bar=2)])
    ir = compile_song(song)
    bar2 = ir.bars[1]
    assert len(bar2.fill_placeholders) == 1
    pos, label = bar2.fill_placeholders[0]
    assert pos == Fraction(0)
    assert label == "fill"


def test_compile_placeholder_other_bars_empty():
    """Only the targeted bar carries the placeholder; others have none."""
    song = _make_placeholder_song([FillPlaceholder(label="fill", bar=2)])
    ir = compile_song(song)
    assert ir.bars[0].fill_placeholders == []
    assert ir.bars[2].fill_placeholders == []
    assert ir.bars[3].fill_placeholders == []


def test_compile_placeholder_custom_label():
    song = _make_placeholder_song([FillPlaceholder(label="build", bar=1)])
    ir = compile_song(song)
    _, label = ir.bars[0].fill_placeholders[0]
    assert label == "build"


def test_compile_placeholder_with_beat():
    """A placeholder at bar 1 beat 3 should be at Fraction(1, 2)."""
    song = _make_placeholder_song([FillPlaceholder(label="fill", bar=1, beat="3")])
    ir = compile_song(song)
    pos, label = ir.bars[0].fill_placeholders[0]
    assert pos == Fraction(1, 2)  # beat 3 of 4/4 with subdivision=8
    assert label == "fill"


def test_compile_placeholder_does_not_replace_events():
    """Placeholder leaves groove events intact (unlike a real fill)."""
    song = _make_placeholder_song([FillPlaceholder(label="fill", bar=1)])
    ir = compile_song(song)
    # money beat has BD, SN, HH — all events should still be present
    bar1_instruments = {e.instrument for e in ir.bars[0].events}
    assert "BD" in bar1_instruments
    assert "SN" in bar1_instruments
    assert "HH" in bar1_instruments


def test_compile_multiple_placeholders():
    song = _make_placeholder_song(
        [FillPlaceholder(label="fill", bar=2), FillPlaceholder(label="solo", bar=4)],
        bars=4,
    )
    ir = compile_song(song)
    assert len(ir.bars[1].fill_placeholders) == 1
    assert ir.bars[1].fill_placeholders[0][1] == "fill"
    assert len(ir.bars[3].fill_placeholders) == 1
    assert ir.bars[3].fill_placeholders[0][1] == "solo"


def test_compile_like_with_fills_inherits_placeholders():
    """``like … with fills`` sections inherit fill_placeholders from the original."""
    from groovescript.ast_nodes import Section as Sec
    song = Song(
        metadata=Metadata(),
        grooves=[MONEY_BEAT],
        sections=[
            Sec(name="verse", bars=4, groove="money beat",
                fill_placeholders=[FillPlaceholder(label="fill", bar=4)]),
            Sec(
                name="verse 2",
                bars=None,
                groove=None,
                inherit=InheritSpec(parent="verse", categories=frozenset({"fills"})),
            ),
        ],
    )
    ir = compile_song(song)
    # bars 5–8 are verse 2; bar 8 (offset 3) should carry the placeholder
    bar8 = ir.bars[7]
    assert len(bar8.fill_placeholders) == 1
    assert bar8.fill_placeholders[0][1] == "fill"


# ── 12/8 and double-digit beat label tests ─────────────────────────────────


def test_compile_12_8_beat_12_at_position_11_12():
    """12/8 with subdivision=12: beat 12 sits at 11/12 of the bar."""
    groove = Groove(
        name="twelve",
        bars=[[PatternLine(instrument="BD", beats=["1", "7", "12"])]],
    )
    ir = compile_groove(groove, beats_per_bar=12)
    positions = sorted(e.beat_position for e in ir.events)
    assert positions == [Fraction(0), Fraction(1, 2), Fraction(11, 12)]


def test_compile_12_8_beat_12_and_at_position_23_24():
    """12/8 with subdivision=24 unlocks the '&' suffix on double-digit beats."""
    groove = Groove(
        name="twelve-24",
        bars=[[PatternLine(instrument="SN", beats=["12&"])]],
    )
    ir = compile_groove(groove, beats_per_bar=12)
    assert [e.beat_position for e in ir.events] == [Fraction(23, 24)]


def test_compile_12_8_triplet_suffix_on_double_digit_beat():
    """With subdivision=36 (3 per beat), 12trip / 12let resolve to the expected slots."""
    groove = Groove(
        name="twelve-36",
        bars=[[PatternLine(instrument="HH", beats=["12t", "12l"])]],
    )
    ir = compile_groove(groove, beats_per_bar=12)
    positions = sorted(e.beat_position for e in ir.events)
    assert positions == [Fraction(34, 36), Fraction(35, 36)]


def test_compile_12_8_rejects_beat_13():
    groove = Groove(
        name="twelve",
        bars=[[PatternLine(instrument="BD", beats=["13"])]],
    )
    with pytest.raises(ValueError, match="out of range"):
        compile_groove(groove, beats_per_bar=12)


# ── per-section time signature tests ───────────────────────────────────────


def test_compile_section_time_signature_override():
    """A section with its own time_signature flows through to IRBar."""
    from groovescript.parser import parse
    src = """\
title: "mix"
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
    song = parse(src)
    ir = compile_song(song)
    # First two bars (verse) are 4/4, last two (outro) are 3/4.
    assert ir.bars[0].time_signature == "4/4"
    assert ir.bars[1].time_signature == "4/4"
    assert ir.bars[2].time_signature == "3/4"
    assert ir.bars[3].time_signature == "3/4"
    # The outro groove should have been recompiled against beats_per_bar=3.
    outro_bd_positions = sorted(
        e.beat_position for e in ir.bars[2].events if e.instrument == "BD"
    )
    # Waltz: BD at beat 1 → position 0 (out of 3 beats).
    assert outro_bd_positions == [Fraction(0)]


def test_compile_section_time_signature_inherits_via_like():
    from groovescript.parser import parse
    src = """\
title: "mix"
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
  groove: "waltz"
  time_signature: 3/4

section "outro":
  like "verse"
"""
    song = parse(src)
    ir = compile_song(song)
    # Both verse and outro should be in 3/4 because outro inherits time_signature.
    assert all(b.time_signature == "3/4" for b in ir.bars)


# ---------------------------------------------------------------------------
# Inline unnamed grooves inside a section
# ---------------------------------------------------------------------------

INLINE_GROOVE_SRC = """\
title: "Inline groove"
tempo: 120

section "chorus":
  bars: 2
  groove:
      BD: 1, 3
      SN: 2, 4
      crash: 1
"""


def test_compile_inline_groove_is_stored_on_section():
    """An inline groove body lands on Section.inline_grooves; Section.groove is rewritten to the synthetic name."""
    song = parse(INLINE_GROOVE_SRC)
    section = song.sections[0]
    assert len(section.inline_grooves) == 1
    assert isinstance(section.inline_grooves[0], Groove)
    assert section.groove is not None
    assert section.groove.startswith("__inline_groove_")
    assert section.groove == section.inline_grooves[0].name


def test_compile_inline_groove_compiles_and_renders():
    """An inline section groove compiles end-to-end and renders all of its instruments."""
    from groovescript.lilypond import emit_lilypond
    song = parse(INLINE_GROOVE_SRC)
    ir = compile_song(song)
    assert len(ir.bars) == 2
    ly = emit_lilypond(ir)
    assert "cymc" in ly  # crash rendered
    assert "bd" in ly
    assert "sn" in ly


def test_compile_inline_groove_infers_subdivision_from_pattern():
    src = """\
section "chorus":
  bars: 1
  groove:
      BD: 1, 3
      SN: 2, 4
      HH: *8
"""
    song = parse(src)
    ir = compile_song(song)
    assert ir.bars[0].subdivision == 8


def test_compile_inline_groove_inherited_through_like():
    src = """\
section "verse":
  bars: 2
  groove:
      BD: 1, 3
      HH: *8

section "verse 2":
  like "verse"
"""
    song = parse(src)
    ir = compile_song(song)
    # Two sections, each with 2 bars = 4 bars total.
    assert len(ir.bars) == 4


# ---------------------------------------------------------------------------
# Count+notes form for groove bodies
# ---------------------------------------------------------------------------

def test_compile_groove_count_notes_body_parses():
    """A count+notes groove body is stored on Groove.count_notes with empty bars."""
    src = """\
groove "run":
  count: 1 and 2 and 3 and 4 and
  notes: BD, HH, SN, HH, BD, HH, SN, HH

section "s":
  bars: 1
  groove: "run"
"""
    song = parse(src)
    groove = song.grooves[0]
    assert groove.count_notes is not None
    assert groove.bars == []


def test_compile_groove_count_notes_expands_to_events():
    """A count+notes groove body compiles to one event per hit in sequence."""
    src = """\
groove "run":
  count: 1 and 2 and 3 and 4 and
  notes: BD, HH, SN, HH, BD, HH, SN, HH

section "s":
  bars: 1
  groove: "run"
"""
    song = parse(src)
    ir = compile_song(song)
    bar = ir.bars[0]
    assert bar.subdivision == 8
    instruments = [e.instrument for e in sorted(bar.events, key=lambda e: e.beat_position)]
    assert instruments == ["BD", "HH", "SN", "HH", "BD", "HH", "SN", "HH"]


def test_compile_groove_count_notes_infers_16th_subdivision():
    src = """\
groove "fast":
  count: 1 e and a 2 e and a 3 e and a 4 e and a
  notes: HH, HH, HH, HH, HH, HH, HH, HH, HH, HH, HH, HH, HH, HH, HH, HH

section "s":
  bars: 1
  groove: "fast"
"""
    song = parse(src)
    ir = compile_song(song)
    assert ir.bars[0].subdivision == 16


def test_compile_groove_count_notes_simultaneous_hits_and_modifiers():
    """Paren groups and trailing modifiers in the notes string propagate into events."""
    src = """\
groove "shot":
  count: 1 and 2 and
  notes: (BD, CR) accent, HH, SN ghost, HH

section "s":
  bars: 1
  groove: "shot"
"""
    song = parse(src)
    ir = compile_song(song)
    bar = ir.bars[0]
    # Events at position 0: BD accent + CR accent
    at_zero = [e for e in bar.events if e.beat_position == 0]
    instruments = {e.instrument for e in at_zero}
    assert instruments == {"BD", "CR"}
    for event in at_zero:
        assert "accent" in event.modifiers
    # Ghost SN on beat 2 lands at 1/4 of the bar under an 8th grid.
    sn_events = [e for e in bar.events if e.instrument == "SN"]
    assert len(sn_events) == 1
    assert sn_events[0].beat_position == Fraction(1, 4)
    assert "ghost" in sn_events[0].modifiers


def test_compile_groove_count_notes_length_mismatch_errors():
    src = """\
groove "bad":
  count: 1 and 2 and
  notes: BD, HH, SN

section "s":
  bars: 1
  groove: "bad"
"""
    song = parse(src)
    with pytest.raises(ValueError, match="4 slot"):
        compile_song(song)


# ---------------------------------------------------------------------------
# `like:` section list merging (fills, variations)
# ---------------------------------------------------------------------------

def test_compile_like_section_appends_own_fills_on_top_of_inherited():
    """A `like:` section keeps inherited fills and adds its own; a new
    fill at the same bar replaces the inherited one."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "roll":
  count: "1 e and a"
  notes: "SN, SN, SN, SN"

fill "shot":
  count: "1 and"
  notes: "(BD, CR), SN"

section "verse":
  bars: 4
  groove: "beat"
  fill "roll" at bar 2
  fill "roll" at bar 4

section "verse 2":
  like "verse" with fills
  fill "shot" at bar 4
"""
    song = parse(src)
    ir = compile_song(song)

    verse2 = [b for b in ir.bars if b.section_name == "verse 2"]
    start = ir.bars.index(verse2[0])
    verse2_bars = ir.bars[start : start + 4]

    # Bar 2 of verse 2: inherited "roll" (SN on 16ths).
    sn_events = [e for e in verse2_bars[1].events if e.instrument == "SN"]
    assert len(sn_events) >= 4

    # Bar 4 of verse 2: "shot" replaces the inherited "roll".
    bar4_events = verse2_bars[3].events
    instruments_bar4 = {e.instrument for e in bar4_events}
    assert "CR" in instruments_bar4
    sn_events_bar4 = [e for e in bar4_events if e.instrument == "SN"]
    assert len(sn_events_bar4) == 1


def test_compile_like_section_merges_variations():
    src = """\
groove "beat":
    BD: 1, 3
    HH: *8

section "a":
  bars: 2
  groove: "beat"
  variation at bar 1:
    add SN at 2

section "b":
  like "a" with variations
  variation at bar 2:
    add CR at 1
"""
    song = parse(src)
    ir = compile_song(song)
    b_bars = [b for b in ir.bars if b.section_name == "b"]
    start = ir.bars.index(b_bars[0])
    b_section = ir.bars[start : start + 2]

    # Bar 1: inherited SN variation still in effect.
    bar1_sn = [e for e in b_section[0].events if e.instrument == "SN"]
    assert len(bar1_sn) == 1

    # Bar 2: new CR variation in effect.
    bar2_cr = [e for e in b_section[1].events if e.instrument == "CR"]
    assert len(bar2_cr) == 1


def test_compile_like_section_without_own_extras_still_inherits():
    """Regression: ``like "x" with fills`` (no child extras) must still fully inherit the parent's fills."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "roll":
  count: "1 e and a"
  notes: "SN, SN, SN, SN"

section "verse":
  bars: 4
  groove: "beat"
  fill "roll" at bar 4

section "verse 2":
  like "verse" with fills
"""
    song = parse(src)
    ir = compile_song(song)
    verse2 = [b for b in ir.bars if b.section_name == "verse 2"]
    start = ir.bars.index(verse2[0])
    bar4 = ir.bars[start + 3]
    sn_events = [e for e in bar4.events if e.instrument == "SN"]
    assert len(sn_events) >= 4


# ---------------------------------------------------------------------------
# Variation substitute action (compile-level)
# ---------------------------------------------------------------------------

SUBSTITUTE_SRC = """\
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "chorus":
  bars: 2
  groove: "money beat"
  variation "shot" at bar 2:
    count: 1 and 2 and 3 and 4 and
    notes: BD, HH, SN, HH, BD, HH, SN, (BD CR)
"""


def test_compile_substitute_action_wipes_and_replaces_bar_events():
    """A substitute action drops every event from the target bar and replaces
    them with the expansion of the count+notes body."""
    song = parse(SUBSTITUTE_SRC)
    ir = compile_song(song)
    bars = ir.bars

    # Bar 1 still has the original groove.
    bar1_instruments = sorted(e.instrument for e in bars[0].events)
    assert bar1_instruments.count("HH") == 8
    assert bar1_instruments.count("BD") == 2
    assert bar1_instruments.count("SN") == 2

    # Bar 2: substituted events only.
    bar2 = bars[1]
    positions = sorted({e.beat_position for e in bar2.events})
    assert positions == [Fraction(i, 8) for i in range(8)]
    last_instruments = {e.instrument for e in bar2.events if e.beat_position == Fraction(7, 8)}
    assert last_instruments == {"BD", "CR"}
    beat1_instruments = {e.instrument for e in bar2.events if e.beat_position == 0}
    assert beat1_instruments == {"BD"}  # no stray HH from the original groove


def test_compile_substitute_action_infers_subdivision():
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    count: 1 e and a 2 e and a 3 e and a 4 e and a
    notes: HH, SN, HH, SN, HH, SN, HH, SN, HH, SN, HH, SN, HH, SN, HH, SN
"""
    song = parse(src)
    ir = compile_song(song)
    bar2 = ir.bars[1]
    assert bar2.subdivision == 16
    assert len([e for e in bar2.events if e.instrument == "SN"]) == 8


def test_compile_substitute_action_unquoted_count_notes():
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    count: 1 2 3 4
    notes: BD, SN, BD, SN
"""
    song = parse(src)
    assert song.sections[0].variations[0].actions[0].action == "substitute"
    ir = compile_song(song)
    bar2 = ir.bars[1]
    instruments = [e.instrument for e in sorted(bar2.events, key=lambda e: e.beat_position)]
    assert instruments == ["BD", "SN", "BD", "SN"]


def test_compile_substitute_action_length_mismatch_errors():
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    count: 1 2 3 4
    notes: BD, SN
"""
    song = parse(src)
    with pytest.raises(ValueError, match="4 slot"):
        compile_song(song)


# ---------------------------------------------------------------------------
# Multi-instrument variation actions (compile-level)
# ---------------------------------------------------------------------------

def test_compile_variation_remove_multiple_instruments_and_beats():
    """`remove snare hat at 2, 3` strips both instruments at both beats."""
    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    remove snare hat at 2, 3
"""
    song = parse(src)
    ir = compile_song(song)
    bar2 = ir.bars[1]
    sn_positions = sorted(e.beat_position for e in bar2.events if e.instrument == "SN")
    assert Fraction(1, 4) not in sn_positions  # beat 2
    assert Fraction(3, 4) in sn_positions       # beat 4 remains
    hh_positions = sorted(e.beat_position for e in bar2.events if e.instrument == "HH")
    assert Fraction(1, 4) not in hh_positions
    assert Fraction(1, 2) not in hh_positions
    assert Fraction(0) in hh_positions


def test_compile_variation_add_multiple_instruments():
    """`add snare kick at 1` lands both instruments at beat 1."""
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    add snare kick at 1
"""
    song = parse(src)
    actions = song.sections[0].variations[0].actions
    assert [a.instrument for a in actions] == ["SN", "BD"]
    ir = compile_song(song)
    bar2 = ir.bars[1]
    at_zero = {e.instrument for e in bar2.events if e.beat_position == 0}
    assert {"SN", "BD"} <= at_zero


# ---------------------------------------------------------------------------
# Comma-free simultaneous-hit groups (compile-level)
# ---------------------------------------------------------------------------

def test_compile_comma_free_simultaneous_group_in_groove_count_notes():
    """`(bass crash)` inside a groove count+notes body is equivalent to `(bass, crash)`."""
    src = """\
groove "shot":
  count: 1 and 2 and
  notes: (bass crash), hat, snare, hat

section "s":
  bars: 1
  groove: "shot"
"""
    song = parse(src)
    ir = compile_song(song)
    at_zero = {e.instrument for e in ir.bars[0].events if e.beat_position == 0}
    assert at_zero == {"BD", "CR"}


def test_compile_comma_free_simultaneous_group_in_substitute_action():
    """`(bass crash)` inside a substitute-action notes string also works."""
    src = """\
groove "beat":
    HH: *8

section "s":
  bars: 2
  groove: "beat"
  variation at bar 2:
    count: 1 2 3 4
    notes: (bass crash), snare, bass, snare
"""
    song = parse(src)
    ir = compile_song(song)
    at_zero = {e.instrument for e in ir.bars[1].events if e.beat_position == 0}
    assert at_zero == {"BD", "CR"}


# ---------------------------------------------------------------------------
# Mixed subdivision: triplet + straight content in the same bar
# ---------------------------------------------------------------------------


def test_compile_mixed_triplet_and_eighth_in_groove():
    """Regression test: triplet and 8th labels can coexist in a single bar.

    This was previously rejected with 'cannot mix triplet and 16th/8th content'.
    """
    groove = Groove(
        name="mixed",
        bars=[
            [
                PatternLine(instrument="HH", beats=StarSpec(note_value=8)),
                PatternLine(instrument="BD", beats=["1", "3"]),
                PatternLine(instrument="SN", beats=["2t", "2l", "4t", "4l"]),
            ]
        ],
    )
    ir = compile_groove(groove)
    # 8th star needs 2 per beat; triplet labels need 3 per beat → lcm = 6 → 24 slots
    assert ir.subdivision == 24
    # HH should appear 8 times (every 8th note)
    hh_events = [e for e in ir.events if e.instrument == "HH"]
    assert len(hh_events) == 8
    # SN should appear 4 times (2t, 2l, 4t, 4l)
    sn_events = [e for e in ir.events if e.instrument == "SN"]
    assert len(sn_events) == 4
    # Triplet positions should be correct
    assert sn_events[0].beat_position == Fraction(1, 4) + Fraction(1, 3) / 4  # 2t
    assert sn_events[1].beat_position == Fraction(1, 4) + Fraction(2, 3) / 4  # 2l


def test_compile_mixed_triplet_and_sixteenth_in_groove():
    """Regression test: triplet and 16th labels can coexist in a single bar."""
    groove = Groove(
        name="mixed16",
        bars=[
            [
                PatternLine(instrument="BD", beats=["1", "1e", "1&", "1a"]),
                PatternLine(instrument="SN", beats=["3t", "3l"]),
            ]
        ],
    )
    ir = compile_groove(groove)
    # 16th labels need 4 per beat; triplet labels need 3 per beat → lcm = 12 → 48 slots
    assert ir.subdivision == 48
    # BD at 1, 1e, 1&, 1a
    bd_events = [e for e in ir.events if e.instrument == "BD"]
    assert len(bd_events) == 4
    assert bd_events[0].beat_position == Fraction(0)       # 1
    assert bd_events[1].beat_position == Fraction(1, 16)   # 1e
    assert bd_events[2].beat_position == Fraction(1, 8)    # 1&
    assert bd_events[3].beat_position == Fraction(3, 16)   # 1a
    # SN at 3t, 3l
    sn_events = [e for e in ir.events if e.instrument == "SN"]
    assert len(sn_events) == 2
    assert sn_events[0].beat_position == Fraction(1, 2) + Fraction(1, 3) / 4  # 3t
    assert sn_events[1].beat_position == Fraction(1, 2) + Fraction(2, 3) / 4  # 3l


def test_parse_file_fixture_mixed_subdivision():
    """End-to-end: mixed_subdivision.gs exercises both 8th+triplet and
    16th+triplet in the same bar, across a full song."""
    from pathlib import Path
    from groovescript.parser import parse_file

    fixtures = Path(__file__).parent / "fixtures"
    song = parse_file(str(fixtures / "mixed_subdivision.gs"))
    assert song.metadata.title == "Mixed Subdivision Test"
    ir = compile_song(song)
    # Section 1 (8th+triplet): lcm(2,3)*4 = 24 slots.
    for bar in ir.bars[:4]:
        assert bar.subdivision == 24
    # Section 2 (16th+triplet): lcm(4,3)*4 = 48 slots.
    for bar in ir.bars[4:]:
        assert bar.subdivision == 48


def test_compile_mixed_count_notes_groove():
    """Mixed subdivision in a count+notes groove."""
    from groovescript.parser import parse

    src = """\
groove "mixed-cn":
  count: "1 & 2 trip let 3 & 4"
  notes: "BD HH SN SN SN BD HH SN"

section "s":
  bars: 1
  groove: "mixed-cn"
"""
    song = parse(src)
    ir = compile_song(song)
    assert len(ir.bars) == 1
    # 8th (&) needs 2 per beat, triplet needs 3 → lcm(3,2)=6 → subdivision=24
    assert ir.bars[0].subdivision == 24


def test_compile_mixed_fill_subdivision():
    """A fill can mix triplet and straight beat labels."""
    from groovescript.parser import parse

    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "mixed-fill":
  count "3 & 4 trip let":
    3: SN
    3&: SN
    4: BD, CR
    4t: SN
    4l: SN

section "s":
  bars: 4
  groove: "beat"
  fill "mixed-fill" at bar 4 beat 3
"""
    song = parse(src)
    ir = compile_song(song)
    assert len(ir.bars) == 4
    # Fill bar should have mixed subdivision
    fill_bar = ir.bars[3]
    assert fill_bar.subdivision >= 24  # lcm(3,2)*4 = 24


# ---------------------------------------------------------------------------
# Multi-bar fills
# ---------------------------------------------------------------------------


def test_compile_multi_bar_fill():
    """A fill with two count blocks spans two bars when placed."""
    from groovescript.parser import parse

    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "two-bar":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR
  count "1 2 3 4":
    1: BD, CR
    2: BD
    3: BD
    4: BD

section "verse":
  bars: 4
  groove: "beat"
  fill "two-bar" at bar 3 beat 3
"""
    song = parse(src)
    ir = compile_song(song)
    assert len(ir.bars) == 4
    # Bar 3: fill starts at beat 3, groove preserved before that
    bar3 = ir.bars[2]
    hh_in_bar3 = [e for e in bar3.events if e.instrument == "HH"]
    assert len(hh_in_bar3) > 0  # groove events before beat 3 preserved
    sn_in_bar3 = [e for e in bar3.events if e.instrument == "SN"]
    assert any(e.beat_position >= Fraction(1, 2) for e in sn_in_bar3)  # fill hits at beat 3+
    # Bar 4: entirely replaced by fill bar 2
    bar4 = ir.bars[3]
    instruments = {e.instrument for e in bar4.events}
    assert instruments == {"BD", "CR"}  # only BD and CR from fill bar 2
    assert len(bar4.events) == 5  # 1: BD+CR, 2: BD, 3: BD, 4: BD


def test_compile_default_groove_and_bars():
    """Sections can omit bars/groove when metadata provides defaults."""
    from groovescript.parser import parse

    src = """\
metadata:
  tempo: 120
  default_groove: "rock"
  default_bars: 8

groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "half-time":
    BD: 1
    SN: 3
    HH: *8

section "verse":
  // uses defaults: groove "rock", bars 8

section "chorus":
  groove: "half-time"
  // uses default_bars: 8

section "bridge":
  bars: 4
  // uses default_groove: "rock"
"""
    song = parse(src)
    ir = compile_song(song)
    assert len(ir.bars) == 20  # 8 + 8 + 4
    # Verse uses default groove (rock)
    assert ir.bars[0].events  # not empty
    # Bridge uses only 4 bars
    assert ir.sections[2].bars == 4


def test_compile_multi_bar_fill_truncated_at_section_end():
    """A multi-bar fill that extends past the section boundary is truncated."""
    from groovescript.parser import parse

    src = """\
groove "beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "two-bar":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR
  count "1 2 3 4":
    1: BD, CR
    2: SN
    3: SN
    4: SN

section "verse":
  bars: 4
  groove: "beat"
  fill "two-bar" at bar 4 beat 3
"""
    song = parse(src)
    ir = compile_song(song)
    # Only 4 bars total: fill bar 1 applies to bar 4, fill bar 2 would be bar 5 — truncated
    assert len(ir.bars) == 4
    # Bar 4 should have the fill overlay (snare buildup from beat 3)
    bar4 = ir.bars[3]
    sn_in_bar4 = [e for e in bar4.events if e.instrument == "SN"]
    assert any(e.beat_position >= Fraction(1, 2) for e in sn_in_bar4)
