title: "Extra Cymbals Demo"
tempo: 120
time_signature: 4/4

// Splash, china, second crash, and stack — each shown beside the
// existing crash so the visual distinction is obvious. Every new
// cymbal has a unique notehead+staff-position pair:
//   CR  — x at position 7 (existing)
//   CR2 — x at position 6 (one space below CR; opposite-side mounting)
//   SP  — diamond at position 8 (above CR; small high cymbal)
//   CH  — circle-x at position 9 (highest; trashy character)
//   ST  — slash at position 7 (same line as CR; pre-muted/short)
groove "all cymbals":
  BD: 1, 3
  SN: 2, 4
  HH: *8
  SP: 1
  CH: 1&
  CR2: 3
  ST: 4&

// Choke modifier on the new ringing cymbals (SP, CH, CR2). Stack is
// physically pre-muted so it does not accept choke.
groove "ending":
  BD: 1
  SN: 4
  CR: 1 accent choke
  SP: 2 choke
  CH: 3 choke
  CR2: 4 accent choke

section "demo":
  bars: 2
  groove: "all cymbals"

section "ending":
  bars: 1
  groove: "ending"
