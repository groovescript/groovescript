"""Gradual tempo changes: ``rit`` / ``accel`` spans and ``a tempo``."""

import xml.etree.ElementTree as ET
from fractions import Fraction

import pytest

from groovescript.compiler import compile_song
from groovescript.errors import GrooveScriptError
from groovescript.lilypond import emit_lilypond
from groovescript.midi import TICKS_PER_BEAT, emit_midi
from groovescript.musicxml import emit_musicxml
from groovescript.parser import parse

HEAD = """\
tempo: 120
groove "g":
  BD: 1, 3
  SN: 2, 4
  HH: *8
"""


def _song(body: str):
    return compile_song(parse(HEAD + body))


def _section(lines: str, bars: int = 4, name: str = "verse") -> str:
    indented = "".join(f"  {line}\n" for line in lines.strip().splitlines())
    return f'section "{name}":\n  bars: {bars}\n  groove: "g"\n{indented}'


def _midi_tempos(data: bytes) -> list[tuple[int, float]]:
    """(tick, bpm) for every Set Tempo event in the file's first track."""
    assert data[:4] == b"MThd"
    i = 14
    assert data[i:i + 4] == b"MTrk"
    length = int.from_bytes(data[i + 4:i + 8], "big")
    body = data[i + 8:i + 8 + length]
    out, j, tick = [], 0, 0
    while j < len(body):
        delta = 0
        while True:
            c = body[j]
            j += 1
            delta = (delta << 7) | (c & 0x7F)
            if not c & 0x80:
                break
        tick += delta
        assert body[j] == 0xFF
        kind, size = body[j + 1], body[j + 2]
        if kind == 0x51:
            us = int.from_bytes(body[j + 3:j + 6], "big")
            out.append((tick, round(60_000_000 / us, 2)))
        j += 3 + size
    return out


def _tempo_at(tempos: list[tuple[int, float]], tick: int) -> float:
    return [bpm for t, bpm in tempos if t <= tick][-1]


BAR = 4 * TICKS_PER_BEAT  # one 4/4 bar


# ── Parsing ──────────────────────────────────────────────────────────────────

def test_parses_every_form():
    song = parse(HEAD + _section("""
rit from bar 1 to bar 2
ritardando from bar 2 beat 3 to bar 3 to tempo 90
accel from bar 3 to bar 4 beat 2&
accelerando from bar 1 beat 2 to bar 1 beat 4 to tempo 150
a tempo at bar 4
a tempo at bar 4 beat 3
"""))
    section = song.sections[0]
    spans = [(t.kind, t.from_bar, t.from_beat, t.to_bar, t.to_beat, t.target) for t in section.tempo_spans]
    assert spans == [
        ("rit", 1, None, 2, None, None),
        ("rit", 2, "3", 3, None, 90),
        ("accel", 3, None, 4, "2&", None),
        ("accel", 1, "2", 1, "4", 150),
    ]
    assert [(a.bar, a.beat) for a in section.a_tempos] == [(4, None), (4, "3")]
    assert all(t.line for t in section.tempo_spans + section.a_tempos)


def test_bare_a_is_not_a_keyword():
    """``a tempo`` is one terminal, so ``1a``-style beat labels and other
    words beginning with ``a`` (``accent``, ``add``) still parse."""
    src = HEAD.replace("SN: 2, 4", "SN: 2, 4a accent") + _section("""
rit from bar 1 to bar 1
a tempo at bar 2
variation at bar 3:
  add CR at 1
""")
    section = parse(src).sections[0]
    assert [(a.bar, a.beat) for a in section.a_tempos] == [(2, None)]
    assert len(section.variations) == 1


# ── IR tempo curve ───────────────────────────────────────────────────────────

def test_rit_ramps_linearly_to_target_and_holds():
    ir = _song(_section("rit from bar 2 to bar 2 to tempo 80"))
    b1, b2, b3, b4 = ir.bars
    assert b1.tempo_points == []
    # 4 steps per beat over one 4/4 bar: 16 points, each at the tempo the
    # curve reaches at the end of its step.
    assert len(b2.tempo_points) == 16
    assert b2.tempo_points[0] == (Fraction(0), 117.5)
    assert b2.tempo_points[-1] == (Fraction(15, 16), 80.0)
    bpms = [bpm for _, bpm in b2.tempo_points]
    assert bpms == sorted(bpms, reverse=True)
    # Held: later bars in the section carry no points (nominal stays 120).
    assert b3.tempo_points == b4.tempo_points == []
    assert b2.tempo_span_starts == [(Fraction(0), "rit")]
    # Ends at the end of the bar it starts in.
    from groovescript.compiler import END_OF_SPAN_BAR
    assert b2.tempo_span_stops == [END_OF_SPAN_BAR]


