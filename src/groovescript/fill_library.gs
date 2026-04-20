// Built-in drum fill library. Each fill is one bar of 4/4 unless noted.
// Reference these by name from any section's `fill "..." at bar N` line
// without defining them in your own file. Define a fill with the same
// name to override the library version.

fill "crash":
  count "1":
    1: BD, CR

fill "snare-roll":
  count "1 2 3 4":
    SN: *16

fill "snare-roll-half":
  count "3 4":
    SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a

fill "snare-roll-beat":
  count "4":
    SN: 4, 4e, 4&, 4a

fill "snare-roll-trip":
  count "1 2 3 4":
    SN: *8t

fill "tom-roll":
  count "1 2 3 4":
    HT: 1, 1e, 1&, 1a
    MT: 2, 2e, 2&, 2a
    FT: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a

fill "tom-roll-half":
  count "3 4":
    MT: 3, 3e, 3&, 3a
    FT: 4, 4e, 4&, 4a
