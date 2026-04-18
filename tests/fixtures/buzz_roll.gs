title: "Buzz Roll Demo"
tempo: 100

groove "money beat":
  HH: *8
  BD: 1, 3
  SN: 2, 4

groove "buzz under bd":
  HH: 1, 2
  BD: 1, 3, 4
  SN: 3 buzz:2

groove "buzz tie across bar":
  bar 1:
    BD: 1, 3
    SN: 4 buzz:2
  bar 2:
    BD: 1, 3

fill "buzz fill":
  count "1 2 3 4":
    1: SN
    2: SN
    3: SN buzz:2

section "intro":
  bars: 2
  groove: "money beat"

section "with buzz":
  bars: 2
  groove: "money beat"
  fill "buzz fill" at bar 2

section "groove with buzz + bd":
  bars: 2
  groove: "buzz under bd"

section "buzz tie across bar":
  bars: 2
  groove: "buzz tie across bar"
