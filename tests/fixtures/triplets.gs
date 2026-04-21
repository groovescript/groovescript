title: "Triplets"
tempo: 112
time_signature: 4/4

// Standard 8th-note money beat for context.
groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

// Triplet groove using the VERBOSE positional labels `1trip` / `1let`.
// `Ntrip` / `Nlet` normalize to the short forms `Nt` / `Nl` at parse time.
groove "triplet":
    1: BD
    1trip: SN
    1let: SN
    2: BD
    3: BD
    3trip: SN
    3let: SN
    4: BD

// Fill using the SHORT forms `3t` / `3l` on a count line that uses the
// bare tokens `trip` / `let`. Both forms resolve to the same IR positions.
fill "triplet fill":
  count "3 trip let 4":
    3: SN
    3t: SN
    3l: SN
    4: BD, CR

// Fill using the BARE tokens `trip` / `let` as the keys themselves — they
// inherit the last-seen beat number (1 here), so `trip` / `let` = `1t` / `1l`.
fill "bare trip let":
  count "1 trip let 2":
    1: BD
    trip: SN
    let: SN
    2: BD

section "intro":
  bars: 4
  groove: "money beat"
  // Bar 4: straight groove on beats 1-2, triplet fill from beat 3.
  fill "triplet fill" at bar 4 beat 3

section "verbose positional":
  bars: 2
  groove: "triplet"

section "bare count tokens":
  bars: 2
  groove: "money beat"
  fill "bare trip let" at bar 2 beat 1
