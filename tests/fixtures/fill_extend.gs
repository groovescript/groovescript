metadata:
  title: "Fill Extension"
  tempo: 120
  time_signature: 4/4

// Demonstrates `extend:` on fills — purely-additive layering on top of
// a base fill (user-defined or from the built-in fill library). The
// base fill's events are preserved; the extension body adds more.

// Add a driving bass-drum pulse to the library snare roll. No need for
// a `count "..."` wrapper around the extension body — the bare form
// works for single-bar extensions.
fill "snare-roll+kick":
  extend: "snare-roll"
  BD: *4

// Alias — no body. `fill "big hit"` is a synonym for the library `crash`.
fill "big hit":
  extend: "crash"

// A user-defined two-bar base fill.
fill "two-bar base":
  count "3 e & a 4 e & a":
    SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a
  count "1 2 3 4":
    1: BD, CR
    2: BD
    3: BD
    4: BD

// Broadcast: a single-bar extension applied to every bar of a 2-bar base.
fill "two-bar + hat":
  extend: "two-bar base"
  count "1 2 3 4":
    HH: *4

section "driving snare roll":
  bars: 4
  groove: "rock"
  fill "snare-roll+kick" at bar 4

section "big hit opener":
  bars: 4
  groove: "rock"
  fill "big hit" at bar 1

section "layered two-bar":
  bars: 4
  groove: "rock"
  fill "two-bar + hat" at bar 3
