title: "Multirest Demo"
tempo: 120
time_signature: 4/4

// Demonstrates that ``rest xN`` for N > 1 collapses to a single multi-bar
// rest measure with the count above the staff (the standard "tacet N bars"
// notation). MIDI/MusicXML still play back the full N bars of silence so
// playback length matches the printed chart. A lone ``rest`` (or
// ``rest x1``) stays a plain whole-bar rest.

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  play:
    groove "money beat" x4

section "tacet":
  play:
    rest x16

section "verse":
  play:
    groove "money beat" x4
    rest x8
    groove "money beat" x4
