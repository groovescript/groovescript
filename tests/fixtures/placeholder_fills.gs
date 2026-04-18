// Fixture demonstrating fill placeholder syntax.
// The groove renders normally; placeholder bars carry a boxed label above
// the staff to indicate that a fill is intended even though the notes are TBD.

metadata:
  title: "Placeholder Fills Demo"
  tempo: 120
  time_signature: 4/4

groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *16

section "verse":
  bars: 4
  groove: "rock"
  fill placeholder at bar 4

section "chorus":
  bars: 4
  groove: "rock"
  fill placeholder "build" at bar 3
  fill placeholder "crash out" at bar 4 beat 3
