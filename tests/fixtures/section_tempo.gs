title: "Section Tempo"
tempo: 120
time_signature: 4/4

// Demonstrates per-section tempo overrides.
// Intro and verse run at the global 120 BPM.
// The breakdown slows to 80 BPM.
// The chorus picks back up to 140 BPM.
// The outro returns to 100 BPM.

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "half time":
    BD: 1, 2&
    SN: 3
    HH: *8

fill "crash landing":
  count "4":
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"

section "verse":
  bars: 8
  groove: "money beat"
  fill "crash landing" at bar 8

section "breakdown":
  bars: 4
  groove: "half time"
  tempo: 80

section "chorus":
  bars: 8
  groove: "money beat"
  tempo: 140
  fill "crash landing" at bar 8

section "outro":
  bars: 4
  groove: "money beat"
  tempo: 100
