"""Render randomly generated charts through LilyPond and report warnings.

Complements ``test_fuzz_consistency.py`` (which checks MIDI and MusicXML
against the IR without external tools): this one needs the ``lilypond``
binary. It catches engraving problems -- bar-check failures, invalid
durations, unterminated ties or hairpins -- that only LilyPond notices, and
compares the drum onsets LilyPond itself plays (its own MIDI output of the
engraved music, repeats unfolded) against the IR, so notes the LilyPond
emitter silently drops are caught too.

    uv run python -m tests.fuzz_lilypond              # seeds 0-99
    uv run python -m tests.fuzz_lilypond 500 1000     # seeds 500-999
    uv run python -m tests.fuzz_lilypond --jobs 8 0 400

Exits non-zero if any seed fails, printing the seed, the LilyPond messages
and the chart source. Reproduce one with ``tests.fuzz_charts.generate(seed)``.
"""

from __future__ import annotations

import argparse
import struct
from collections import Counter
from fractions import Fraction
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from groovescript.compiler import compile_song
from groovescript.lilypond import emit_lilypond
from groovescript.parser import parse

from .fuzz_charts import generate

# LilyPond messages that are not about the chart itself.
_IGNORED = ("Changing working directory", "Processing", "Parsing", "Interpreting",
            "Preprocessing", "Finding", "Fitting", "Drawing", "Converting",
            "Layout output", "Success", "Element count", "Calculating",
            "Solving", "Copying")
# Layout notices: a dense random chart may overfill a page; not a bug.
_IGNORED_ANYWHERE = ("has been compressed", "compressing over-full page")


def _midi_drum_onsets(data: bytes) -> Counter:
    """Note-on ticks on the drum channel (10), as quarter notes."""
    division = struct.unpack(">H", data[12:14])[0]
    onsets: Counter = Counter()
    pos = 14
    while pos < len(data):
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + length]
        pos += 8 + length
        i, tick, status = 0, 0, 0
        while i < len(body):
            delta = 0
            while True:
                b = body[i]; i += 1
                delta = (delta << 7) | (b & 0x7F)
                if not b & 0x80:
                    break
            tick += delta
            if body[i] & 0x80:
                status = body[i]; i += 1
            if status == 0xFF:
                i += 1
                n = 0
                while True:
                    b = body[i]; i += 1
                    n = (n << 7) | (b & 0x7F)
                    if not b & 0x80:
                        break
                i += n
            elif status in (0xF0, 0xF7):
                n = 0
                while True:
                    b = body[i]; i += 1
                    n = (n << 7) | (b & 0x7F)
                    if not b & 0x80:
                        break
                i += n
            else:
                kind = status & 0xF0
                size = 1 if kind in (0xC0, 0xD0) else 2
                if kind == 0x90 and (status & 0x0F) == 9 and body[i + 1] > 0:
                    onsets[round(Fraction(tick, division) * 48)] += 1
                i += size
    return onsets


def _ir_onsets(song) -> Counter:
    """Drum onsets from the IR, in 48ths of a quarter (1/192 of a 4/4 bar)."""
    onsets: Counter = Counter()
    ts = song.metadata.time_signature
    start = Fraction(0)
    for bar in song.bars:
        ts = bar.time_signature or ts
        n, d = (int(x) for x in ts.split("/"))
        length = Fraction(4 * n, d)
        if not bar.is_rest:
            for e in bar.events:
                if not getattr(e, "tied_from_prev", False):
                    onsets[round((start + e.beat_position * length) * 48)] += 1
        start += length
    return onsets


def _diff(want: Counter, got: Counter) -> list[str]:
    def near(c: Counter, k: int) -> int:
        return c[k - 1] + c[k] + c[k + 1]  # LilyPond rounds tuplet ticks
    lines = []
    for k in sorted(set(want) | set(got)):
        if want[k] and near(got, k) < want[k]:
            lines.append(f"  missing {want[k] - near(got, k)} note(s) at quarter {Fraction(k, 48)}")
        elif got[k] and near(want, k) < got[k]:
            lines.append(f"  extra {got[k] - near(want, k)} note(s) at quarter {Fraction(k, 48)}")
    return lines


def _run_lilypond(ly: str, stem: Path) -> list[str]:
    stem.with_suffix(".ly").write_text(ly)
    proc = subprocess.run(
        ["lilypond", "--loglevel=WARN", "-dno-point-and-click", "-o", str(stem), str(stem.with_suffix(".ly"))],
        capture_output=True, text=True,
    )
    messages = [
        line for line in (proc.stdout + proc.stderr).splitlines()
        if line.strip() and not line.startswith(_IGNORED)
        and not any(text in line for text in _IGNORED_ANYWHERE)
    ]
    if proc.returncode != 0 and not messages:
        messages = [f"lilypond exited with {proc.returncode}"]
    return messages


def check_seed(seed: int, workdir: Path) -> tuple[int, str] | None:
    """``None`` if ``seed`` renders cleanly, else ``(seed, report)``."""
    src = generate(seed)
    try:
        song = compile_song(parse(src))
        ly = emit_lilypond(song, compact=True)
        # For the onset check: no vocal staff (it follows the *printed*
        # bars), repeats unfolded so LilyPond's MIDI plays every pass as the
        # IR does, and a \midi block.
        playback = emit_lilypond(song, compact=True, lyrics_style="off")
    except Exception as exc:  # noqa: BLE001 - any failure is a finding
        return seed, f"compile failed: {type(exc).__name__}: {exc}\n--- source ---\n{src}"
    messages = _run_lilypond(ly, workdir / f"fuzz{seed}")
    if messages:
        return seed, "\n".join(messages) + f"\n--- source ---\n{src}"
    playback = playback.replace("\\repeat volta", "\\repeat unfold")
    cut = playback.rstrip().rfind("}")
    playback = playback[:cut] + "  \\layout { }\n  \\midi { }\n}\n"
    stem = workdir / f"fuzz{seed}-play"
    messages = _run_lilypond(playback, stem)
    midi = next((p for p in (stem.with_suffix(".midi"), stem.with_suffix(".mid")) if p.exists()), None)
    if midi is None:
        return seed, "no MIDI from LilyPond:\n" + "\n".join(messages) + f"\n--- source ---\n{src}"
    diff = _diff(_ir_onsets(song), _midi_drum_onsets(midi.read_bytes()))
    if diff:
        return seed, "LilyPond's notes differ from the IR:\n" + "\n".join(diff[:12]) + f"\n--- source ---\n{src}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("start", nargs="?", type=int, default=0)
    parser.add_argument("stop", nargs="?", type=int, default=100)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)
    if shutil.which("lilypond") is None:
        print("lilypond is not installed", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        with ThreadPoolExecutor(args.jobs) as pool:
            results = list(pool.map(lambda s: check_seed(s, workdir), range(args.start, args.stop)))
    failures = [r for r in results if r is not None]
    for seed, report in failures:
        print(f"=== seed {seed} ===\n{report}\n")
    print(f"{len(failures)} of {args.stop - args.start} seeds failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
