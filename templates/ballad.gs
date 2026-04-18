title: "{{TITLE}}"
tempo: 72
time_signature: 4/4
dsl_version: 1

// Slow ballad: sparse kick and snare, open hi-hat for a breathy feel.
groove "ballad groove":
    BD: 1, 3
    SN: 2, 4
    OH: 1, 2, 3, 4

groove "ballad build":
    BD: 1, 2&, 3
    SN: 2, 4
    OH: 1, 2, 3, 4
    CR: 1

fill "swell":
  count "4 e & a":
    SN: 4, 4e, 4&, 4a

fill "crash and land":
  count "4":
    BD: 4
    CR: 4

section "verse":
  bars: 8
  groove: "ballad groove"
  fill "swell" at bar 8 beat 4

section "chorus":
  bars: 8
  groove: "ballad build"
  fill "swell" at bar 8 beat 4

section "verse 2":
  like "verse" with fills

section "chorus 2":
  like "chorus" with fills

section "bridge":
  bars: 4
  groove: "ballad groove"
  fill "crash and land" at bar 4

section "outro":
  bars: 4
  groove: "ballad groove"
