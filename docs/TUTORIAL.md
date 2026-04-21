# GrooveScript tutorial

This tutorial builds up a real drum chart piece by piece. Each step
introduces one concept, and by the end you will have a multi-section song
with grooves, placeholder fills, variations, and real fills.

If you haven't installed GrooveScript yet, start with
[`GETTING_STARTED.md`](GETTING_STARTED.md). For a searchable reference of
every feature, see [`DSL_REFERENCE.md`](DSL_REFERENCE.md).

## Step 1 — metadata

Every chart starts with a few metadata fields. The only required one is
`title`; everything else has a sensible default.

```groovescript
title: "Tutorial Song"
tempo: 120
time_signature: 4/4
```

- `title` appears as a large centered title on the rendered page.
- `tempo` sets the song-level BPM (displayed in the score header).
- `time_signature` sets the meter. If omitted, defaults to `4/4`.

You don't have to pick a subdivision — GrooveScript infers the grid of
each bar from the beat labels and stars you write.

## Step 2 — form and sections

A GrooveScript song is an ordered list of **sections**. File order is song
order. The simplest section just plays a groove for N bars:

```groovescript
section "intro":
  bars: 4
  groove: "money beat"

section "verse":
  bars: 8
  groove: "money beat"

section "chorus":
  bars: 8
  groove: "money beat"
```

Each section becomes a boxed rehearsal mark above the staff (`INTRO`,
`VERSE`, `CHORUS`) showing the section name and bar range.

If two sections share most of their content, use `like` to inherit:

```groovescript
section "verse 2":
  like "verse"
  # add overrides or additions here
```

By default, bare `like` copies only the basic arrangement (bars, groove,
tempo, time signature, inline grooves, section-level dynamics, and any
`crash in` flag). To also inherit fills, variations, or cues, list the
categories after `with`:

```groovescript
section "chorus 2":
  like "chorus" with fills, variations
```

The three categories (`fills`, `variations`, `cues`) are order-insensitive
and commas between them are optional.

For more complex arrangements you can replace `bars:` / `groove:` with a
`play:` block that lists grooves, one-off bars, and rests in order — see
[DSL reference → Section arrangement](DSL_REFERENCE.md#section-arrangement-play).

## Step 3 — defining basic grooves

A groove is a named, reusable pattern. Define it once at the top of the
file and reference it from any section.

```groovescript
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8
```

- The groove body sits directly indented under the `groove "…":` line.
  Each line is either `INSTRUMENT: beats` (what this example shows) or
  `beat: instruments` (the other notation style, also legal and
  mixable).
- `*8` means "a hit on every 8th note". The general form is `*N` (or
  `*Nt` for triplets), where N is one of `2`, `4`, `8`, `16`. So `*16`
  would be sixteenths and `*8t` eighth-note triplets.
- GrooveScript infers the bar's grid from what you wrote — here the `*8`
  and the quarter-note beats `1, 2, 3, 4` both fit on an 8th-note grid,
  so the bar is notated in 8ths.

Instruments can be written as canonical abbreviations (`BD`, `SN`, `HH`),
lowercase (`bd`, `sn`, `hh`), or verbose names (`kick`, `snare`, `hat`) —
they all normalize to the same output. Full list in
[DSL reference → Instruments](DSL_REFERENCE.md#instruments).

GrooveScript also ships with a **library of common grooves** (`rock`,
`disco`, `funk`, `bossa-nova`, etc.) that you can reference by name
without defining them. See
[DSL reference → Library of grooves](DSL_REFERENCE.md#library-of-grooves).

## Step 4 — placeholder fills

When you're transcribing a song it's useful to mark "something happens
here" without yet committing to the exact notes. `fill placeholder` draws
a boxed label above a bar while leaving the groove underneath unchanged:

```groovescript
section "verse":
  bars: 8
  groove: "money beat"
  fill placeholder at bar 4
  fill placeholder "build" at bar 8
```

The label defaults to "fill" but can be any string. You can later swap
any placeholder for a real fill (step 6) without touching the surrounding
section.

## Step 5 — variations

A variation modifies a single bar of the section's groove without defining
a whole new groove. The name is optional:

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

Supported actions are `add`, `remove`, `replace`, and `substitute`
(wipes the bar and replaces it with a count+notes body). Each action
can target a single instrument or a space-separated list. Supported
modifiers are `ghost`, `accent`, `flam`, `drag`, and `double` (32nd-note
double stroke).

See [DSL reference → Variation actions](DSL_REFERENCE.md#variation-actions)
for the full grammar.

## Step 6 — defining real fills

When a placeholder becomes a real fill, you have two syntaxes to choose
from. Both reach the same IR, so pick whichever reads most naturally for
the phrase.

**Count-block syntax** — explicit beat labels on each line:

```groovescript
fill "bar 4 fill":
  count "3 e & a 4":
    3:  SN
    3e: SN
    3&: SN
    3a: SN
    4:  BD, CR
```

**Count+notes syntax** — positional 1-to-1 alignment between count tokens
and hit tokens:

```groovescript
fill "bar 4 fill":
  count: "3 e & a 4"
  notes: "snare, snare, snare, snare, (bass, crash)"
```

Use either form at the top level, then attach it to a section with
`fill "bar 4 fill" at bar 4`. A fill attached with `at bar N beat X`
runs from beat X to the end of the bar.

If a fill only appears once, you can skip the top-level definition and
write it inline:

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

See [DSL reference → Fill](DSL_REFERENCE.md#fill) for the full fill
grammar including simultaneous hits, trailing modifiers, and triplet
subdivisions.

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

section "chorus":
  bars: 8
  groove: "money beat"
  variation "chorus lift" at bar 8:
    replace HH with CR at 1
    add SN ghost at 2&
    replace SN with SN accent at 4
```

Save it as `charts/tutorial.gs` (use `./scaffold-chart tutorial` if you
haven't already) and build:

```bash
./build-pdf tutorial
```

`./build-pdf` compiles `charts/tutorial.gs` to LilyPond and then renders
the PDF alongside it — `charts/tutorial.pdf`.

From here, browse [`DSL_REFERENCE.md`](DSL_REFERENCE.md) for anything this
tutorial skipped: time-signature changes per section, multi-bar grooves,
triplet subdivisions, inline unnamed grooves, the `play:` arrangement form,
vocal cues, per-section tempo, and more.
