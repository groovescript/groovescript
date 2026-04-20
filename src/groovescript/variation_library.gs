// Built-in named variations library. Reference any of these from a
// section via `variation "name" at bar N` (no trailing body) without
// defining them in your own file. Define a variation with the same
// name at the top level to override the library version.
//
// Variations here use only stock instruments (HH, OH, RD, CR, BD, SN)
// so they compose with almost any groove. Where a variation targets a
// specific beat, the beat label must exist in the target bar's
// subdivision — the compiler bumps the bar's grid automatically when
// the variation introduces a finer grid (e.g. adding a 16th-note hit).

// ----- Open hi-hat accents -----

variation "open-hat-4":
  replace HH with OH at 4

variation "open-hat-4&":
  replace HH with OH at 4&

variation "open-hat-2&":
  replace HH with OH at 2&

// ----- Cymbal swaps -----

variation "ride-instead":
  replace HH with RD at *

variation "hat-instead":
  replace RD with HH at *

// ----- Crash accents -----

variation "crash-1":
  add CR at 1

variation "crash-4&":
  add CR at 4&

// ----- Instrument drops -----

variation "drop-kick":
  remove BD at *

variation "drop-snare":
  remove SN at *

variation "drop-hats":
  remove HH at *

// ----- Dynamics -----

variation "accent-2-4":
  modify add accent to SN at 2, 4

variation "ghost-snare":
  modify add ghost to SN at *

variation "flam-backbeat":
  modify add flam to SN at 2, 4

// ----- Lead-ins -----

variation "fill-prep":
  add SN at 4e, 4&, 4a

variation "busier-kick":
  add BD at 3&, 4&
