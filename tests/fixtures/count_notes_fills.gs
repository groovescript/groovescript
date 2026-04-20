title: "Count and Notes Fills"
tempo: 120
time_signature: 4/4

// Demonstrates count + notes fill syntax: each token in the count string
// aligns positionally with the corresponding note(s) in the notes string.
// Parenthesised groups express simultaneous hits on a single count token.

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

// Long instrument names (snare, bass, crash) are accepted as aliases.
fill "snare run":
  count: "3 e & a 4"
  notes: "snare snare snare snare (bass, crash)"

// Canonical abbreviations work too.
fill "crash landing":
  count: "4"
  notes: "(BD, CR)"

// Omitting the ``notes:`` line defaults every count slot to a single snare
// hit — the most common starting point for a fill.
fill "snare roll":
  count: "3 e & a 4 e & a"

section "intro":
  bars: 4
  groove: "money beat"
  fill "crash landing" at bar 4

section "verse":
  bars: 4
  groove: "money beat"
  fill "snare run" at bar 4 beat 3

section "bridge":
  bars: 4
  groove: "money beat"
  fill "snare roll" at bar 4 beat 3
