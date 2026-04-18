title: "Dual Notation"
tempo: 120
time_signature: 4/4

// Demonstrates dual notation: both instrument→positions and position→instruments
// styles, used interchangeably in grooves and fills.

// Classic instrument→positions groove
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

// New position→instruments groove
groove "open beat":
    1: BD, HH
    1&: HH
    2: SN, HH
    2&: HH
    3: BD, HH
    3&: HH
    4: SN, HH
    4&: HH

// Multi-bar groove mixing both notations in different bars
groove "two bar":
    bar 1:
      // classic instrument→positions style
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      // new position→instruments style
      1: BD, HH
      1&: HH
      2: SN, HH
      2&: HH
      3: BD, HH
      3&: OH
      4: SN, HH
      4&: HH

// Fill using new instrument→positions notation
fill "crash landing":
  count "4":
    BD: 4
    CR: 4

// Fill mixing both notations: classic position→instruments for the run,
// new instrument→positions for the kick
fill "snare run":
  count "3 e & a 4":
    SN: 3, 3e, 3&, 3a
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "crash landing" at bar 4

section "verse":
  bars: 8
  groove: "two bar"

section "chorus":
  bars: 8
  groove: "open beat"
  fill "snare run" at bar 8 beat 3

section "verse 2":
  like "verse"

section "outro":
  bars: 4
  groove: "money beat"
  fill "crash landing" at bar 4
