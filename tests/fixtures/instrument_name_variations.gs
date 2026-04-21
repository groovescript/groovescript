title: "Instrument Name Variations"
tempo: 120
time_signature: 4/4

// Demonstrates that instruments can be written with verbose names or
// lowercase abbreviations; they all normalize to canonical abbreviations
// in the IR.

// Groove using a mix of canonical (HH), lowercase (sn), and verbose (kick)
// names on pattern lines.
groove "alias groove":
    kick: 1, 3
    snare: 2, 4
    hat: *8

// Side-stick (SCS aliases).
groove "cross-stick groove":
    kick:        1, 3
    cross-stick: 2, 4
    hat:         *8

groove "click groove":
    kick:   1, 3
    click:  2, 4
    hat:    *8

// Low-tom (FT) alias exercise.
groove "floor tom groove":
    kick:   1, 3
    snare:  2, 4
    lowtom: 1&, 3&
    hat:    *8

// Fill using verbose names in position→instruments notation
fill "alias fill":
  count "3 e & a 4":
    3: snare
    3e: snare
    3&: snare
    3a: snare
    4: kick, crash

section "verse":
  bars: 4
  groove: "alias groove"
  fill "alias fill" at bar 4 beat 3
  variation "add ride" at bar 2:
    add ride at 1, 3
    remove hat at 1, 3

section "cross-stick":
  bars: 2
  groove: "cross-stick groove"

section "click":
  bars: 2
  groove: "click groove"

section "floor tom":
  bars: 2
  groove: "floor tom groove"
