title: "Chained Like"

groove "basic":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "ending":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "verse":
  bars: 4
  groove: "basic"
  fill "ending" at bar 4

section "verse 2":
  like "verse" with fills

section "verse 3":
  like "verse 2" with fills
