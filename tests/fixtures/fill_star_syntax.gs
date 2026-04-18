title: "Fill Star Syntax"

groove "basic":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "floor tom eighths":
  count "1 2 3 4":
    FT: *8 except 4 and

fill "hi-hat sixteenths":
  count "1 2 3 4":
    HH: *16

section "verse":
  bars: 4
  groove: "basic"
  fill "floor tom eighths" at bar 4

section "chorus":
  bars: 4
  groove: "basic"
  fill "hi-hat sixteenths" at bar 4
