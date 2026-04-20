metadata:
  title: "Library Fills"
  tempo: 120
  time_signature: 4/4

// Demonstrates the built-in fill library: reference a named fill
// without defining it in the file. The grooves themselves are also
// resolved from the built-in groove library. Each section below
// showcases a different family of stock fills.

section "accents":
  bars: 4
  groove: "rock"
  fill "crash" at bar 1
  fill "crash-4" at bar 4

section "snare rolls":
  bars: 4
  groove: "rock"
  fill "snare-roll-beat" at bar 1 beat 4
  fill "snare-roll-half" at bar 2 beat 3
  fill "snare-roll" at bar 4

section "snare roll triplets":
  bars: 4
  groove: "rock"
  fill "snare-roll-trip-half" at bar 2 beat 3
  fill "snare-roll-trip" at bar 4

section "buzz rolls":
  bars: 4
  groove: "rock"
  fill "buzz-roll-beat" at bar 1 beat 4
  fill "buzz-roll-half" at bar 2 beat 3
  fill "buzz-roll" at bar 4

section "tom rolls":
  bars: 4
  groove: "16th-rock"
  fill "tom-roll-half" at bar 2 beat 3
  fill "tom-roll-up" at bar 3
  fill "tom-roll" at bar 4

section "tom triplets":
  bars: 2
  groove: "shuffle"
  fill "tom-roll-trip" at bar 2

section "around the kit":
  bars: 4
  groove: "rock"
  fill "around-kit" at bar 2
  fill "snare-tom-half" at bar 3 beat 3
  fill "around-kit-16ths" at bar 4

section "rudimental":
  bars: 4
  groove: "funk"
  fill "linear-half" at bar 2 beat 3
  fill "flam-fill" at bar 4 beat 3
