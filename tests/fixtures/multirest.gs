title: "Multirest Demo"
tempo: 120
time_signature: 4/4

// Demonstrates the play: multirest xN item, which renders an N-bar rest
// as a single visual multi-bar rest measure with the count above (the
// standard "tacet N bars" notation), as opposed to ``rest xN`` which
// produces N visible whole-bar rests.

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  play:
    groove "money beat" x4

section "tacet":
  play:
    multirest x16

section "verse":
  play:
    groove "money beat" x4
    multirest x8
    groove "money beat" x4
