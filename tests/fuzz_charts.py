"""Seeded random generator of valid GrooveScript charts, for the exporter
consistency tests (``test_fuzz_consistency.py``) and ``scripts/fuzz.py``.

Every chart it produces is meant to compile. If one doesn't, either the
generator wrote something the language forbids (fix the generator) or the
compiler rejects valid input (a bug). Either way the failing test prints
the seed and the source.

Features beyond the basic arrangement (articulations, buzz rolls,
``extend:``, placeholders, multi-bar fills, ``crash in``, ``break on bar``,
backing vocals) are drawn from a second random stream, so adding one
doesn't reshuffle every existing seed's base chart. HH and OH never share
a beat (rejected by design).
"""

from __future__ import annotations

import random

METERS = ["4/4", "4/4", "3/4", "2/4", "5/4", "6/8", "7/8", "12/8"]
# CR is kept out of grooves so ``variation … add CR`` never collides.
HAND = ["HH", "SN", "RD", "FT", "HT", "MT", "CB"]
FEET = ["BD", "HF"]
MODS = ["", "", "", " accent", " ghost"]
SUFFIX_8 = ["", "&"]
SUFFIX_16 = ["", "e", "&", "a"]
SUFFIX_TRIP = ["", "t", "l"]


def _beats(ts: str) -> int:
    return int(ts.split("/")[0])


def _labels(
    rng: random.Random, bpb: int, k: int, grid: str, skip_beat: int | None = None
) -> list[str]:
    """``k`` distinct beat labels on ``grid`` ('8', '16' or 'trip'), never on
    ``skip_beat`` (a beat taken by a tuplet group)."""
    suffixes = {"8": SUFFIX_8, "16": SUFFIX_16, "trip": SUFFIX_TRIP}[grid]
    pool = [
        f"{b}{s}" for b in range(1, bpb + 1) for s in suffixes if b != skip_beat
    ]
    picks = rng.sample(pool, min(k, len(pool)))
    order = {lab: i for i, lab in enumerate(pool)}
    return sorted(picks, key=order.__getitem__)


def _pattern_line(
    rng: random.Random, inst: str, bpb: int, beat_unit: int, grid: str,
    skip_beat: int | None,
) -> str:
    style = rng.random()
    if skip_beat is None:
        # Star lines cover every beat, so only when no tuplet beat is taken.
        if style < 0.12 and grid != "trip":
            return f"{inst}: *{'8' if grid == '8' else '16'}"
        if style < 0.18 and beat_unit == 4:
            return f"{inst}: *8t"
    labels = _labels(rng, bpb, rng.randint(1, max(1, bpb * 2)), grid, skip_beat)
    if not labels:
        labels = [str(next(b for b in range(1, bpb + 1) if b != skip_beat))]
    return f"{inst}: " + ", ".join(lab + rng.choice(MODS) for lab in labels)


def _groove_lines(rng: random.Random, bpb: int, beat_unit: int) -> list[str]:
    grid = rng.choice(["8", "8", "16", "trip"])
    insts = rng.sample(HAND, rng.randint(1, 3)) + rng.sample(FEET, rng.randint(0, 1))
    tuplet_line = None
    skip_beat = None
    if rng.random() < 0.15 and bpb >= 2:
        # Every hit on a tuplet's beat must sit on its slots, so the other
        # lines stay off that beat entirely.
        skip_beat = rng.randint(1, bpb)
        kind, n = rng.choice([("triplet", 3), ("quintuplet", 5), ("sextuplet", 6)])
        slots = sorted(rng.sample(range(1, n + 1), rng.randint(1, n)))
        inst = rng.choice([i for i in HAND if i not in insts])
        tuplet_line = f"{inst}: {skip_beat}{{{kind} {', '.join(map(str, slots))}}}"
    lines = [_pattern_line(rng, inst, bpb, beat_unit, grid, skip_beat) for inst in insts]
    if tuplet_line:
        lines.append(tuplet_line)
    return lines


def _fill(rng: random.Random, name: str, bpb: int) -> tuple[list[str], int]:
    """A one-bar count+notes fill and the beat it starts on."""
    start = rng.randint(1, bpb)
    grid = rng.choice(["8", "16"])
    suffixes = SUFFIX_8 if grid == "8" else SUFFIX_16
    labels = [f"{b}{s}" for b in range(start, bpb + 1) for s in suffixes]
    labels = labels[: rng.randint(1, len(labels))]
    count = " ".join(labels)
    notes = ", ".join(rng.choice(["SN", "FT", "HT", "MT", "(BD CR)", "SN accent"]) for _ in labels)
    return ([f'fill "{name}":', f'  count: "{count}"', f'  notes: "{notes}"'], start)


