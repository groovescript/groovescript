title: "Tempo Changes"
tempo: 112

groove "rock":
  BD: 1, 3
  SN: 2, 4
  HH: *8

groove "build":
  BD: 1, 2, 3, 4
  SN: 2, 4
  HH: *16

# A gradual push into the chorus, then a hold: the verse ends faster than it
# started and the chorus begins back at 112 with an automatic "a tempo".
section "verse":
  bars: 8
  groove: "rock"
  accel from bar 7 to bar 8 beat 3 to tempo 124

section "chorus":
  bars: 8
  groove: "build"
  # Pull back mid-section, then snap back on the downbeat.
  rit from bar 4 beat 3 to bar 5 to tempo 100
  a tempo at bar 6

# Classic ending: a two-bar rit with no explicit target (80%) on the last bars.
section "outro":
  bars: 4
  groove: "rock"
  rit from bar 3 to bar 4
  variation at bar 4:
    add CR at 1
    remove HH at 1
