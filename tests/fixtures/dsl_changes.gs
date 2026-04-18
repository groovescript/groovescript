title: "DSL Changes Showcase"
tempo: 120
time_signature: 4/4

// Showcases the DSL ergonomics upgrades shipped across the "DSL changes"
// backlog batches. Each feature appears at least once below:
//
// Parsing ergonomics
//   - "and" is a long-form alias for "&" anywhere a beat suffix is accepted.
//   - Commas are optional everywhere lists of beats or instruments appear.
//   - `count:` and `notes:` values no longer require surrounding quotes.
//   - Simultaneous-hit groups inside `notes:` may use whitespace instead of
//     commas (e.g. `(bass crash)`).
//   - `notes:` strings may be comma-delimited, so each hit can carry its own
//     modifiers (accent/ghost/flam/drag).
//
// Grooves
//   - Grooves can use the same `count:` / `notes:` positional notation as
//     fills, in addition to the classic `pattern:` style.
//   - Sections can define an unnamed, one-off groove inline.
//
// Fills
//   - Sections can declare one-off inline fills without first defining a
//     named `fill` block at the top level.
//   - A single `fill ... at bar <list>` places the same fill across multiple
//     bars at once, including inline fills with a beat offset.
//
// Variations
//   - Variations no longer require a name — a bare `variation at bar N:`
//     block is legal.
//   - `variation at bars 1 5:` — space-separated bar lists, in addition to
//     the comma-separated form.
//   - `remove` / `add` / `replace` accept multiple instruments in a single
//     action (e.g. `remove snare hat at 2`).
//   - `substitute` (via `count:` / `notes:`) wipes a bar and replaces it with
//     events expanded from a count+notes body.
//   - `modify add <mod> at <target>` / `modify remove <mod> at <target>`
//     decorates existing hits with (or strips) a modifier without re-stating
//     the instrument.

// Classic pattern — commas optional in beat lists; `and` shorthand on HH.
groove "money beat":
    BD: 1 3
    SN: 2 4
    // Bare `and` resolves against the last beat number, so this is
    // shorthand for `1, 1&, 2, 2&, 3, 3&, 4, 4&` — "HH on every eighth".
    HH: 1 and 2 and 3 and 4 and

// Count+notes groove body, unquoted. Subdivision inferred from the count
// labels (16ths here).
groove "sixteenth run":
  count: 1 e and a 2 e and a 3 e and a 4 e and a
  notes: BD, HH, SN, HH, BD, HH, SN, HH, BD, HH, SN, HH, BD, HH, SN, HH

// Top-level count+notes fill using the comma-delimited notes syntax with
// per-hit accent/ghost modifiers.
fill "dynamic run":
  count: "1 and 2 and 3 and 4 and"
  notes: "SN accent, SN ghost, SN ghost, SN ghost, SN accent, SN ghost, SN ghost, (BD, CR) accent"

// Unquoted count+notes fill with a whitespace-only simultaneous group.
fill "shot":
  count: 3 and 4 and
  notes: (BD CR) accent, HH, SN ghost, HH

// Multi-bar-placeable build fill.
fill "build":
  count "3 e and a 4":
    3: SN
    3e: SN
    3and: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  // Anonymous variation (no name required), comma-free beat list.
  variation at bar 4:
    add CR accent at 1

section "verse":
  bars: 4
  groove: "sixteenth run"
  fill "dynamic run" at bar 4
  // Multi-instrument remove: drop both snare and hat on beat 2.
  variation at bar 2:
    remove snare hat at 2
  // Multi-instrument add + per-hit modifiers.
  variation at bar 3:
    add snare ghost kick accent at 3e
  // Pairwise replace: snare → ride, hat → crash, both on beat 4.
  variation at bar 4:
    replace snare hat with ride crash at 4

section "chorus":
  bars: 4
  groove: "money beat"
  // Inline one-off fill, defined right where it's placed. Position→
  // instrument lines mix comma-free and comma-ful forms freely.
  fill at bar 4 beat 3:
    count "3 e and a 4":
      3: SN accent
      3e: SN ghost
      3and: SN ghost
      3a: SN ghost
      4: BD CR
  // Whole-bar substitute with a count+notes body. Note the comma-free
  // simultaneous group `(bass crash)` in the final slot.
  variation "shot" at bar 2:
    count: 1 and 2 and 3 and 4 and
    notes: bass, hat, snare, hat, bass, hat, snare, (bass crash) accent

section "bridge":
  bars: 8
  groove: "money beat"
  // Named fill placed at multiple bars via a bar list.
  fill "build" at bar 4, 8 beat 3
  // Accent all hits on beat 2 of bars 2 and 6 without retyping each
  // instrument; space-separated bar list, no comma required.
  variation at bars 2 6:
    modify add accent at 2
  // Strip an accent modifier from an existing hit without touching the
  // underlying snare event.
  variation at bar 3:
    modify remove accent at 2

section "outro":
  bars: 2
  // Inline one-off groove — no name, no top-level declaration needed.
  // Grid (8ths) inferred from the beat labels.
  groove:
      BD: 1 3
      SN: 2 4
      crash: 1
      HH: 2 3 4
