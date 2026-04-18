// Multi-bar fill: a fill spanning two bars.
// Bar 1: snare buildup starting at beat 3.
// Bar 2: full-bar crash + kick resolution.

metadata:
  title: "Multi-Bar Fill Test"
  tempo: 120

groove "rock":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "two-bar fill":
  count "3 e & a 4 e & a":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: SN
    4e: SN
    4&: SN
    4a: SN
  count "1 2 3 4":
    1: BD, CR
    2: BD
    3: BD
    4: BD

section "verse":
  bars: 8
  groove: "rock"
  fill "two-bar fill" at bar 7 beat 3
