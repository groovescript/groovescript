# GrooveScript DSL reference

Comprehensive reference for every GrooveScript feature. If you're new to
the language, start with [`GETTING_STARTED.md`](GETTING_STARTED.md) or
[`TUTORIAL.md`](TUTORIAL.md) first.

## Contents

- [Metadata](#metadata)
  - [`title`, `tempo`, `time_signature`, `dsl_version`, `default_groove`, `default_bars`](#metadata)
- [Instruments](#instruments)
  - [Canonical / lowercase / verbose aliases](#instruments)
- [Beat labels](#beat-labels)
  - [16th-note suffixes `e`, `&` / `and`, `a`](#beat-labels)
  - [Triplet suffixes `trip` / `let` (`t` / `l`)](#beat-labels)
  - [`*N` / `*Nt` — hit on every Nth note (straight or triplet)](#beat-labels)
  - [`*N except` — star exclusion](#star-exclusion-n-except)
  - [Double-digit beat numbers for compound meter](#beat-labels)
  - [Bare suffix resolution](#beat-labels)
- [Optional commas in list contexts](#optional-commas)
- [Groove](#groove)
  - [Instrument→positions and position→instruments styles](#groove)
  - [Multi-bar grooves (`bar N:` blocks)](#groove)
  - [Bar-level inheritance (`like: bar N`)](#bar-level-inheritance-like-bar-n)
  - [Groove extension (`extend:`)](#groove-extension-extend)
  - [Count+notes groove bodies](#countnotes-groove-bodies)
  - [Inline unnamed grooves inside a section](#inline-unnamed-grooves-inside-a-section)
  - [Optional quotes around `count:` / `notes:` values](#optional-quotes-around-count--notes-values)
- [Library of grooves](#library-of-grooves)
- [Placeholder grooves](#placeholder-grooves)
- [Fill](#fill)
  - [Count-block syntax](#fill)
  - [Count+notes syntax](#fill)
  - [Multi-bar fills](#multi-bar-fills)
  - [Simultaneous hits and trailing modifiers](#fill)
  - [Inline one-off fills inside a section](#section)
  - [Fill placeholders](#fill-placeholders)
  - [Fill extension (`extend:`)](#fill-extension-extend)
- [Library of fills](#library-of-fills)
- [Section](#section)
  - [Classic form (`bars:` / `groove:`)](#classic-form--single-groove)
  - [`like` inheritance](#classic-form--single-groove)
  - [Per-section tempo (`tempo:`)](#classic-form--single-groove)
  - [Per-section time signature (`time_signature:`)](#mixed--changing-meter)
  - [`crash in` — start a section on a crash](#crash-in)
  - [Section arrangement (`play:`)](#section-arrangement-play)
  - [Vocal cues and text annotations](#vocal-cues-and-text-annotations)
  - [Crescendos and decrescendos](#crescendos-and-decrescendos)
- [Variation actions](#variation-actions)
  - [`add`, `remove`, `replace`, `substitute`](#variation-actions)
  - [Multi-instrument actions](#variation-actions)
- [Modifiers](#modifiers)
  - [`ghost`, `accent`, `flam`, `drag`](#modifiers)
  - [`double` / `32nd` (double strokes)](#modifiers)
  - [`buzz` / `buzz:N` (buzz rolls)](#buzz-rolls)
- [Hi-hat foot chick (`HF`)](#hi-hat-foot-chick)

---

## Metadata

```groovescript
title: "Song Name"
tempo: 120
time_signature: 4/4
dsl_version: 1            # optional — the GrooveScript DSL version this
                          # file targets. Omit to accept the current version.
```

Per-bar subdivision is inferred automatically from the content of each
bar — the beat labels you write (`1`, `2&`, `3e`, `4trip`, …) and any
`*N` / `*Nt` star hits together determine the grid GrooveScript uses
when emitting LilyPond. There is no `subdivision:` keyword and no
`default_subdivision` metadata field — just write the rhythm you want
and the compiler picks the right grid.

Mixed subdivisions — straight 16ths (or 8ths) combined with triplets in
the same bar — are supported. The compiler uses the least common
multiple of the two grids to accommodate both. For example, a bar with
both 8th-note content and triplets uses 6 slots per beat; a bar mixing
16ths and triplets uses 12 slots per beat:

```groovescript
groove "mixed":
    BD: 1, 3
    SN: 2, 4
    HH: 1, 1&, 2, 2&, 3trip, 3let, 4trip, 4let
```

### Default groove and default bars

The metadata block can declare defaults that apply to any section that
omits `groove:` or `bars:`:

```groovescript
title: "Example"
tempo: 120
default_groove: "rock"
default_bars: 8
```

With these defaults, a section can be as short as:

```groovescript
section "verse":
```

which is equivalent to `bars: 8` + `groove: "rock"`. A section that sets
its own `bars:` or `groove:` overrides the default.

### Placeholder groove (minimal sections)

A section that declares `bars:` without a `groove:` — and has no
`default_groove` either — renders as a **placeholder groove**: each bar
is an empty measure (no notes, no rests) with a boxed "Section groove"
label above the first bar.

```groovescript
section "intro":
  bars: 4

section "verse":
  bars: 8
  fill at bar 8                 // placeholders compose — "Fill" label on bar 8
```

This is the iteration-1 form of a chart: print the form, pencil in the
grooves by hand, or fill in `groove:` lines later. `bars:` is still
required; only `groove:` is optional.

The implicit form above is shorthand. Three equivalent explicit forms
let you label individual placeholders or sit them alongside transcribed
grooves inside a `play:` block — see [Placeholder
grooves](#placeholder-grooves).

`dsl_version` is a forward-compatibility marker. When a file declares
`dsl_version: N` with N different from the current DSL version, parsing
fails with a clear error. Files that omit the line are accepted at the
current version with no warning. New charts scaffolded from the
templates in `templates/` include the line automatically.

Time signatures 4/4, 3/4, 6/8, 12/8, and generally any `N/M` with a
numerator from 1–99 are supported.

## Instruments

Every instrument can be written as its canonical abbreviation, a lowercase
abbreviation, or a verbose name — all normalize to the same canonical form in
the output.

| Canonical | Lowercase | Verbose aliases          | Drum              |
|-----------|-----------|--------------------------|-------------------|
| `BD`      | `bd`      | `kick`, `bass`               | bass drum         |
| `SN`      | `sn`      | `snare`                      | snare             |
| `SCS`     | `scs`     | `click`, `cross-stick`       | snare cross stick |
| `HH`      | `hh`      | `hat`, `hihat`, `hi-hat`     | closed hi-hat     |
| `OH`      | `oh`      | `open`, `openhat`            | open hi-hat       |
| `HF`      | `hf`      | `hihatfoot`, `footchick`     | hi-hat foot chick |
| `RD`      | `rd`      | `ride`                       | ride              |
| `CR`      | `cr`      | `crash`                      | crash             |
| `FT`      | `ft`      | `floortom`, `lowtom`         | floor tom         |
| `HT`      | `ht`      | `hightom`, `hitom`           | high tom          |
| `MT`      | `mt`      | `midtom`                     | mid tom           |

## Beat labels

Beats are counted `1 2 3 4` with 16th-note subdivisions written as `1e 1& 1a`,
`2e 2& 2a`, etc. 8th-note triplets are written as `1trip 1let` (or `1t 1l`).

The star syntax `*N` means "a hit on every Nth note", where N is one of
`2`, `4`, `8`, or `16`. Append `t` for triplet versions: `*8t` fills the
bar with eighth-note triplets, `*4t` with quarter-note triplets, and so
on. The star's hit count in a bar is `beats_per_bar * N / beat_unit` for
the straight form (and three-halves of that for the triplet form), so
`HH: *8` in 4/4 produces 8 hits, `HH: *16` produces 16, `HH: *8t`
produces 12. A star that does not divide the time signature evenly (for
example `*4t` in 3/4 would yield 4.5 hits) is rejected at parse time.

### Star exclusion (`*N except`)

Add `except <beat_list>` after a star to fill every Nth note **except**
the listed beats. This is useful for patterns like 16th-note hats with
intentional gaps where an open hat or other instrument plays instead:

```groovescript
groove "open hat 16ths":
    BD: 1, 3
    SN: 2, 4
    HH: *16 except 2a, 4a   // every 16th except the "a" of 2 and 4
    OH: 2a, 4a               // open hats fill the gaps
```

Commas in the except list are optional — `*16 except 2a 4a` works too.
Bare suffix resolution applies in the except list, so `*8 except 1 and`
expands to `*8 except 1, 1&`.

Beat numbers go up to 99, so compound meters like 12/8 can address every
eighth note directly — `BD: 1, 7`, `SN: 4, 10`, `HH: 1, 2, …, 12`. Any
suffix that applies to single-digit beats also works on double-digit ones
(`12&`, `12trip`, `10e`, etc.).

The token `and` is a long-form alias for `&` anywhere a beat suffix is
accepted — `1and` parses identically to `1&`, both in pattern lines and in
fill `count:` strings (`"1 and 2 and 3 and 4 and"`).

### Bare suffix resolution

Inside a beat list on a single line, a bare suffix token (`and`, `&`, `e`,
`a`, `trip`, `let`) attaches itself to the **most recently seen beat
number**, exactly like in fill `count:` strings. So all of these lines
describe the same pattern — HH on every eighth note of a 4/4 bar:

```groovescript
HH: 1, 1&, 2, 2&, 3, 3&, 4, 4&
HH: 1 1and 2 2and 3 3and 4 4and   # positional "and"
HH: 1 and 2 and 3 and 4 and       # bare "and"
HH: 1 & 2 & 3 & 4 &               # bare "&"
```

And for 16th-note or triplet grids:

```groovescript
HH: 1 e and a 2 e and a 3 e and a 4 e and a   # all 16 sixteenths
HH: 1 trip let 2 trip let 3 trip let 4 trip let  # triplet eighths
```

Bare suffix resolution applies to beat lists in pattern lines and in
variation action beat lists (`add SN ghost at 2 and`). It does **not**
apply to position→instrument lines (`1: BD HH`), where the right-hand
side is a list of instruments, not beats.

## Optional commas

Commas between items in a list are **optional** — wherever a list of beats
or instruments appears on a single line you can separate the items with a
space instead of a comma. This is handy when typing on mobile, where commas
are a shift-key away:

```groovescript
groove "money beat":
    BD: 1 3              # same as  BD: 1, 3
    SN: 2 4              # same as  SN: 2, 4
    HH: 1 1& 2 2& 3 3& 4 4&
    1: BD HH             # position → instruments, also comma-free

section "chorus":
  bars: 4
  groove: "money beat"
  variation at bar 4:
    add SN ghost at 1 3  # same as  add SN ghost at 1, 3
    replace HH with CR at 1 3
```

Modifiers (`ghost`, `accent`, `flam`, `drag`, `double` / `32nd`) still
attach to the primary they follow, so `BD: 1 flam 3 accent` means "BD on 1
with a flam and BD on 3 with an accent". You may mix comma-free and
comma-ful forms on the same line. The comma-delimited form inside fill
`notes:` strings still requires commas (see below) because the string is a
single opaque token to the parser.

## Groove

Both notation styles work interchangeably and may be mixed in the same block:

```groovescript
groove "name":
    BD: 1, 3              # instrument→positions style
    SN: 2, 4
    HH: *8                # a hit on every eighth note

groove "pos style":
    1: BD, HH             # position→instruments style
    2: SN, HH
    3: BD, HH
    4: SN, HH
```

The bar's subdivision is inferred from the labels and stars you wrote —
in the `money beat` example above, the `*8` on HH (and beats addressed
at `1`, `2`, `3`, `4` on the others) both fit cleanly on an eighth-note
grid, so the bar is notated in eighths.

Multi-bar grooves are written as a sequence of `bar N:` blocks directly
under the groove's colon; each bar can use either style and each bar's
grid is inferred independently:

```groovescript
groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 2&, 4
      SN: 2, 4
      HH: *16              # this bar is notated on a 16th-note grid
```

#### Bar-level inheritance (`like: bar N`)

Inside a multi-bar groove, a `bar N:` block can start with `like: bar M`
to copy all pattern lines from bar M as a starting point, then layer
additions/overrides on top. This avoids duplicating nearly-identical bars:

```groovescript
groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      like: bar 1              # start with bar 1's pattern
      BD: 1, 2&, 4             # override kick only; SN and HH inherited
```

Same-instrument lines in the current bar override the inherited lines;
new instruments are added. `like: bar N` must reference a bar that
exists in the same groove.

### Groove extension (`extend:`)

A groove can inherit from another groove and layer changes on top using
`extend:`:

```groovescript
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "rock with crash":
  extend: "rock"
  CR: 1                        # adds crash on beat 1; BD, SN, HH inherited
```

Merge rules: same instrument in the extending groove's body overrides
the base groove's line for that instrument; new instruments are added.
The base groove is not modified.

When the base groove is multi-bar and the extending groove has a single-bar
body, the overrides are broadcast to every bar of the base. When the
override body is omitted entirely, the result is an exact copy of the base
groove:

```groovescript
groove "rock copy":
  extend: "rock"               # identical to "rock"
```

Chains work: `C` can extend `B`, which extends `A`. The base groove can
also be a built-in library groove (e.g. `extend: "rock"`).

**Applying variation actions in `extend:`** — in addition to (or instead of)
pattern-line overrides, the extend body accepts the same action syntax used
by section variations (`add`, `remove`, `replace`, `substitute`, `modify add`,
`modify remove`). This lets a derived groove be used everywhere a named
groove is accepted, without re-stating the base groove plus a matching
variation at every call site.

```groovescript
groove "rock on ride":
  extend: "rock"
  replace HH with RD at *      # every HH hit becomes an RD hit
```

Bare actions apply to every bar of the base. To scope actions to specific
bars, wrap them in a `variation at bar N:` (or `variation at bars N, M:`)
block. Bare bundles and scoped bundles can be mixed freely:

```groovescript
groove "two-bar rock":
  bar 1:
    HH: *8 / BD: 1, 3 / SN: 2, 4
  bar 2:
    HH: *8 / BD: 1, 3 / SN: 2, 4

groove "two-bar with lift":
  extend: "two-bar rock"
  variation at bar 1:
    replace HH with RD at *    # bar 1 only
  variation at bar 2:
    add CR at 1                # bar 2 only
```

When both pattern-line overrides and variation actions are given in the
same `extend:` body, the pattern-line merge runs first, then the actions
apply to the resulting events. `replace`, `add`, `remove`, and the
`modify` family all behave the same as they do in a section variation —
including the rule that any modifiers on the original events are *not*
carried over to events produced by `replace` (the new hits start fresh).

Scoping to a bar number that doesn't exist in the merged groove is an
error, caught at compile time.

A bare `text: "…"` line at the top of an `extend:` body annotates bar 1
of the resolved groove — the same effect as nesting `text:` inside
`bar 1:` of a multi-bar pattern, but available to single-bar derived
grooves that have no `bar 1:` block to put it in:

```groovescript
groove "main groove":
  extend: "rock"
  add BD at 3&
  text: "Quarter note pulse"
```

### Count+notes groove bodies

A groove can also use the positional `count:` / `notes:` form — the same
one used by fills. The bar's grid is inferred from the count string (e.g.
`1 and 2 and …` → 8ths, `1 e and a …` → 16ths, `1 trip let …` →
8th-note triplets), and the count tokens line up 1-to-1 with the notes:

```groovescript
groove "sixteenth run":
  count: 1 e and a 2 e and a 3 e and a 4 e and a
  notes: BD, HH, SN, HH, BD, HH, SN, HH, BD, HH, SN, HH, BD, HH, SN, HH
```

Parenthesised groups express simultaneous hits, and trailing modifiers
attach to the hit (or group) they follow:

```groovescript
groove "shot":
  count: 1 and 2 and 3 and 4 and
  notes: (BD, CR) accent, HH, SN ghost, HH, BD, HH, SN, HH
```

The count+notes form produces a single-bar groove. Quotes around the
`count:` / `notes:` values are optional (see below).

### Inline unnamed grooves inside a section

Sections can define a one-off groove inline, without first declaring a
named top-level groove. Any groove body (classic instrument/bar lines
or count+notes) is accepted:

```groovescript
section "chorus":
  bars: 4
  groove:
      BD: 1, 3
      SN: 2, 4
      crash: 1
      HH: 2, 3, 4
```

The unnamed groove is scoped to its section and does not pollute the
top-level groove namespace.

### Optional quotes around `count:` / `notes:` values

Wherever a line looks like `count: <value>` or `notes: <value>` the
surrounding double quotes are optional. These three snippets all parse
identically:

```groovescript
fill "roll":
  count: "1 e and a"
  notes: "SN, SN, SN, SN"

fill "roll":
  count: 1 e and a
  notes: SN, SN, SN, SN

fill "roll":
  count: 1 e and a     # trailing comments are fine too
  notes: SN, SN, SN, SN
```

The block form `count "label": …` (with a quoted label) is unchanged —
the rewrite only applies to the standalone `count:` / `notes:` shape.

## Library of grooves

GrooveScript includes a built-in library of common drum patterns that you
can reference by name in your sections without defining them.

Each built-in is a single bar of 4/4 and can be referenced from any
section without a `groove "…":` block in your file. The **Notation**
column shows the exact pattern lines, so you can see at a glance where
the kick, snare, hats, and other voices land.

| Name                 | Grid  | Description                                         | Notation                                                              |
|----------------------|-------|-----------------------------------------------------|-----------------------------------------------------------------------|
| `rock`               | 8ths  | Basic 8th-note rock groove                          | `HH: *8` / `BD: 1, 3` / `SN: 2, 4`                                    |
| `rock-2`             | 8ths  | Rock with an extra kick on the `&` of 2             | `HH: *8` / `BD: 1, 2&, 3` / `SN: 2, 4`                                |
| `rock-3`             | 8ths  | Rock with a pushed kick on the `&` of 3             | `HH: *8` / `BD: 1, 3, 3&` / `SN: 2, 4`                                |
| `16th-rock`          | 16ths | 16th-note hi-hat driving a rock backbeat            | `HH: *16` / `BD: 1, 3` / `SN: 2, 4`                                   |
| `four-on-the-floor`  | 8ths  | Kick on every beat, snare on 2 and 4                | `HH: *8` / `BD: 1, 2, 3, 4` / `SN: 2, 4`                              |
| `disco`              | 16ths | Alternating closed/open hats on 8ths and 16ths      | `HH: 1, 1&, 2, 2&, 3, 3&, 4, 4&` / `OH: 1e, 1a, 2e, 2a, 3e, 3a, 4e, 4a` / `BD: 1, 2, 3, 4` / `SN: 2, 4` |
| `funk`               | 16ths | Syncopated kick-and-snare funk with 16th hats       | `HH: *16` / `BD: 1, 2&, 3e` / `SN: 2, 4, 2a, 4a`                      |
| `shuffle`            | trip  | 8th-note triplet shuffle on the hats                | `HH: 1, 1let, 2, 2let, 3, 3let, 4, 4let` / `BD: 1, 3` / `SN: 2, 4`    |
| `jazz-ride`          | trip  | Classic jazz ride on the cymbal, backbeat on 2 & 4  | `RD: 1, 2, 2let, 3, 4, 4let` / `BD: 1, 3` / `SN: 2, 4`                |
| `bossa-nova`         | 16ths | Bossa-style cross-stick pattern over 16th hats      | `HH: *16` / `BD: 1, 1a, 2&, 3, 3a, 4&` / `SCS: 1, 2&, 3&, 4`          |

Example:

```groovescript
section "verse":
  bars: 8
  groove: "rock"  # uses the built-in rock groove
```

If you define a groove with the same name in your file, it **overrides**
the library groove for the rest of that file. `extend:` (see
[Groove extension](#groove-extension-extend)) also accepts library
grooves as a base, so you can layer changes on top of any built-in
without redefining it:

```groovescript
groove "rock + crash on 1":
  extend: "rock"
  CR: 1
```

The canonical source for every built-in is `src/groovescript/groove_library.gs`
in the repository — the table above mirrors it, so any new or updated
grooves added there should also be reflected here.

## Placeholder grooves

A **placeholder groove** is a TBD slot — empty bars with a boxed
rehearsal label — that lets you sketch a chart's form before every
groove has been transcribed. The shorthand version is the [minimal
section](#placeholder-groove-minimal-sections) (a section with `bars:`
but no `groove:`); the explicit forms below let you label individual
placeholders or place them alongside transcribed grooves inside a
`play:` block.

Three syntactic surfaces, all parallel to fill placeholders:

```groovescript
// 1. Top-level declaration. Reference it from any section by name.
groove placeholder "verse-A"

// 2. Section's sole groove. Nameless or named.
section "intro":
  bars: 4
  groove: placeholder

section "pre-chorus":
  bars: 4
  groove: placeholder "hookline tease"

section "verse":
  bars: 8
  groove: "verse-A"                  // resolves to the top-level placeholder

// 3. Inside a play: block, alongside transcribed grooves.
section "chorus":
  play:
    groove placeholder x4            // explicit nameless, 4 bars
    groove placeholder "build" x2    // explicit named, 2 bars
    groove "outro idea" x4           // undefined name → auto-promotes to a
                                     //   named placeholder with that label
    groove "money beat" x4           // a real, transcribed groove
```

Inside a `play:` list, an undefined groove name **auto-promotes** to a
named placeholder whose label is the reference name itself. This makes
the common case — listing the section's grooves by name before
transcribing them — a one-liner. Defined names continue to resolve
normally; only unknown ones get promoted.

Outside a `play:` list, `groove: "name"` referencing an undefined name
remains an error so typos are still caught — use `groove: placeholder
"name"` if you want the section's sole groove to be a TBD slot.

Labels:

- A **named** placeholder uses its given label verbatim: `"verse-A"`,
  `"hookline tease"`, `"build"`, etc.
- A **nameless** placeholder uses `"<Section> groove"` (capitalised
  section name + the literal word `groove`). When a single section has
  more than one nameless placeholder span, they're suffixed
  `1`, `2`, … so they can be told apart on the page.
- Top-level `groove placeholder "X"` declarations and section sole
  grooves with the same name are duplicate-name errors, the same as
  declaring two real grooves of the same name.

Compatibility with other features:

- **Fill placeholders** and **cues** overlay placeholder bars normally,
  so a placeholder section can still show `fill at bar 4` and `cue
  "vocals in" at bar 1`.
- **Variations** that target a placeholder bar are an error — there
  are no notes to vary. Transcribe the groove first.
- **`extend:`** cannot reference a placeholder groove (the placeholder
  has no pattern to inherit from).
- **MIDI** and **MusicXML** export emit silent measures for the
  duration of each placeholder span, so playback length still matches
  the printed chart.

## Fill

Two fill syntaxes are supported and may be used in different bars of the
same fill.

**Count-block syntax** — explicit beat labels, both notation styles work and may be mixed:

```groovescript
fill "name":
  count "3 e & a 4":
    SN: 3, 3e, 3&, 3a    # instrument→positions style
    4:  BD, CR            # position→instruments style (comma = simultaneous hits)
```

The `count "…":` header is **optional** when every line already pins each
hit to a specific beat — i.e. pure instrument→positions or
position→instruments notation. The header then serves only as
documentation, so it can be dropped:

```groovescript
fill "crash landing":
    BD: 1, 3
    SN: 2, 4
    CR: 1
```

This bare form implies a single bar. For multi-bar fills without count
labels, separate the bars with `bar N:` (mirroring the groove syntax):

```groovescript
fill "two bar buildup":
  bar 1:
    SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a
  bar 2:
    1: BD, CR
    BD: 2, 3, 4
```

The `bar N:` numbers are visual markers — file order determines the
playback order, same as with `count "…":` blocks.

**Count+notes syntax** — positional 1-1 alignment between count tokens and notes:

```groovescript
fill "name":
  count: "3 e & a 4"
  notes: "snare, snare, snare, snare, (bass, crash)"
```

Each top-level token in `notes` maps to the corresponding token in `count`.
`notes:` strings are **comma-delimited**, so each hit can carry its own
trailing modifiers (`snare accent`, `snare ghost`, `(bass, crash) accent`).
Parenthesised groups (`(bass, crash)`) express simultaneous hits on that
count position; a trailing modifier after the group applies to every note
in the group.

The legacy **space-delimited** form (`"snare snare snare snare (bass,
crash)"`) is still accepted when the `notes:` string contains no top-level
commas — useful for the simplest case where every hit is a bare instrument.

Omit the `notes:` line entirely to default every count slot to a single
snare hit — convenient for the common snare-roll case:

```groovescript
fill "snare roll":
  count: "3 e & a 4 e & a"
```

is equivalent to:

```groovescript
fill "snare roll":
  count: "3 e & a 4 e & a"
  notes: "SN, SN, SN, SN, SN, SN, SN, SN"
```

Instrument names in `notes` follow the same alias rules as everywhere else
(see the Instruments table above). In addition, `hi-hat` (with a hyphen) is
accepted here.

Count tokens: digits `1`–`9` for beat numbers; `e`, `&`, `a` for 16th-note
subdivisions; `and` as a long-form alias for `&`; `trip` / `let` (and
positional forms like `1trip`, `1let`, `1and`) for triplet subdivisions and
long-form `&`.

### Multi-bar fills

A fill can span multiple bars by including multiple `count` blocks. Each
block becomes one bar; the bars play in sequence when the fill is placed.

**Count-block syntax** — multiple `count "…":` blocks in a single fill:

```groovescript
fill "two bar buildup":
  count "3 e & a 4 e & a":
    SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a
  count "1 e & a 2 e & a 3 e & a 4":
    SN: 1, 1e, 1&, 1a, 2, 2e, 2&, 2a, 3, 3e, 3&, 3a
    4: BD, CR
```

**Count+notes syntax** — multiple `count:` / `notes:` pairs:

```groovescript
fill "two bar fill":
  count: "3 e & a 4 e & a"
  notes: "SN, SN, SN, SN, SN, SN, SN, SN"
  count: "1 e & a 2 e & a 3 e & a 4"
  notes: "SN, SN, SN, SN, SN, SN, SN, SN, SN, SN, SN, SN, (BD CR)"
```

Each `count:` / `notes:` pair defines one bar. The first pair is bar 1
of the fill, the second is bar 2, and so on.

When placing a multi-bar fill, the fill replaces bars starting from
the placement position. For example, if a two-bar fill is placed at
bar 3, it replaces bars 3 and 4:

```groovescript
section "chorus":
  bars: 8
  groove: "rock"
  fill "two bar fill" at bar 7    # replaces bars 7 and 8
```

Each bar of the fill has its own independently-inferred subdivision,
so you can mix grids across bars (e.g., 16ths in bar 1, triplets in
bar 2).

### Fill placeholders

```groovescript
fill at bar 4                       # implicit: boxed "Fill" label above bar 4
fill at bar 4, 8                    # implicit: placeholder on multiple bars
fill at bar 4 beat 3                # implicit: starting at a specific beat
fill placeholder "build" at bar 4   # explicit form with a custom label
fill placeholder at bar 4 beat 3    # explicit form starting at a specific beat
```

A placeholder draws a boxed annotation above the staff without altering
groove events. Swap for a real fill later without touching the surrounding
section.

`fill at bar N` (no body, no reference) is the shorthand form — no need
to write the `placeholder` keyword. Use the longer `fill placeholder
"label" at bar N` form when you want a custom label.

### Fill extension (`extend:`)

A fill can inherit from another named fill (user-defined or from the
built-in [fill library](#library-of-fills)) and layer extra events on
top. Extension is **purely additive** — the base fill's events are
preserved and the extension body's events are appended.

```groovescript
// Layer a driving kick pulse onto a library snare roll. The bare form
// (no count "…": wrapper) works for single-bar extensions.
fill "snare-roll+kick":
  extend: "snare-roll"
  BD: *4

// Equivalent with an explicit count block — also valid, and required
// when the extension needs to target a specific bar of a multi-bar base.
fill "snare-roll+kick v2":
  extend: "snare-roll"
  count "1 2 3 4":
    BD: *4

// Pure alias — no body, just a rename.
fill "big hit":
  extend: "crash"
```

**Preferred layering style** is `instrument: positions`
(`BD: 1, 3`) rather than `position: instruments` (`1: BD` +
`3: BD`). Both parse identically, but the `instrument: positions`
form reads more naturally when you're adding an independent voice on
top of a base pattern.

**Bar alignment** (for multi-bar base fills):

- A 1-bar extension applied to an N-bar base is **broadcast** to every
  base bar — handy for adding the same voice across a whole multi-bar fill.
- An N-bar extension targets base bars 1..N in order; later base bars
  are inherited unchanged.
- An extension with more bars than the base is an error — extension is
  for layering, not lengthening.

**No override semantics**: if the extension adds an event at the same
(instrument, position) as a base event, both fire (purely additive). If
that is not what you want, either omit the colliding voice from the
extension or replace the base entirely by defining a new fill from
scratch.

**Chaining is supported**: `C extend: "B"` where `B extend: "A"` is
fine; cycles are rejected. Extending a fill does **not** mutate the
base — the base still compiles to its original events elsewhere.

## Library of fills

GrooveScript ships with a library of stock drum fills you can drop into
any section without defining them in your file. Each entry is one bar
of 4/4 and is referenced exactly like a user-defined fill:

```groovescript
section "verse":
  bars: 8
  groove: "rock"
  fill "snare-roll-half" at bar 8 beat 3
```

**Naming convention**: base name = whole bar; `-half` = beats 3-4
(place with `at bar N beat 3`); `-beat` = beat 4 only (place with
`at bar N beat 4`); `-trip` = 8th-note triplet grid; `-up` = ascending
pitch variant (tom rolls only). Default grid is 16ths.

### Accents

| Name      | Description                                                  |
|-----------|--------------------------------------------------------------|
| `crash`   | Bass drum + crash on beat 1 — section opener / big accent    |
| `crash-4` | Bass drum + crash on beat 4 — anticipation into next section |

### Snare rolls (straight)

| Name                | Grid  | Description                                  |
|---------------------|-------|----------------------------------------------|
| `snare-roll`        | 16ths | Full bar of 16th-note snares                 |
| `snare-roll-half`   | 16ths | 16th-note snare roll across beats 3 and 4   |
| `snare-roll-beat`   | 16ths | One-beat 16th-note snare roll on beat 4     |

### Snare rolls (triplets)

| Name                    | Grid  | Description                               |
|-------------------------|-------|-------------------------------------------|
| `snare-roll-trip`       | trip  | Full bar of 8th-note triplet snares      |
| `snare-roll-trip-half`  | trip  | 8th-note triplet snare roll on beats 3-4 |

### Buzz rolls

| Name               | Length                 | Description                                      |
|--------------------|------------------------|--------------------------------------------------|
| `buzz-roll`        | whole note             | Full-bar buzz roll on snare                      |
| `buzz-roll-half`   | half note              | Half-note buzz roll starting on beat 3           |
| `buzz-roll-beat`   | quarter note           | Quarter-note buzz roll on beat 4                 |

### Tom rolls

| Name            | Grid  | Description                                                              |
|-----------------|-------|--------------------------------------------------------------------------|
| `tom-roll`      | 16ths | Descending 16th-note tom roll: HT (beat 1) → MT (beat 2) → FT (beats 3-4) |
| `tom-roll-half` | 16ths | Half-bar descending tom roll on beats 3-4 (MT → FT)                     |
| `tom-roll-up`   | 16ths | Ascending 16th-note tom roll: FT → MT → HT                              |
| `tom-roll-trip` | trip  | Descending 8th-note triplet tom roll: HT → MT → FT                      |

### Snare + tom mixes

| Name                | Grid    | Description                                                 |
|---------------------|---------|-------------------------------------------------------------|
| `snare-tom-half`    | 16ths   | Classic rock fill: 16th snares on beat 3, tom tour on beat 4 |
| `around-kit`        | 1/4s    | Quarter-note tour: SN → HT → MT → FT                         |
| `around-kit-16ths`  | 16ths   | 16th-note tour: four snares, four HT, four MT, four FT      |

### Rudimental

| Name          | Grid  | Description                                                        |
|---------------|-------|--------------------------------------------------------------------|
| `flam-fill`   | 16ths | Half-bar 16th-snare roll with flams on the downbeats of 3 and 4    |
| `linear-half` | 16ths | Gadd-style half-bar linear fill (no two hits at once)               |

Defining a fill with the same name in your file **overrides** the
library fill for the rest of that file. Library fills sit alongside the
built-in [groove library](#library-of-grooves) — both are resolved at
compile time; nothing needs to be imported.

The canonical source for every built-in is `src/groovescript/fill_library.gs`
in the repository — the tables above mirror it, so any new or updated
fills added there should also be reflected here.

## Section

### Classic form — single groove

```groovescript
section "name":
  bars: 8
  groove: "money beat"
  tempo: 140                           # optional BPM override for this section
  time_signature: 7/8                  # optional meter override for this section
  fill "name" at bar 4                # whole-bar fill
  fill "name" at bar 8 beat 3         # runs from 3 to end of bar 8
  fill "name" at bar 4, 8 beat 3      # same fill placed at two bars at once
  fill "name" at bars 4 8 beat 3      #   (comma- or space-separated)
  fill at bar 6 beat 3:               # inline one-off fill (no top-level name needed)
  fill at bar 4, 8 beat 3:            # inline fill placed in multiple bars
    count "3 e & a 4":
      3: SN
      3e: SN
      3&: SN
      3a: SN
      4: BD, CR
  fill at bar 4                       # implicit placeholder: boxed "Fill" label
  fill placeholder "build" at bar 4   # placeholder with a custom label
  fill placeholder at bar 4 beat 3    # placeholder starting at a specific beat
  variation "lift" at bar 8:          # named variation
    replace HH with CR at 1
    add SN ghost at 2&
    replace SN with SN accent at 4
  variation at bar 4:                 # the name is optional
    add CR accent at 1
  variation "crashes" at bars 4, 8:  # same actions on multiple bars
    replace HH with CR at 1
```

Inline fills accept the same `count …:` and `count:`/`notes:` block
forms as top-level `fill` definitions, and — as with top-level fills —
the `count "…"` header is optional whenever the lines pin each hit to a
specific beat:

```groovescript
section "verse":
  bars: 4
  groove: "money beat"
  fill at bar 4:                # bare single-bar inline fill
    BD: 1, 3
    SN: 2, 4
    CR: 1
  fill at bar 4 beat 3:         # bare, starting mid-bar
    SN: 3, 3e, 3a
    4: BD, CR
```

Multi-bar inline fills without a count label use `bar N:` delimiters,
exactly like top-level fills. The fill attaches to its section at the bar
(and optional beat) given on the `fill at bar N …:` line — exactly like a
named `fill "name" at bar N` placement.

Inherit from another section:

```groovescript
section "verse 2":
  like "verse"
```

Bare `like "parent"` inherits only the basic arrangement: `bars`, `groove`,
`repeat`, `tempo`, `time_signature`, `play`, inline grooves,
section-level dynamic spans, and the `crash in` flag. To also inherit
`fills`, `variations`, or `cues`, list the categories after `with`:

```groovescript
section "chorus 2":
  like "chorus" with fills, variations, cues
```

The three categories are order-insensitive and commas between them are
optional (`with fills variations cues` is equivalent). Listing the same
category twice is an error.

Scalar fields on the inheriting section (`bars`, `groove`, `repeat`,
`tempo`, `play`, `time_signature`) override the inherited values when
explicitly set. List fields concatenate — inherited first, then the
inheriting section's additions. If a new entry targets the same bar as
an inherited entry, the new entry wins.

Dynamic spans (`cresc …`, `decresc …`) defined inside a groove or fill
always travel with that groove or fill wherever it's referenced, so a
`like` inheritor that reuses the same groove automatically gets those
inner spans. Spans declared at the section level are inherited only by
bare `like` (they're part of the basic arrangement).

### Mixed / changing meter

Any section may declare its own `time_signature: N/M` to override the
song-level meter for the duration of that section. The staff emits a
`\time` change at the section boundary and every groove referenced by
the section is recompiled against the new beats-per-bar, so beat labels
resolve against the right bar length:

```groovescript
title: "Verse in 4, Bridge in 7"
time_signature: 4/4

groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "seven":
    BD: 1, 3, 5
    SN: 2, 4, 6
    HH: *8               # 7 eighth-note hits in 7/8

section "verse":
  bars: 4
  groove: "rock"

section "bridge":
  bars: 4
  groove: "seven"
  time_signature: 7/8
```

`time_signature` is inherited through `like` just like the other
section-scoped scalars (`bars`, `groove`, `repeat`, `tempo`). A section's
own explicit `time_signature:` always takes precedence over whatever it
inherits.

### Crash in

Add a bare `crash in` line to replace the first riding-instrument hit of
the section's first bar with a crash (plus a kick on the same beat, if
none is already there). This mirrors what drummers do at the top of a
new section — swap the normal cymbal/ride for a crash on the downbeat,
typically struck together with the bass drum:

```groovescript
section "chorus":
  bars: 8
  groove: "money beat"   # HH: *8 ride, BD: 1, 3
  crash in               # -> first HH hit becomes a CR on beat 1
                         #    (BD on 1 already there, so it's left alone)
```

The **riding instrument** is the one with the most hits in bar 1
(typically whatever was declared with `*4`, `*8`, or `*16`). Works for
any ride-like instrument — `HH`, `OH`, `RD`, `CR`, or even a floor-tom
ride (`FT: *8`). Among cymbals tied on hit count, the priority is
`RD > HH > OH > CR > HF`.

Behaviour details:

- If the riding instrument has a hit on beat 1, that hit is replaced by
  a `CR` at the same position. `accent` modifiers carry over; a `ghost`
  modifier is dropped (a ghosted crash is unusual).
- If the rider has no hit on beat 1 (e.g. `HH: *8 except 1`) or no clear
  rider can be identified (all lines explicit, no `*N`), a fresh `CR`
  is simply added on beat 1 — other instruments are untouched.
- If beat 1 already carries a `CR`, the crash step is a no-op.
- A `BD` (kick) is always ensured on beat 1: if none is present, one is
  added; if one is already there, it's left as-is (no duplicate).
- With `play:`, the flag targets the first bar of the first item.
- `crash in` is inherited through `like` alongside the other
  section-scoped fields.

#### Crashing into multiple bars

`crash in` accepts an optional `at` clause to target more than just bar
1 of the section:

- `crash in at <bars>` — comma list of 1-indexed section-bar numbers.
  Commas are optional, same as `variation at bars …` and `fill at bars
  …`. Bars outside the section are silently ignored.
- `crash in at *N` — every Nth bar starting at bar 1. For a 24-bar
  section, `crash in at *8` crashes bars 1, 9, and 17. The `*Nt`
  triplet variant is rejected (it has no meaning for a bar count).

```groovescript
section "verse":
  bars: 8
  groove: "money beat"
  crash in at 1, 5            # crash on bar 1 and bar 5

section "long form":
  bars: 24
  groove: "money beat"
  crash in at *8              # crash on bars 1, 9, 17
```

The same crash-plus-kick algorithm runs at every targeted bar.

#### Top-level `crash in` and the per-section `no crash in` opt-out

Place a bare `crash in` at the top level of the file (outside any
section) to crash into **every section after the first** by default —
the first section is left alone since it doesn't have a previous
section to crash *into*. A section can opt out with `no crash in`, or
override the bars with its own `crash in [at …]`:

```groovescript
crash in

section "intro":
  bars: 2
  groove: "money beat"        # not crashed (first section)

section "verse":
  bars: 4
  groove: "money beat"        # bar 1 crashed by the top-level default

section "bridge":
  bars: 2
  groove: "money beat"
  no crash in                 # opts out of the top-level default

section "chorus":
  bars: 8
  groove: "money beat"
  crash in at 1, 5            # explicit spec wins over the top-level default
```

`no crash in` is inherited through `like` and also cancels any crash-in
inherited from the parent section. Combining `crash in` and `no crash
in` in the same section is rejected. The top-level `crash in` directive
itself is purely additive — nothing else parses or compiles
differently when it's absent.

### Section arrangement (`play:`)

Use `play:` to compose a section from an **ordered sequence** of grooves,
one-off bars, and rests. The section's total bar count is the sum of all
items. `bars:`, `groove:`, and `repeat:` must not appear alongside `play:`.

```groovescript
section "verse":
  tempo: 120
  play:
    groove "money beat" x4       # play a named groove N times (N defaults to 1)
    bar "setup":                 # inline one-off bar definition, played once
      BD: 1, 3
      SN: 4
      CR: 1
    rest x2                      # N bars of silence (N defaults to 1)
    groove "money beat" x4
    bar "setup" x1               # reuse a bar defined earlier in the same play: block
  fill "crash" at bar 1
  variation "push" at bar 8:
    add CR accent at 1
```

Items allowed inside `play:`:

| Item                                       | Meaning                                                                          |
|--------------------------------------------|----------------------------------------------------------------------------------|
| `groove "name" [xN]`                       | Play the named groove N times (default 1). Multi-bar grooves tile all their bars each repeat. If `"name"` isn't defined anywhere, it auto-promotes to a named placeholder — see [Placeholder grooves](#placeholder-grooves). |
| `groove [xN]:` *(with indented body)*      | Inline nameless groove definition played N times (default 1). Body uses the same instrument/bar lines as a named groove. |
| `groove "name" [xN]:` *(with indented body)* | Inline **named** groove definition played N times (default 1). Later `groove "name" [xN]` items in the same section reference this definition. |
| `groove placeholder [xN]`                  | Nameless placeholder span N bars long. Renders as empty bars with a `"<Section> groove"` rehearsal label. |
| `groove placeholder "label" [xN]`          | Named placeholder span N bars long, labelled `"label"`. |
| `bar "name" [xN]:` *(with indented body)*  | Inline definition of a one-off bar, registered under `name` within this section, played N times. |
| `bar "name" [xN]`  *(no body)*             | Reference to a previously-defined bar in this section, played N times. |
| `rest [xN]`                                | N bars of whole-bar silence. Rendered as a full-bar rest (`R1` in 4/4). |

Inline nameless grooves under `play:` are handy for one-off sections
where defining a named `groove "…":` at the top of the file would be
overkill:

```groovescript
section "outro":
  play:
    groove "main" x4
    groove x2:                   # inline nameless groove
      BD: 1, 3
      SN: 2, 4
      HH: *16
    rest
```

To define an inline groove and reuse it later in the same section, give
it a name — the first occurrence defines the body, subsequent occurrences
reference it by name:

```groovescript
section "pre-chorus":
  play:
    groove "ride the tom" x4:    # define + play
      FT: *8
      BD: 1, 3
      SN: 2, 4
    groove "main" x1
    groove "ride the tom" x4     # reuse by name
```

The per-bar grid for each `bar` and `rest` item is inferred just like
any other bar — from the beat labels, `*N` stars, and modifiers used
inside it. Whole-bar rests take the same grid as the surrounding meter.

Fills and variations attach to bars by 1-based position within the
section, exactly as in the classic form. A fill placed over a rest bar
**replaces** the rest entirely.

### Vocal cues and text annotations

- `cue "text" at bar N [beat X]` — places a text annotation above the
  staff at the given bar (and optional beat).
- `text: "…"` inside a groove `bar N:` block — attaches a text annotation
  to that bar of the groove.
- `text: "…"` at the top of a groove `extend:` body — annotates bar 1 of
  the resolved groove. Useful for single-bar derived grooves where there
  is no `bar N:` block to nest the text in.

### Crescendos and decrescendos

Dynamic hairpins are added as section-level lines:

```groovescript
section "verse":
    bars: 8
    groove: "rock"
    cresc from bar 5 to bar 6
    decresc from bar 7 beat 3 to bar 8
```

- `cresc from bar N [beat X] to bar M [beat Y]` — crescendo hairpin (`\<`).
- `decresc from bar N [beat X] to bar M [beat Y]` — decrescendo hairpin (`\>`).

If the starting beat is omitted, the hairpin begins at the start of the bar.
If the ending beat is omitted, it runs to the end of the bar. Both beat
arguments are optional, so all four combinations are valid:

```
cresc from bar 3 to bar 4                     # whole-bar to whole-bar
cresc from bar 3 beat 3 to bar 4              # mid-bar start
cresc from bar 3 to bar 4 beat 1              # specific end beat
cresc from bar 3 beat 3 to bar 4 beat 1       # both specified
```

Dynamic spans layer on top of per-note modifiers (`ghost`, `accent`, etc.).
Dynamic spans may also appear inside a `groove` or `fill` body — in that
case, the spans ride with the groove or fill wherever it's placed, and
are automatically inherited by any section that uses it. Section-level
dynamic spans are inherited by bare `like` along with the other
section-scoped fields.

## Variation actions

A `variation at bar N:` (optionally named: `variation "lift" at bar N:`)
modifies one or more bars of the section's groove. To apply the same
actions to multiple bars, use `bars` with a comma-separated list:

```groovescript
variation "crashes" at bars 4, 8:
  replace HH with CR at 1

variation at bars 2, 4, 6, 8:
  add CR accent at 1
```

Both `bar` (singular) and `bars` keywords work — `bar 4` and `bars 4`
are equivalent for a single bar.

| Action          | Form                                                         |
|-----------------|--------------------------------------------------------------|
| `add`           | `add INSTRUMENT [mods] [INSTRUMENT [mods]]… at <beats>`      |
| `remove`        | `remove INSTRUMENT [INSTRUMENT]… at <beats>`                 |
| `replace`       | `replace INSTRUMENT [INSTRUMENT]… with INSTRUMENT [mods] [INSTRUMENT [mods]]… at <beats>` |
| `modify add`    | `modify add MODIFIER [MODIFIER]… to INSTRUMENT at <beats>` (decorate an existing hit on that instrument) |
| `modify remove` | `modify remove MODIFIER [MODIFIER]… from INSTRUMENT at <beats>` (strip modifiers from an existing hit on that instrument) |
| `substitute`    | `count: <…>` + `notes: <…>` (wipes the bar and replaces it with the count+notes body) |

`add`, `remove`, and `replace` accept multiple instruments in a single
action — trailing modifiers attach to the instrument they follow, and
`replace` pairs sources with targets in order:

```
variation at bar 4:
  remove snare hat at 2            # drop SN and HH on beat 2
  add snare ghost kick accent at 3 # add SN (ghost) and BD (accent) on beat 3
  replace snare hat with ride crash at 4  # SN→RD and HH→CR on beat 4
```

`substitute` replaces every event in the bar with the result of a
`count:` / `notes:` body — the same positional notation used by fills and
count+notes grooves:

```
variation "shot" at bar 8:
  count: 1 and 2 and 3 and 4 and
  notes: bass, hat, snare, hat, bass, hat, snare, (bass crash) accent
```

Simultaneous-hit groups inside `notes:` may use either commas
(`(bass, crash)`) or whitespace (`(bass crash)`) between instruments.

`modify add` / `modify remove` decorate a hit that's already there —
handy when the variation is "play the same pattern but flam the snare on
beat 2" and you don't want to re-state the beat positions:

```
variation at bar 4:
  modify add flam to snare at 2        # flam the snare on beat 2
  modify remove accent from bass at 1  # strip the accent from the bass on beat 1
```

Both forms accept multiple modifiers (`modify add flam accent to snare at
2`) and either a comma-separated beat list, `*` for every beat in the bar,
or a bare `at *`. `modify remove` silently ignores modifiers that aren't
on the named instrument's event, so sweeping removals are safe.

Bar lists in `variation at bars …:` may be comma- or space-separated —
`variation at bars 1 5:` parses the same as `variation at bars 1, 5:`.

### Reusable named variations

Define a variation once at the top level and reference it from any
section — the same pattern as grooves and fills:

```groovescript
variation "crash-on-one":
  add CR at 1

section "chorus":
  bars: 8
  groove: "rock"
  variation "crash-on-one" at bars 1, 5   # reference, no body

section "outro":
  bars: 4
  groove: "rock"
  variation "crash-on-one" at bar 1       # reused in another section
```

A top-level `variation "name":` captures a bundle of actions without
binding them to specific bars. A section then points bars at that
bundle with the no-body form `variation "name" at bar N` (or
`at bars N, M`). Multiple references to the same name are independent —
the actions are re-applied on each referenced bar.

Inline variations (`variation ... at bar N:` with a trailing body) still
work the same way as before, and may coexist with named-reference
variations in the same section.

### Library of variations

GrooveScript ships a built-in library of reusable variations that any
section can reference without defining them locally:

| Name             | Actions                                          |
|------------------|--------------------------------------------------|
| `open-hat-4`     | `replace HH with OH at 4`                        |
| `open-hat-4&`    | `replace HH with OH at 4&`                       |
| `crash-1`        | `add CR at 1`                                    |
| `drop-kick`      | `remove BD at *`                                 |
| `accent-2-4`     | `modify add accent to SN at 2, 4`                |
| `flam-backbeat`  | `modify add flam to SN at 2, 4`                  |

If you define a top-level `variation "name":` with the same name as a
library entry, your definition takes precedence. The canonical source
for every built-in is `src/groovescript/variation_library.gs`.

## Modifiers

Supported modifiers: `ghost`, `accent`, `flam`, `drag`, `double`
(alias: `32nd`), `buzz`.

- **`ghost`** — parenthesised notehead. Softer / unaccented hit.
- **`accent`** — `>` above the note.
- **`flam`** — rendered as a `\slashedGrace` grace note. Only supported on
  snare (`SN`) and toms (`FT`, `HT`, `MT`); using it on any other
  instrument is a compile error.
- **`drag`** — rendered as a two-note grace cluster.
- **`double`** (or **`32nd`**) — on a 16th-note hit, plays the slot as two
  equal 32nd notes (a double stroke). Only valid in bars whose inferred
  grid is 16ths (4 slots/beat) and **incompatible with `flam` and
  `drag`**.
- **`buzz`** (or **`buzz:N`**, **`buzz:Nd`**, **`buzz:Ndd`**) — a snare
  buzz roll rendered as a three-slash tremolo (`:32`). The note occupies
  a span of the given duration instead of a single point hit. See
  [Buzz rolls](#buzz-rolls) below.

Modifier interaction rules for `double`:

- `ghost double` → both 32nd strokes are parenthesised.
- `accent double` → accent on the first stroke only.
- When multiple instruments share a slot, only those carrying `double` are
  doubled; others play once on the first 32nd.

```groovescript
groove "hihat doubles":
    BD: 1, 3
    SN: 2, 4
    HH: 1, 1e double, 1&, 1a, 2, 2e double, 2&, 2a,
        3, 3e double, 3&, 3a, 4, 4e double, 4&, 4a
```

### Buzz rolls

A `buzz` modifier turns a snare hit into a sustained buzz roll. Unlike
every other event (which is a point-in-time hit), a buzz roll occupies
a span of beats.

```groovescript
SN: 4 buzz        // quarter-note buzz (default when no duration given)
SN: 3 buzz:2      // half-note buzz starting on beat 3
SN: 3 buzz:2d     // dotted-half buzz starting on beat 3
SN: 3 buzz:2dd    // double-dotted-half buzz starting on beat 3
SN: 4 buzz:8      // eighth-note buzz
```

Valid durations are `1`, `2`, `4`, `8`, `16`, with optional `d` (dotted)
or `dd` (double-dotted) suffix. When no duration is specified, `buzz`
defaults to a quarter note (`buzz:4`).

**Constraints:**

- **Snare-only** — `buzz` on any instrument other than `SN` is an error.
- **Incompatible** with `flam`, `drag`, `double`, and `ghost`.
  Compatible with `accent`.
- The buzz span may tie across one or more barlines (e.g. a `buzz:2`
  starting on beat 4 of 4/4 continues into beat 1 of the next bar).
  The LilyPond emitter renders this as tied tremolo notes
  (`sn4:32~ | sn4:32`). A buzz that runs past the last bar of the song
  is a compile error, and hand-played instrument events in the
  continuation bars are rejected the same way as in-bar overlaps.
- **Hand-played** instruments (`HH`, `OH`, `RD`, `CR`, `FT`, `HT`, `MT`,
  `SCS`) cannot have events inside the buzz span — this is a
  compile error.
- **Foot-played** instruments (`BD`, `HF`) *may* overlap the buzz span.
  When they do, the LilyPond emitter produces a localised voice split
  (`<< { sn2:32 } \\ { bd4 bd4 } >>`) so the buzz renders in voice 1
  (stems up) and the feet render in voice 2 (stems down).

`buzz` is accepted everywhere modifiers appear: groove pattern lines,
fill lines, fill instrument lines, variation `add`/`replace`, and
count+notes bodies.

## Hi-hat foot chick

The `HF` instrument represents the hi-hat "chick" — closing the hi-hat
with the foot, with no stick hit. It is a foot-played sound and renders
on the LilyPond `hhp` (hi-hat pedal) staff position.

```groovescript
groove "jazz ride with foot":
  RD: 1, 2, 2let, 3, 4, 4let
  BD: 1, 3
  HF: 2, 4

groove "hh foot + buzz overlap":
  HF: 3, 4
  SN: 3 buzz:2   // HF can overlap the buzz span (foot instrument)
```

`HF` is classified as a **foot instrument** for buzz-roll overlap
purposes — like `BD`, it can coexist with a snare buzz roll without
causing a compile error.
