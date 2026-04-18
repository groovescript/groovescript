metadata:
  title: "32nd Note Double Strokes"
  tempo: 100
  time_signature: 4/4

// A straight 16th-note hi-hat groove with double strokes on 1e and 4a.
groove "main":
    BD: 1, 3
    SN: 2, 4
    HH: 1, 1e double, 1&, 1a, 2, 2e, 2&, 2a, 3, 3e double, 3&, 3a, 4, 4e, 4&, 4a double

// Same groove using "32nd" alias — should behave identically.
groove "alias":
    BD: 1, 3
    SN: 2, 4
    HH: 1, 1e 32nd, 1&, 1a, 2, 2e, 2&, 2a, 3, 3e 32nd, 3&, 3a, 4, 4e, 4&, 4a 32nd

// A fill bar that uses double strokes and ghost modifier together.
fill "turnaround":
  count "1 e & a 2 e & a 3 e & a 4 e & a":
    1: SN ghost double
    1e: SN
    1&: SN double
    1a: SN
    2: SN
    2e: SN ghost double
    2&: SN
    2a: SN
    3: SN double
    3e: SN
    3&: SN double
    3a: SN
    4: BD
    4e: SN
    4&: BD
    4a: CR

section "INTRO":
  bars: 4
  groove: "main"

section "OUTRO":
  bars: 4
  groove: "alias"
  fill "turnaround" at bar 4
