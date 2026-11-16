"""Render randomly generated charts through LilyPond and report warnings.

Complements ``test_fuzz_consistency.py`` (which checks MIDI and MusicXML
against the IR without external tools): this one needs the ``lilypond``
binary and catches engraving problems -- bar-check failures, invalid
durations, unterminated ties or hairpins -- that only LilyPond notices.

    uv run python -m tests.fuzz_lilypond              # seeds 0-99
    uv run python -m tests.fuzz_lilypond 500 1000     # seeds 500-999
    uv run python -m tests.fuzz_lilypond --jobs 8 0 400

Exits non-zero if any seed fails, printing the seed, the LilyPond messages
and the chart source. Reproduce one with ``tests.fuzz_charts.generate(seed)``.
"""

from __future__ import annotations

import argparse
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


def check_seed(seed: int, workdir: Path) -> tuple[int, str] | None:
    """``None`` if ``seed`` renders cleanly, else ``(seed, report)``."""
    src = generate(seed)
    try:
        ly = emit_lilypond(compile_song(parse(src)), compact=True)
    except Exception as exc:  # noqa: BLE001 - any failure is a finding
        return seed, f"compile failed: {type(exc).__name__}: {exc}\n--- source ---\n{src}"
    ly_path = workdir / f"fuzz{seed}.ly"
    ly_path.write_text(ly)
    proc = subprocess.run(
        ["lilypond", "--loglevel=WARN", "-dno-point-and-click", "-o", str(workdir / f"fuzz{seed}"), str(ly_path)],
        capture_output=True, text=True,
    )
    messages = [
        line for line in (proc.stdout + proc.stderr).splitlines()
        if line.strip() and not line.startswith(_IGNORED)
    ]
    if proc.returncode != 0 or messages:
        return seed, "\n".join(messages) + f"\n--- source ---\n{src}"
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
