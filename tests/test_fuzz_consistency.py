"""Exporter consistency over randomly generated charts.

Each seed produces a valid chart (``tests/fuzz_charts.py``). The compiled IR
is the reference; MIDI and MusicXML must agree with it on:

* the number of bars and the length of every bar (from its meter);
* the onset of every drum hit.

Most bugs found by the hand audits were exactly this kind of mismatch (a
meter or tuplet one exporter got wrong), so this catches the next ones
automatically. Run more seeds with ``GS_FUZZ_SEEDS=2000 uv run pytest
tests/test_fuzz_consistency.py``; ``scripts/fuzz.py`` also renders each
chart through LilyPond and fails on its warnings.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction

import pytest

from groovescript.compiler import compile_song
from groovescript.midi import TICKS_PER_BEAT, _NOTE, emit_midi
from groovescript.musicxml import _DIVS_PER_BEAT, emit_musicxml
from groovescript.parser import parse

from .fuzz_charts import generate
from .test_midi import _collect_note_on, _parse_tracks

SEEDS = range(int(os.environ.get("GS_FUZZ_SEEDS", "150")))


def _bar_quarters(ts: str) -> Fraction:
    n, d = ts.split("/")
    return Fraction(int(n) * 4, int(d))


def _ir_bars(song):
    """[(meter, bar length in quarters, {(onset in quarters, instrument)})]."""
    out = []
    ts = song.metadata.time_signature
    for bar in song.bars:
        ts = bar.time_signature or ts
        length = _bar_quarters(ts)
        hits = Counter(
            (e.beat_position * length, e.instrument)
            for e in bar.events
            if not getattr(e, "tied_from_prev", False)
        )
        out.append((ts, length, hits))
    return out


def _check_midi(song, bars, src):
    tracks = _parse_tracks(emit_midi(song))
    drum = Counter()
    for track in tracks[1:]:
        for tick, pitch, _vel in _collect_note_on(track):
            drum[(tick, pitch)] += 1
    expected = Counter()
    start = Fraction(0)
    for _ts, length, hits in bars:
        for (onset, inst), n in hits.items():
            tick = round((start + onset) * TICKS_PER_BEAT)
            expected[(tick, _NOTE[inst])] += n
        start += length

    def _near(counter, key):
        tick, pitch = key
        return sum(counter[(t, pitch)] for t in (tick - 1, tick, tick + 1))

    missing = [k for k in expected if _near(drum, k) < expected[k]]
    extra = [k for k in drum if _near(expected, k) < drum[k]]
    assert not missing and not extra, (
        f"MIDI disagrees with the IR.\nmissing (tick, pitch): {missing[:8]}\n"
        f"extra: {extra[:8]}\n--- source ---\n{src}"
    )


def _parse_xml(data: bytes) -> ET.Element:
    text = data.decode("utf-8")
    text = re.sub(r"<\?xml[^?]*\?>", "", text)
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text, flags=re.DOTALL)
    return ET.fromstring(text.strip())


def _check_musicxml(song, bars, src):
    root = _parse_xml(emit_musicxml(song))
    parts = root.findall("part")
    assert parts, "no parts"
    for part in parts:
        measures = part.findall("measure")
        assert len(measures) == len(bars), (
            f"part {part.get('id')}: {len(measures)} measures for {len(bars)} bars"
            f"\n--- source ---\n{src}"
        )
        for idx, (measure, (ts, length, hits)) in enumerate(zip(measures, bars), 1):
            pos = 0
            onsets = Counter()
            for note in measure.iter("note"):
                if note.find("grace") is not None:
                    continue
                dur = int(note.findtext("duration"))
                if note.find("chord") is not None:
                    onset = last_onset
                else:
                    onset = pos
                    pos += dur
                last_onset = onset
                tied = any(t.get("type") == "stop" for t in note.findall("tie"))
                if note.find("rest") is None and not tied and part.get("id") == "P1":
                    onsets[onset] += 1
            want = int(length * _DIVS_PER_BEAT)
            assert pos == want, (
                f"part {part.get('id')} bar {idx} ({ts}): measure lasts {pos} "
                f"divisions, should be {want}\n--- source ---\n{src}"
            )
            if part.get("id") == "P1":
                expected = Counter()
                for (onset, _inst), n in hits.items():
                    expected[int(onset * _DIVS_PER_BEAT)] += n
                assert onsets == expected, (
                    f"bar {idx} ({ts}): MusicXML onsets {sorted(onsets.items())} "
                    f"!= IR {sorted(expected.items())}\n--- source ---\n{src}"
                )


@pytest.mark.parametrize("seed", SEEDS)
def test_exporters_agree_with_ir(seed):
    src = generate(seed)
    song = compile_song(parse(src))
    bars = _ir_bars(song)
    _check_midi(song, bars, src)
    _check_musicxml(song, bars, src)
