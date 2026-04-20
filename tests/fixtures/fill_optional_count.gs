title: "Optional Count Prefix"
tempo: 120
time_signature: 4/4

// Demonstrates that the `count "..."` prefix is optional when every beat
// position is fully specified by the instrument->positions or
// position->instruments lines themselves. Multi-bar fills use the new
// `bar N:` delimiter in lieu of a count label.

groove "basic":
    BD: 1, 3
    SN: 2, 4
    HH: *8

// Single-bar fill with no count prefix, verbose instrument->positions notation.
fill "bare verbose":
    BD: 1, 3
    SN: 2, 4
    CR: 1

// Single-bar fill with no count prefix, position->instruments notation.
fill "bare positions":
    1: BD, CR
    2: SN
    3: SN
    4: SN

// Multi-bar fill delimited by `bar N:` instead of count labels.
fill "two bar bare":
    bar 1:
      SN: 3, 3e, 3&, 3a, 4, 4e, 4&, 4a
    bar 2:
      1: BD, CR
      BD: 2, 3, 4

section "intro":
    bars: 4
    groove: "basic"
    fill "bare verbose" at bar 4

section "verse":
    bars: 4
    groove: "basic"
    fill "bare positions" at bar 4

section "outro":
    bars: 8
    groove: "basic"
    fill "two bar bare" at bar 7

// Inline fills drop the count prefix too — positions are fully specified
// by the lines themselves.
section "bridge":
    bars: 4
    groove: "basic"
    fill at bar 4:
        BD: 1, 3
        SN: 2, 4
        CR: 1

section "double drop":
    bars: 4
    groove: "basic"
    fill at bars 2, 4:
        1: BD, CR
        2: SN

section "half bar":
    bars: 4
    groove: "basic"
    fill at bar 4 beat 3:
        SN: 3, 3e, 3a
        4: BD, CR
