metadata:
  title: "Basic Fills"
  tempo: 120
  time_signature: 4/4

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 2&, 4
      SN: 2, 4
      HH: *8

fill "bar 4 fill":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "bar 4 fill" at bar 4 beat 3

section "verse":
  bars: 8
  groove: "two bar"
  fill "bar 4 fill" at bar 8 beat 3
