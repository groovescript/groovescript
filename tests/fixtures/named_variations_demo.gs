metadata:
  title: "Named Variations Demo"
  tempo: 100
  time_signature: 4/4

// Define a reusable variation once, reference it from multiple sections.
variation "crash-on-one":
  add CR at 1

variation "ride-and-crash":
  replace HH with RD at *
  add CR at 1

section "verse":
  bars: 4
  groove: "rock"
  variation "crash-on-one" at bar 1       // user-defined reference
  variation "open-hat-4" at bar 2         // from the built-in library
  variation "flam-backbeat" at bar 3      // from the built-in library

section "chorus":
  bars: 4
  groove: "rock"
  variation "ride-and-crash" at bar 1     // reuse a user-defined variation
  variation "accent-2-4" at bar 4         // library dynamic

section "outro":
  bars: 2
  groove: "rock"
  variation "crash-on-one" at bars 1, 2   // same named variation, two bars
