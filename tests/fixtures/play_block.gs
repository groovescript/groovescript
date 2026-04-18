title: "Play Block Demo"
tempo: 120
time_signature: 4/4

// Demonstrates the play: block syntax: ordered grooves, one-off bars, and rests.

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "half-time":
    BD: 1, 2&
    SN: 3
    HH: *8

fill "crash landing":
  count "4":
    4: BD, CR

fill "snare run":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "verse":
  play:
    groove "money beat" x4
    bar "setup":
      BD: 1, 3
      SN: 4
      CR: 1
    rest x2
    groove "money beat" x4
    bar "setup" x1
  fill "crash landing" at bar 4
  fill "snare run" at bar 9 beat 3

section "chorus":
  play:
    groove "half-time" x4
    bar "big hit":
      BD: 1
      SN: 1
      CR: 1
    rest x1
    groove "half-time" x2
    bar "big hit" x1
