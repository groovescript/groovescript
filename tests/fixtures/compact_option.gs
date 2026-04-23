metadata:
  title: "Compact option demo"
  tempo: 120
  time_signature: 4/4

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

fill "turnaround":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "verse":
  bars: 12
  groove: "money beat"

section "chorus":
  bars: 12
  groove: "money beat"
  fill "turnaround" at bar 12 beat 3