def _articulate(xrng: random.Random, line: str, sixteenths: bool) -> str:
    """Maybe add a flam/drag (snare) or, on a plain 16th grid, a ``double``
    to one hit of a pattern line (not star or tuplet lines)."""
    inst, _, hits = line.partition(": ")
    if hits.startswith("*") or "{" in hits:
        return line
    items = hits.split(", ")
    i = xrng.randrange(len(items))
    label = items[i].split()[0]
    if inst == "SN" and xrng.random() < 0.3:
        items[i] = f"{label} {xrng.choice(['flam', 'drag'])}"
    elif sixteenths and xrng.random() < 0.15:
        # ``double`` needs exactly 4 slots per beat (a 16th grid).
        items[i] = f"{label} double"
    return f"{inst}: " + ", ".join(items)


def generate(seed: int) -> str:
    """Return the source of one random, valid chart."""
    rng = random.Random(seed)
    xrng = random.Random(seed * 7919 + 17)  # second stream: see module doc
    ts = rng.choice(METERS)
    bpb = _beats(ts)
    beat_unit = int(ts.split("/")[1])
    song_tempo = rng.choice([72, 96, 120, 144])
    out = [f'title: "fuzz {seed}"', f"tempo: {song_tempo}", f"time_signature: {ts}", ""]

    grooves = []
    for gi in range(rng.randint(1, 3)):
        name = f"g{gi}"
        grooves.append(name)
        out.append(f'groove "{name}":')
        lines = _groove_lines(rng, bpb, beat_unit)
        body = " ".join(line.partition(": ")[2] for line in lines)
        words = body.replace(",", " ").split()
        sixteenths = (
            (any(w[-1:] in ("e", "a") and w[0].isdigit() for w in words) or "*16" in words)
            and "{" not in body and "*8t" not in words
            and not any(w[-1:] in ("t", "l") and w[0].isdigit() for w in words)
        )
        out += [f"    {_articulate(xrng, line, sixteenths)}" for line in lines]
        out.append("")
    if xrng.random() < 0.25:
        # A buzz roll lasting one beat, alone on the snare.
        grooves.append("gb")
        # Not on beat 1: crashes land there (``crash in``, ``add CR at 1``)
        # and no hand can play during a buzz roll.
        out += ['groove "gb":', f"    SN: {xrng.randint(2, bpb)} buzz:{beat_unit}", "    BD: 1", ""]
    if xrng.random() < 0.25:
        # A derived groove: the base plus a splash (an instrument nothing
        # else uses, so no variation collides with it).
        grooves.append("gx")
        out += ['groove "gx":', '    extend: "g0"', "    SP: 1", ""]
    multibar_fill = xrng.random() < 0.2
    if multibar_fill:
        count = " ".join(str(b) for b in range(1, bpb + 1))
        out += [
            'fill "fm":',
            f'  count "{count}":',
            f"    SN: {' '.join(str(b) for b in range(1, bpb + 1))}",
            f'  count "{count}":',
            "    FT: 1",
            "    BD: 1",
            "",
        ]

    fills = []
    for fi in range(rng.randint(0, 2)):
        name = f"f{fi}"
        lines, start = _fill(rng, name, bpb)
        fills.append((name, start))
        out += lines + [""]

    for si in range(rng.randint(1, 4)):
        bars = rng.randint(1, 4)
        out.append(f'section "s{si}":')
        if si > 0 and rng.random() < 0.12:
            # Inherit an earlier section, optionally with its overlays.
            extra = rng.choice(["", " with fills", " with variations", " with fills, variations"])
            out.append(f'  like "s{rng.randrange(si)}"{extra}')
            out.append("")
            continue
        if rng.random() < 0.12:
            # A per-section meter with at least as many beats, so every
            # groove's beat labels still fit.
            wider = [
                m for m in ("4/4", "5/4", "6/8", "7/8", "12/8")
                if _beats(m) >= bpb and m != ts and m.endswith(f"/{beat_unit}")
            ]
            if wider:
                out.append(f"  time_signature: {rng.choice(wider)}")
        placeholder_bars: set[int] = set()  # variations can't target these
        if rng.random() < 0.2:
            # play: list mixing grooves and rests
            out.append("  play:")
            total = 0
            for _ in range(rng.randint(1, 3)):
                if rng.random() < 0.25:
                    n = rng.randint(1, 3)
                    out.append(f"    rest x{n}")
                elif xrng.random() < 0.15:
                    n = rng.randint(1, 2)
                    out.append(f"    groove placeholder x{n}")
                    placeholder_bars.update(range(total + 1, total + n + 1))
                else:
                    n = rng.randint(1, 2)
                    out.append(f'    groove "{rng.choice(grooves)}" x{n}')
                total += n
            bars = total
        elif xrng.random() < 0.08:
            out.append(f"  bars: {bars}")
            out.append("  groove: placeholder")
            placeholder_bars.update(range(1, bars + 1))
        else:
            out.append(f"  bars: {bars}")
            out.append(f'  groove: "{rng.choice(grooves)}"')
            if bars in (2, 4) and rng.random() < 0.2:
                out.append(f"  repeat: {rng.choice([d for d in (1, 2) if bars % d == 0])}")
        section_tempo = song_tempo
        if rng.random() < 0.25:
            section_tempo = rng.choice([80, 100, 132])
            out.append(f"  tempo: {section_tempo}")
        used_bars: set[int] = set(placeholder_bars)
        if xrng.random() < 0.12:
            out.append("  crash in")
        has_break = False
        if xrng.random() < 0.1:
            bar = xrng.randint(1, bars)
            if bar not in used_bars:
                used_bars.add(bar)
                has_break = True
                out.append(f"  break on bar {bar}")
        if multibar_fill and xrng.random() < 0.3:
            bar = xrng.randint(1, bars)
            if bar not in used_bars and bar + 1 not in used_bars:
                used_bars.update((bar, bar + 1))
                out.append(f'  fill "fm" at bar {bar}')
        if fills and rng.random() < 0.5:
            name, start = rng.choice(fills)
            bar = rng.randint(1, bars)
            used_bars.add(bar)
            beat = f" beat {start}" if start > 1 else ""
            out.append(f'  fill "{name}" at bar {bar}{beat}')
        if rng.random() < 0.4:
            bar = rng.randint(1, bars)
            if bar not in used_bars:
                used_bars.add(bar)
                out.append(f"  variation at bar {bar}:")
                out.append(f"    add CR at 1")
        if rng.random() < 0.15 and bpb >= 2:
            bar = rng.randint(1, bars)
            # A break may span several bars; none may change meter.
            if bar not in used_bars and not has_break:
                used_bars.add(bar)
                other = rng.choice([m for m in ("3/4", "2/4", "5/4", "6/8", "7/8") if m != ts])
                obpb = _beats(other)
                out.append(f"  variation at bar {bar}:")
                out.append(f"    time_signature: {other}")
                hits = ", ".join(str(b) for b in range(1, obpb + 1))
                out.append(f"    add SN at {hits}")
        if rng.random() < 0.2:
            bar = rng.randint(1, bars)
            out.append(f'  cue "c{si}" at bar {bar}')
        if rng.random() < 0.15:
            a = rng.randint(1, bars)
            b = rng.randint(a, bars)
            kind = rng.choice(["rit", "accel"])
            target = ""
            if rng.random() < 0.5:
                # A target must move the right way from the section tempo.
                t = section_tempo - 30 if kind == "rit" else section_tempo + 30
                target = f" to tempo {t}"
            out.append(f"  {kind} from bar {a} to bar {b}{target}")
        if rng.random() < 0.15:
            a = rng.randint(1, bars)
            b = rng.randint(a, bars)
            out.append(f"  {rng.choice(['cresc', 'decresc'])} from bar {a} to bar {b}")
        free = [b for b in range(1, bars + 1) if b not in used_bars]
        if free and rng.random() < 0.15:
            bar = rng.choice(free)
            words = " ".join(f"la{i}" for i in range(1, min(bpb, 3) + 1))
            count = " ".join(str(b) for b in range(1, min(bpb, 3) + 1))
            out.append("  lyrics:")
            out.append(f'    bar {bar}: "{count}" "{words}"')
            if xrng.random() < 0.4:
                out.append('  lyrics "bv":')
                out.append(f'    bar {bar}: "1" "ooh"')
        out.append("")
    return "\n".join(out)
