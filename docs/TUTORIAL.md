# GrooveScript tutorial

This tutorial builds up a real drum chart in five iterations. Each
iteration is a usable chart on its own — you can stop at any point and
print what you have. By the end you will have a multi-section song
with grooves, fills, variations, and cues.

If you haven't installed GrooveScript yet, start with
[`GETTING_STARTED.md`](GETTING_STARTED.md). For a searchable reference of
every feature, see [`DSL_REFERENCE.md`](DSL_REFERENCE.md).

## Iteration 1 — form and tempo

The smallest useful chart: a title, a tempo, and the form as a list of
sections with bar counts. Every section renders as a **placeholder
groove** — empty bars with a "Section groove" label — so you can print
the form out and pencil in the groove by hand, or fill it in later.

```groovescript
title: "Tutorial Song"
tempo: 120

section "intro":
  bars: 4

section "verse":
  bars: 8

section "chorus":
  bars: 8

section "outro":
  bars: 4
```

- `title` appears as a large centered title on the rendered page.
- `tempo` sets the song-level BPM (displayed in the score header).
- Each section becomes a boxed rehearsal mark (`INTRO: 4`, `VERSE: 8`,
  …) showing the section name and bar count.
- `time_signature` defaults to `4/4`; override per song or per section
  when you need a different meter.

A section declaring `bars:` without a `groove:` is a placeholder — the
measure draws empty staff lines so the reader sees the form at a glance.

## Iteration 2 — grooves

Now pin a groove on each section. Define it once at the top of the file
and reference it by name. GrooveScript infers the bar's grid from what
you wrote — here the `*8` and quarter-note beats fit an 8th-note grid,
so the bar renders in 8ths.

```groovescript
title: "Tutorial Song"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 4
  groove: "money beat"

section "verse":
  bars: 8
  groove: "money beat"

section "chorus":
  bars: 8
  groove: "money beat"

section "outro":
  bars: 4
  groove: "money beat"
```

- Each line is either `INSTRUMENT: beats` (`BD: 1, 3`) or `beat:
  instruments` (`1: BD, HH`) — both are legal and mixable.
- `*8` means "a hit on every 8th note". The general form is `*N` (or
  `*Nt` for triplets), with N one of `2`, `4`, `8`, `16`.
- Instruments accept abbreviations (`BD`, `SN`, `HH`), lowercase, or
  verbose names (`kick`, `snare`, `hat`). Full list in
  [DSL reference → Instruments](DSL_REFERENCE.md#instruments).

GrooveScript also ships with a **library of common grooves** (`rock`,
`disco`, `funk`, `bossa-nova`, etc.) you can reference by name without
defining them. See
[DSL reference → Library of grooves](DSL_REFERENCE.md#library-of-grooves).

## Iteration 3 — fills

Now mark where fills go. Two styles: **placeholder fills** (just a
label, notes TBD) and **real fills** (explicit notes). Use placeholders
while you're still transcribing; swap them for real fills as you nail
the notes down.

```groovescript
title: "Tutorial Song"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "bar 4 fill":
  count "3 e & a 4":
    3:  SN
    3e: SN
    3&: SN
    3a: SN
    4:  BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "bar 4 fill" at bar 4 beat 3

section "verse":
  bars: 8
  groove: "money beat"
  fill at bar 8            // placeholder labelled "Fill"

section "chorus":
  bars: 8
  groove: "money beat"
  fill placeholder "build" at bar 8
```

Placeholder forms:

- `fill at bar N` → boxed "Fill" label, groove renders unchanged.
- `fill placeholder "build" at bar N` → custom label above the bar.

Real-fill forms:

- **Count-block syntax** — explicit beat labels on each line (shown in
  `"bar 4 fill"` above).
- **Count+notes syntax** — positional 1-to-1 alignment:

```groovescript
fill "bar 4 fill":
  count: "3 e & a 4"
  notes: "snare, snare, snare, snare, (bass, crash)"
```

Attach a real fill with `fill "name" at bar N` or `fill "name" at bar
N beat X` (runs from that beat to the end of the bar). If a fill only
appears once, skip the top-level definition and write it inline:

```groovescript
section "verse":
  bars: 8
  groove: "money beat"
  fill at bar 8 beat 3:
    count "3 e & a 4":
      3:  SN
      3e: SN
      3&: SN
      3a: SN
      4:  BD, CR
```

See [DSL reference → Fill](DSL_REFERENCE.md#fill) for simultaneous hits,
trailing modifiers, and triplet subdivisions.

## Iteration 4 — variations and refinements

A variation tweaks a single bar of the section's groove without defining
a whole new groove. Use this to add a crash, ghost a snare, or replace
a hi-hat with a ride for one bar. The name is optional:

```groovescript
section "chorus":
  bars: 8
  groove: "money beat"
  variation "chorus lift" at bar 8:
    replace HH with CR at 1
    add SN ghost at 2&
    replace SN with SN accent at 4
  variation at bar 4:
    add CR accent at 1
```

Supported actions: `add`, `remove`, `replace`, and `substitute` (wipes
the bar and replaces it with a count+notes body). Each action can
target one instrument or a space-separated list. Supported modifiers
are `ghost`, `accent`, `flam`, `drag`, and `double`.

Other useful refinements at this stage:

- **Section inheritance**: `section "verse 2": like "verse"` copies the
  basic arrangement; `like "verse" with fills, variations` opts into
  more.
- **Per-section tempo / time signature** overrides.
- **Dynamic spans**: `cresc from bar 5 to bar 8`.
- **Crash-in**: `crash in` replaces the first cymbal hit of bar 1 with
  a crash — a common section entry.

See [DSL reference → Variation actions](DSL_REFERENCE.md#variation-actions)
and the surrounding sections for full grammars.

## Iteration 5 — cues

Cues are italic text annotations placed at a specific bar/beat — vocal
entries, dynamic markings, "guitar solo", anything the drummer should
see. They don't affect the notes; they're purely informational.

```groovescript
section "chorus":
  bars: 8
  groove: "money beat"
  cue "vocals in" at bar 1
  cue "guitar solo" at bar 5 beat 1
```

## Putting it all together

```groovescript
title: "Tutorial Song"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "bar 4 fill":
  count "3 e & a 4":
    3:  SN
    3e: SN
    3&: SN
    3a: SN
    4:  BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "bar 4 fill" at bar 4 beat 3

section "verse":
  bars: 8
  groove: "money beat"
  fill placeholder "build" at bar 8
  cue "vocals in" at bar 1

section "chorus":
  bars: 8
  groove: "money beat"
  variation "chorus lift" at bar 8:
    replace HH with CR at 1
    add SN ghost at 2&
    replace SN with SN accent at 4
  cue "guitar solo" at bar 5
```

Save it as `charts/tutorial.gs` (use `./scaffold-chart tutorial` if you
haven't already) and build:

```bash
./build-pdf tutorial
```

`./build-pdf` compiles `charts/tutorial.gs` to LilyPond and then renders
the PDF alongside it — `charts/tutorial.pdf`.

From here, browse [`DSL_REFERENCE.md`](DSL_REFERENCE.md) for anything
this tutorial skipped: multi-bar grooves, triplet subdivisions, inline
unnamed grooves, the `play:` arrangement form, bar text, dynamic spans,
and more.
