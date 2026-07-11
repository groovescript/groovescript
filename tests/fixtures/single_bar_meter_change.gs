title: "Single Bar Meter Change"
tempo: 120
time_signature: 4/4

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 8
  groove: "money beat"
  variation at bar 5:
    time_signature: 2/4

section "chorus":
  bars: 8
  groove: "money beat"
  variation "turnaround" at bar 4:
    time_signature: 2/4
    add BD at 1
    add SN at 2
