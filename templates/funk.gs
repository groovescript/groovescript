title: "{{TITLE}}"
tempo: 96
time_signature: 4/4
dsl_version: 1

// Funk groove: 16th-note hi-hats, syncopated kick, snare on 2 and 4.
groove "funk groove":
    BD: 1, 2&, 3&
    SN: 2, 4
    HH: 1, 1e, 1&, 1a, 2, 2e, 2&, 2a, 3, 3e, 3&, 3a, 4, 4e, 4&, 4a

groove "funk open":
    BD: 1, 2&, 3&
    SN: 2, 4
    OH: 1, 2, 3, 4
    HH: 1e, 1&, 1a, 2e, 2&, 2a, 3e, 3&, 3a, 4e, 4&, 4a

fill "turn around":
  count "3 e & a 4 e & a":
    SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a

fill "bomb drop":
  count "4 e & a":
    SN: 4, 4e, 4&, 4a
    CR: 4a

section "verse":
  bars: 8
  groove: "funk groove"
  fill "bomb drop" at bar 8 beat 4

section "chorus":
  bars: 8
  groove: "funk open"
  fill "turn around" at bar 8 beat 3

section "verse 2":
  like "verse" with fills

section "chorus 2":
  like "chorus" with fills

section "bridge":
  bars: 4
  groove: "funk groove"
  fill "turn around" at bar 4 beat 3

section "outro":
  bars: 8
  groove: "funk groove"
