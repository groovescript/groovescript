metadata:
  title: "Library Fills"
  tempo: 120
  time_signature: 4/4

// Demonstrates the built-in fill library: reference a named fill
// without defining it in the file. The grooves themselves are also
// resolved from the built-in groove library.

section "rock":
  bars: 4
  groove: "rock"
  fill "crash" at bar 1
  fill "snare-roll-half" at bar 4 beat 3

section "16th rock":
  bars: 4
  groove: "16th-rock"
  fill "snare-roll" at bar 4

section "funk":
  bars: 4
  groove: "funk"
  fill "tom-roll-half" at bar 4 beat 3

section "shuffle":
  bars: 4
  groove: "shuffle"
  fill "tom-roll" at bar 4
