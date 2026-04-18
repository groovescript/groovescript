title: "{{TITLE}}"
tempo: 120
time_signature: 4/4
dsl_version: 1

groove "main groove":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "crash in":
  count "4":
    BD: 4
    CR: 4

fill "snare build":
  count "3 e & a 4":
    SN: 3, 3e, 3&, 3a
    4: BD, CR

section "intro":
  bars: 4
  groove: "main groove"
  fill "crash in" at bar 4

section "verse":
  bars: 8
  groove: "main groove"
  fill "snare build" at bar 8 beat 3

section "chorus":
  bars: 8
  groove: "main groove"
  fill "snare build" at bar 8 beat 3

section "verse 2":
  like "verse" with fills

section "chorus 2":
  like "chorus" with fills

section "outro":
  bars: 4
  groove: "main groove"
  fill "crash in" at bar 4
