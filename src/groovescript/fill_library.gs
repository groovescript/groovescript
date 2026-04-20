// Built-in drum fill library. Each fill is one bar of 4/4. Reference
// any of these by name from a section's `fill "..." at bar N` line
// without defining them in your own file. Define a fill with the same
// name to override the library version.
//
// Naming convention: base name = whole bar; `-half` = beats 3-4;
// `-beat` = beat 4 only; `-trip` = 8th-note triplet grid; `-up` =
// ascending pitch variant. Default grid is 16ths.

// ----- Single-hit accents -----

fill "crash":
  count "1":
    1: BD, CR

fill "crash-4":
  count "4":
    4: BD, CR

// ----- Snare rolls (16ths) -----

fill "snare-roll":
  count "1 2 3 4":
    SN: *16

fill "snare-roll-half":
  count "3 4":
    SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a

fill "snare-roll-beat":
  count "4":
    SN: 4, 4e, 4&, 4a

// ----- Snare rolls (triplets) -----

fill "snare-roll-trip":
  count "1 2 3 4":
    SN: *8t

fill "snare-roll-trip-half":
  count "3 4":
    SN: 3, 3t, 3l, 4, 4t, 4l

// ----- Buzz rolls -----

fill "buzz-roll":
  count "1":
    SN: 1 buzz:1

fill "buzz-roll-half":
  count "3":
    SN: 3 buzz:2

fill "buzz-roll-beat":
  count "4":
    SN: 4 buzz

// ----- Tom rolls (16ths, descending HT -> MT -> FT) -----

fill "tom-roll":
  count "1 2 3 4":
    HT: 1, 1e, 1&, 1a
    MT: 2, 2e, 2&, 2a
    FT: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a

fill "tom-roll-half":
  count "3 4":
    MT: 3, 3e, 3&, 3a
    FT: 4, 4e, 4&, 4a

fill "tom-roll-up":
  count "1 2 3 4":
    FT: 1, 1e, 1&, 1a
    MT: 2, 2e, 2&, 2a
    HT: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a

// ----- Tom rolls (triplets, descending) -----

fill "tom-roll-trip":
  count "1 2 3 4":
    HT: 1, 1t, 1l
    MT: 2, 2t, 2l
    FT: 3, 3t, 3l, 4, 4t, 4l

// ----- Snare + tom mixes -----

fill "snare-tom-half":
  count "3 4":
    SN: 3, 3e, 3&, 3a
    HT: 4, 4e
    FT: 4&, 4a

fill "around-kit":
  count "1 2 3 4":
    SN: 1
    HT: 2
    MT: 3
    FT: 4

fill "around-kit-16ths":
  count "1 2 3 4":
    SN: 1, 1e, 1&, 1a
    HT: 2, 2e, 2&, 2a
    MT: 3, 3e, 3&, 3a
    FT: 4, 4e, 4&, 4a

// ----- Rudimental -----

fill "flam-fill":
  count "3 4":
    SN: 3 flam, 3e, 3&, 3a, 4 flam, 4e, 4&, 4a

fill "linear-half":
  count "3 4":
    3: SN
    3e: BD
    3&: SN
    3a: BD
    4: HT
    4e: BD
    4&: MT
    4a: FT
