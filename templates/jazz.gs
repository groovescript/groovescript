title: "{{TITLE}}"
tempo: 160
time_signature: 4/4
dsl_version: 1

// Jazz ride pattern with swing feel.
// RD carries the quarter-note ride; HH marks 2 and 4 with foot; SN comps lightly.
groove "swing":
    RD: 1, 1&, 2, 2&, 3, 3&, 4, 4&
    HH: 2, 4
    SN: 2, 4

groove "swing open":
    RD: 1, 1&, 2, 2&, 3, 3&, 4, 4&
    HH: 2, 4
    BD: 1, 3

fill "trading four":
  count "1 e & a 2 e & a 3 e & a 4":
    SN: 1, 1e, 1&, 1a, 2, 2e, 2&, 2a
    HT: 3, 3e, 3&, 3a
    4: BD, CR

section "head":
  bars: 8
  groove: "swing"
  fill "trading four" at bar 8

section "solos":
  bars: 16
  groove: "swing"

section "head out":
  bars: 8
  groove: "swing open"
  fill "trading four" at bar 8
