title: "Cues and Annotations"
tempo: 120
time_signature: 4/4

// Demonstrates vocal cues and bar-level text annotations.

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "chorus groove":
    bar 1:
      text: "Big feel"
      BD: 1, 2&, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 3
      SN: 2, 4
      RD: *8

fill "crash landing":
  count "4":
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  cue "Intro" at bar 1

section "verse":
  bars: 8
  groove: "money beat"
  cue "Verse — vocals enter" at bar 1
  cue "Build" at bar 7 beat 3
  fill "crash landing" at bar 8

section "chorus":
  bars: 8
  groove: "chorus groove"
  cue "Chorus" at bar 1

section "verse 2":
  like "verse" with fills, cues

section "outro":
  bars: 4
  groove: "money beat"
  cue "Outro — fade" at bar 1