def test_default_targets_are_80_and_120_percent():
    ir = _song(_section("rit from bar 1 to bar 1\na tempo at bar 2\naccel from bar 3 to bar 3"))
    assert ir.bars[0].tempo_points[-1][1] == 96.0
    assert ir.bars[2].tempo_points[-1][1] == 144.0


def test_span_with_beats_starts_and_ends_mid_bar():
    ir = _song(_section("accel from bar 1 beat 3 to bar 2 beat 2 to tempo 132"))
    first, second = ir.bars[0], ir.bars[1]
    assert first.tempo_points[0][0] == Fraction(1, 2)
    assert first.tempo_span_starts == [(Fraction(1, 2), "accel")]
    assert second.tempo_points[-1] == (Fraction(3, 16), 132.0)
    assert second.tempo_span_stops == [Fraction(1, 4)]


def test_a_tempo_returns_to_section_tempo():
    ir = _song(_section("rit from bar 1 to bar 1 to tempo 100\na tempo at bar 3 beat 2"))
    assert ir.bars[2].tempo_points == [(Fraction(1, 4), 120.0)]
    assert ir.bars[2].tempo_texts == [(Fraction(1, 4), "a tempo")]


def test_held_change_is_undone_at_next_section_with_a_tempo():
    ir = _song(_section("rit from bar 4 to bar 4") + _section("", name="chorus"))
    chorus = ir.bars[4]
    assert chorus.tempo_points == [(Fraction(0), 120.0)]
    assert chorus.tempo_texts == [(Fraction(0), "a tempo")]


def test_next_section_with_its_own_tempo_needs_no_a_tempo():
    src = _section("rit from bar 4 to bar 4") + _section("tempo: 140", name="chorus")
    chorus = _song(src).bars[4]
    assert chorus.tempo_points == [] and chorus.tempo_texts == []


def test_like_inherits_tempo_changes():
    src = _section("rit from bar 4 to bar 4") + 'section "verse 2":\n  like "verse"\n'
    ir = _song(src)
    assert ir.bars[7].tempo_span_starts == [(Fraction(0), "rit")]


# ── Validation ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lines, message", [
    ("rit from bar 3 to bar 2", "ends before it starts"),
    ("rit from bar 1 to bar 9", "has 4 bars"),
    ("rit from bar 1 to bar 1 to tempo 130", "would not slow down"),
    ("accel from bar 1 to bar 1 to tempo 100", "would not speed up"),
    ("a tempo at bar 2", "already 120"),
    ("rit from bar 1 to bar 3\naccel from bar 2 to bar 4", "overlap"),
    ("rit from bar 1 to bar 3\na tempo at bar 2", "overlap"),
    ("rit from bar 1 beat 9 to bar 2", "rit"),
])
def test_invalid_tempo_changes_are_located_errors(lines, message):
    with pytest.raises(GrooveScriptError) as exc:
        _song(_section(lines))
    assert message in exc.value.message
    assert exc.value.line is not None


# ── MIDI ─────────────────────────────────────────────────────────────────────

def test_midi_plays_the_curve_and_restores():
    src = _section("rit from bar 3 to bar 4 to tempo 90") + _section("", name="chorus")
    tempos = _midi_tempos(emit_midi(_song(src)))
    assert _tempo_at(tempos, 0) == 120
    assert _tempo_at(tempos, 2 * BAR - 1) == 120
    assert 90 < _tempo_at(tempos, 3 * BAR) < 120  # mid-ramp
    assert _tempo_at(tempos, 4 * BAR - 1) == 90  # target reached at the end
    assert _tempo_at(tempos, 4 * BAR) == 120  # next section: back to tempo


