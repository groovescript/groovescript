title: "Play Inline Groove"
tempo: 120
time_signature: 4/4

// Demonstrates nameless and named inline grooves inside a section's play:
// block. The body uses the same groove_body grammar as section-level inline
// grooves, so single-bar, multi-bar, and extend: shapes are all allowed,
// each with an optional xN repeat count. A named inline groove can be
// referenced by name later in the same section.

groove "verse":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "song":
  play:
    groove "verse" x2
    // Single-bar inline groove.
    groove x2:
        BD: 1, 3
        SN: 2, 4
        HH: *16
    groove:
        BD: 1
        SN: 3
        HH: *8
    // Multi-bar inline groove (bar N: blocks).
    groove x2:
      bar 1:
        HH: *8
        SN: 2, 4
        BD: 1, 3
      bar 2:
        HH: *8
        BD: 1, 3and
    // Inline groove that extends a named groove.
    groove x2:
      extend: "verse"
    // Named inline groove — defined here, referenced again below by name.
    groove "tom groove" x1:
        FT: *8
        BD: 1, 3
        SN: 2, 4
    groove "tom groove" x2
    rest
