title: "Modifiers"
tempo: 120
time_signature: 4/4

// Groove with flam on beat 1 snare and accented snare backbeat.
groove "flam groove":
    BD: 1, 3
    SN: 1 flam, 2 accent, 4 accent
    HH: 2, 2&, 3, 3&, 4, 4&

// Fill showcasing flam and drag modifiers in a 16th-note run.
fill "flam fill":
  count "3 e & a 4":
    3: SN flam
    3e: SN
    3&: SN drag
    3a: SN
    4: BD, CR

section "intro":
  bars: 4
  groove: "flam groove"
  fill "flam fill" at bar 4 beat 3

section "verse":
  bars: 4
  groove: "flam groove"
  variation "verse variation" at bar 4:
    add SN ghost at 2&
    replace SN with SN ghost at 4
