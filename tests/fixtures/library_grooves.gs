metadata:
  title: "Library Grooves"
  tempo: 120
  time_signature: 4/4

// Demonstrates the built-in groove library: reference a named groove
// without defining it in the file.

fill "crash in":
  count "4":
    4: BD, CR

section "rock":
  bars: 4
  groove: "rock"
  fill "crash in" at bar 4

section "16th rock":
  bars: 4
  groove: "16th-rock"
  fill "crash in" at bar 4

section "funk":
  bars: 4
  groove: "funk"
  fill "crash in" at bar 4

section "shuffle":
  bars: 4
  groove: "shuffle"
  fill "crash in" at bar 4

section "jazz ride":
  bars: 4
  groove: "jazz-ride"
  fill "crash in" at bar 4
