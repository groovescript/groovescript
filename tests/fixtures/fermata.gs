title: "Fermata Demo"
tempo: 120
time_signature: 4/4

// Verse: a steady backbeat — no fermatas, for contrast.
groove "verse":
  BD: 1, 3
  SN: 2, 4
  HH: *8

// Big finish: held crash on beat 1 (fermata + accent), bar plays out as
// silence. The chart shows "𝄐" above the chord.
groove "big finish":
  BD: 1
  CR: 1 accent fermata

// Buzz-roll ending: a snare buzz roll under a fermata, plus a held crash
// to close. Shows fermata composing with `buzz` (a common drum-corps
// ending) and on a chord that fuses BD and CR.
groove "roll-out":
  SN: 1 buzz fermata
  BD: 4
  CR: 4 fermata

section "verse":
  bars: 2
  groove: "verse"

section "finish":
  bars: 1
  groove: "big finish"

section "roll out":
  bars: 1
  groove: "roll-out"
