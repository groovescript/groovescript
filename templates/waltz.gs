title: "{{TITLE}}"
tempo: 138
time_signature: 3/4
dsl_version: 1

// Waltz groove: kick on 1, snare on 2 and 3, closed hi-hat throughout.
groove "waltz groove":
    BD: 1
    SN: 2, 3
    HH: *8

groove "waltz open":
    BD: 1
    SN: 2, 3
    OH: 1, 2, 3

fill "waltz fill":
  count "2 & 3 &":
    SN: 2, 2&, 3, 3&
    CR: 3&

section "verse":
  bars: 8
  groove: "waltz groove"
  fill "waltz fill" at bar 8 beat 2

section "chorus":
  bars: 8
  groove: "waltz open"
  fill "waltz fill" at bar 8 beat 2

section "verse 2":
  like "verse" with fills

section "chorus 2":
  like "chorus" with fills

section "outro":
  bars: 8
  groove: "waltz groove"
