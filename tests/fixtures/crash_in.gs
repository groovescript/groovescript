title: "Crash-In Showcase"
tempo: 120
time_signature: 4/4

// Fixture covering the ``crash in`` section flag across different riding
// instruments and star-syntax subdivisions. The first bar of each section
// should start with a crash replacing the riding instrument's beat-1 hit.
// Also exercises the multi-bar (``at <bars>`` and ``at *N``) forms, the
// top-level directive, and the per-section ``no crash in`` opt-out.

groove "hh8 beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "ride4 beat":
    BD: 1, 3
    SN: 2, 4
    RD: *4

groove "open16 beat":
    BD: 1, 3
    SN: 2, 4
    OH: *16

groove "floor tom":
    BD: 1, 3
    SN: 2, 4
    FT: *8

// Ambiguous rider (no *N pattern): the compiler falls back to adding a
// crash on beat 1 of the first bar.
groove "explicit hits":
    BD: 1, 3
    SN: 2, 4
    HH: 2, 4

// No BD on beat 1: crash-in adds both a CR and a BD on beat 1.
groove "no kick on one":
    BD: 3
    SN: 2, 4
    HH: *8

section "hihat rider":
    bars: 2
    groove: "hh8 beat"
    crash in

section "ride rider":
    bars: 2
    groove: "ride4 beat"
    crash in

section "open hat sixteenths":
    bars: 2
    groove: "open16 beat"
    crash in

section "floor tom rider":
    bars: 2
    groove: "floor tom"
    crash in

section "ambiguous rider":
    bars: 2
    groove: "explicit hits"
    crash in

section "added kick":
    bars: 2
    groove: "no kick on one"
    crash in

// Multi-bar crash-in with an explicit list of section-bar offsets.
section "explicit bar list":
    bars: 8
    groove: "hh8 beat"
    crash in at 1, 5

// Multi-bar crash-in via the star form: bars 1, 9, 17 of a 24-bar section.
section "every eight bars":
    bars: 24
    groove: "hh8 beat"
    crash in at *8