def test_midi_holds_the_ramp_end_across_bar_lines():
    """Regression test: the MIDI emitter compared each bar's nominal tempo
    with the sounding tempo, so every bar after a ramp began snapped back
    to the section tempo (mid-ramp and while holding the rit's end)."""
    tempos = _midi_tempos(emit_midi(_song(_section("rit from bar 1 to bar 2 to tempo 90"))))
    assert all(bpm != 120 for tick, bpm in tempos if tick > 0)
    assert _tempo_at(tempos, 2 * BAR) == 90  # bar 3: still held
    assert _tempo_at(tempos, 4 * BAR - 1) == 90  # bar 4: still held


def test_midi_without_tempo_changes_is_unchanged():
    tempos = _midi_tempos(emit_midi(_song(_section(""))))
    assert tempos == [(0, 120.0)]


# ── LilyPond ─────────────────────────────────────────────────────────────────

def test_lilypond_prints_spanner_and_a_tempo():
    ly = emit_lilypond(_song(_section("rit from bar 2 to bar 3\na tempo at bar 4")))
    assert ly.count("\\startTextSpan") == 1
    assert '\\italic "rit."' in ly
    assert ly.count("\\stopTextSpan") == 1
    assert ly.index("\\startTextSpan") < ly.index("\\stopTextSpan")
    assert '"a tempo"' in ly


def test_span_snaps_onto_a_note_when_its_beat_is_empty():
    """The spanner must attach to a note; a start on an empty 16th slot
    moves to the next onset rather than silently vanishing."""
    ly = emit_lilypond(_song(_section("rit from bar 1 beat 1e to bar 2 beat 4e")))
    assert ly.count("\\startTextSpan") == 1
    assert ly.count("\\stopTextSpan") == 1


def test_bars_in_a_rit_do_not_compact_into_repeats():
    plain = emit_lilypond(_song(_section("", bars=8)))
    assert "\\repeat volta" in plain
    ly = emit_lilypond(_song(_section("rit from bar 1 to bar 8", bars=8)))
    assert "\\repeat volta" not in ly


def test_two_hairpins_ending_on_one_note_print_one_stop():
    """Regression test: merging hairpin and tempo-span markup into shared
    position maps briefly emitted ``\\!\\!`` when two hairpins ended on the
    same note (the old set de-duplicated them)."""
    ly = emit_lilypond(_song(_section("cresc from bar 1 to bar 2\ndecresc from bar 2 beat 3 to bar 2")))
    assert "\\!\\!" not in ly


def test_section_tempo_change_alone_still_compacts():
    """Regression test: a plain per-section tempo change (no rit/accel) must
    not add tempo points, which would block repeat compaction."""
    same = _section("", bars=8) + _section("", bars=8, name="chorus")
    changed = _section("", bars=8) + _section("tempo: 90", bars=8, name="chorus")
    ir = _song(changed)
    assert all(not b.tempo_points for b in ir.bars)
    assert emit_lilypond(ir).count("\\repeat volta") == emit_lilypond(_song(same)).count("\\repeat volta")


# ── MusicXML ─────────────────────────────────────────────────────────────────

def test_musicxml_prints_words_at_their_beat():
    xml = emit_musicxml(_song(_section("rit from bar 2 beat 3 to bar 3\na tempo at bar 4")))
    root = ET.fromstring(xml)
    measures = root.findall(".//part/measure")
    words = {
        (m.get("number"), d.findtext("direction-type/words"), d.findtext("offset"), d.find("sound") is not None)
        for m in measures for d in m.findall("direction")
        if d.find("direction-type/words") is not None
    }
    assert ("2", "rit.", str(2 * 2520), False) in words
    assert ("4", "a tempo", None, True) in words


def test_ramp_in_compound_meter_uses_the_meters_beat_unit():
    """Regression test: in 6/8, ``tempo:`` counts eighth notes, so a rit to
    60 must end at 30 quarter notes per minute in the MIDI, the same
    conversion the section tempo gets (merged with the /8-meter tempo fix)."""
    src = (
        'time_signature: 6/8\ntempo: 120\n'
        'groove "g":\n  BD: 1, 4\n  HH: *8\n'
        + _section("rit from bar 1 to bar 2 to tempo 60", bars=2)
    )
    tempos = _midi_tempos(emit_midi(compile_song(parse(src))))
    assert tempos[0] == (0, 60.0)  # eighth = 120 → 60 quarters per minute
    assert tempos[-1][1] == 30.0
