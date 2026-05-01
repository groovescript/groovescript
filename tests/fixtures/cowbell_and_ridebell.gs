title: "Cowbell and Ride Bell Demo"
tempo: 120
time_signature: 4/4

// Latin-flavoured groove driven by a steady cowbell on every quarter,
// with ride bell accents on the downbeats. CB renders as a triangle
// notehead at staff position 6; RB renders as a hollow diamond on the
// ride line (position 4).
groove "cowbell pulse":
  BD: 1, 2&, 3
  SN: 2, 4
  CB: *4
  RB: 1, 3

// Bell-of-the-ride pattern: bow on weak beats, bell on strong beats —
// substitution rather than stacking, so the ride/ride-bell mutex is not
// triggered.
groove "bell pattern":
  BD: 1, 3
  SN: 2, 4
  RB: 1, 3
  RD: 2, 4

section "intro":
  bars: 2
  groove: "cowbell pulse"

section "verse":
  bars: 2
  groove: "bell pattern"
