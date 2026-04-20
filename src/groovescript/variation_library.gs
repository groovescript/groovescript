// Built-in named variations library. Reference any of these from a
// section via `variation "name" at bar N` (no trailing body) without
// defining them in your own file. Define a variation with the same
// name at the top level to override the library version.
//
// Kept intentionally small — these are the variations that compose
// with almost any rock/pop groove. Roll your own at the top level for
// anything more specific.

// ----- Open hi-hat accents -----

variation "open-hat-4":
  replace HH with OH at 4

variation "open-hat-4&":
  replace HH with OH at 4&

// ----- Crash accents -----

variation "crash-1":
  add CR at 1

// ----- Instrument drops -----

variation "drop-kick":
  remove BD at *

// ----- Dynamics -----

variation "accent-2-4":
  modify add accent to SN at 2, 4

variation "flam-backbeat":
  modify add flam to SN at 2, 4
