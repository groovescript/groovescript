title: "Top-Level Crash-In"
tempo: 120
time_signature: 4/4

// Fixture for the top-level ``crash in`` directive. Every section after
// the first picks up a bar-1 crash-in by default. Sections opt out with
// ``no crash in`` or override the bars with their own ``crash in [at …]``.

crash in

groove "hh8 beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

// First section: no crash-in (top-level skips the first section).
section "intro":
    bars: 2
    groove: "hh8 beat"

// Inherits the top-level default — bar 1 gets a crash.
section "verse":
    bars: 4
    groove: "hh8 beat"

// Opts out of the top-level default — no crash anywhere.
section "bridge":
    bars: 2
    groove: "hh8 beat"
    no crash in

// Overrides the top-level default with an explicit bar list.
section "chorus":
    bars: 8
    groove: "hh8 beat"
    crash in at 1, 5
