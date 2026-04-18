title: "Time Signature 12/8"
tempo: 100
time_signature: 12/8

// A 12/8 compound-time blues shuffle feel: BD on beats 1 and 7
// (the two main pulses), SN on beats 4 and 10 (the compound back
// beats), HH on every eighth note. Beat numbers go all the way up
// to 12 because each eighth note is its own beat.
groove "shuffle":
    BD: 1, 7
    SN: 4, 10
    HH: *8

// A second bar with a BD pickup on beat 12
groove "shuffle drive":
    bar 1:
      BD: 1, 7
      SN: 4, 10
      HH: *8
    bar 2:
      BD: 1, 7, 12
      SN: 4, 10
      HH: *8

section "intro":
  bars: 4
  groove: "shuffle"

section "verse":
  bars: 4
  groove: "shuffle drive"

section "outro":
  like "intro"
