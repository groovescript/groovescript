title: "Time Signature 3/4"
tempo: 120
time_signature: 3/4

// A simple 3/4 waltz pattern: BD on 1, HH on all, SN on 2 and 3.
groove "waltz beat":
    BD: 1
    SN: 2, 3
    HH: *8

// A two-bar variation for the B section
groove "waltz variation":
    bar 1:
      BD: 1
      SN: 2, 3
      HH: *8
    bar 2:
      BD: 1, 3
      SN: 2
      HH: *8

section "A":
  bars: 8
  groove: "waltz beat"

section "B":
  bars: 8
  groove: "waltz variation"

section "A2":
  like "A"
