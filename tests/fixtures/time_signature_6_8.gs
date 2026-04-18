title: "Time Signature 6/8"
tempo: 92
time_signature: 6/8

// A 6/8 groove: BD on beats 1 and 4, HH on all 6 eighth notes,
// SN on beats 3 and 6 (the "back beats" of each triplet group).
groove "compound":
    BD: 1, 4
    SN: 3, 6
    HH: *8

// A variation with extra BD on beat 4 for drives
groove "compound drive":
    bar 1:
      BD: 1, 4
      SN: 3, 6
      HH: *8
    bar 2:
      BD: 1, 3, 4, 6
      SN: 3, 6
      HH: *8

section "intro":
  bars: 4
  groove: "compound"

section "verse":
  bars: 8
  groove: "compound drive"

section "outro":
  like "intro"
