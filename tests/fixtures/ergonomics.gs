title: "Ergonomics Features Demo"
tempo: 120
time_signature: 4/4

// B5: Star exclusion — 16th hats with intentional gaps for open hats
groove "open hat pattern":
    BD: 1, 3
    SN: 2, 4
    HH: *16 except 2a, 4a
    OH: 2a, 4a

// A3: Bar-level inheritance — two-bar groove with bar 2 copying bar 1
groove "two bar inherited":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      like: bar 1
      BD: 1, 2&, 4

// E11: Groove extension — crash on beat 1 over the base groove
groove "rock with crash":
  extend: "open hat pattern"
    CR: 1

section "verse":
  bars: 4
  groove: "open hat pattern"

section "chorus":
  bars: 4
  groove: "rock with crash"

section "bridge":
  bars: 4
  groove: "two bar inherited"
