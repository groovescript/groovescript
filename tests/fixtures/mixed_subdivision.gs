// Mixed subdivision: triplet and straight content in the same bar.
// Beats 1 & 2 use straight 8th notes, beats 3 & 4 use triplets.

metadata:
  title: "Mixed Subdivision Test"
  tempo: 120

groove "mixed-eighth-triplet":
    BD: 1, 3
    SN: 2, 4
    HH: 1, 1&, 2, 2&
    SN: 3t, 3l, 4t, 4l

groove "mixed-sixteenth-triplet":
    BD: 1, 1e, 1&, 1a, 2, 2e, 2&, 2a
    SN: 3t, 3l, 4t, 4l

section "eighth+triplet":
  bars: 4
  groove: "mixed-eighth-triplet"

section "sixteenth+triplet":
  bars: 4
  groove: "mixed-sixteenth-triplet"
