title: "Mixed Meter"
tempo: 110
time_signature: 4/4

// A 4/4 rock groove for the verse
groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

// A 7/8 groove for the bridge: one hit per eighth-note slot
// (BD on the downbeat of each 2+2+3 group, SN on the "off"s).
groove "odd":
    BD: 1, 3, 5
    SN: 2, 4, 6
    HH: *8

// A 3/4 waltz groove for the outro
groove "waltz":
    BD: 1
    SN: 2, 3
    HH: *8

section "verse":
  bars: 4
  groove: "rock"

// Time signature changes to 7/8 for the bridge
section "bridge":
  bars: 4
  groove: "odd"
  time_signature: 7/8

// And back — the outro is in 3/4
section "outro":
  bars: 4
  groove: "waltz"
  time_signature: 3/4
