metadata:
  title: "Extend Body Text Annotation"
  tempo: 120
  time_signature: 4/4

// Demonstrates `text:` at the top of an `extend:` body. The annotation
// targets bar 1 of the resolved groove, so it appears once per groove
// cycle in the rendered chart.

groove "rock":
  HH: *8
  BD: 1, 3
  SN: 2, 4

// Bare `text:` at the top of an extend body annotates bar 1 of the
// resolved groove. Useful for single-bar derived grooves where there
// is no `bar 1:` block to nest the text in.
groove "main groove":
  extend: "rock"
  add BD at 3&
  text: "Quarter note pulse"

section "verse":
  bars: 4
  groove: "main groove"
