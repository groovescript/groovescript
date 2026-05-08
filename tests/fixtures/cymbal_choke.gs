title: "Cymbal Choke Demo"
tempo: 120
time_signature: 4/4

// Verse: a steady backbeat with no choke, for contrast.
groove "verse":
  BD: 1, 3
  SN: 2, 4
  HH: *8

// Stop hit: single big crash with the drummer choking it immediately —
// the chart shows a "+" above the crash and the rest of the bar is silent.
groove "stop hit":
  BD: 1
  CR: 1 choke

// Bell-driven groove with a choked-bell stab on beat 4 — common in
// metal and arena-rock outros where the bell is grabbed mid-ring.
groove "bell stab":
  BD: 1, 3
  SN: 2, 4
  RB: 1, 2, 3
  RB: 4 choke

// Half-time outro: ride choke on beat 2&, accent-and-choke on beat 4.
groove "outro":
  BD: 1
  SN: 3
  RD: 1, 1&, 2, 3, 3&, 4
  RD: 2& accent choke

section "verse":
  bars: 2
  groove: "verse"

section "stop":
  bars: 1
  groove: "stop hit"

section "bell":
  bars: 2
  groove: "bell stab"

section "outro":
  bars: 2
  groove: "outro"
