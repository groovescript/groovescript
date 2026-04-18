metadata:
  title: "Basic Arrangement"
  tempo: 116
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

section "intro":
  bars: 4
  groove: "money beat"

section "verse":
  bars: 6
  groove: "two bar"
