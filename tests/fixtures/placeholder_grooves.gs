// Fixture demonstrating placeholder-groove syntax.
//
// Placeholder grooves are TBD slots that render as empty bars with a boxed
// rehearsal label, so a chart can capture the form before every groove has
// been transcribed. Three syntactic surfaces:
//
//   1. Top-level declaration:    groove placeholder "verse-A"
//   2. Section's sole groove:    groove: placeholder
//                                groove: placeholder "intro feel"
//   3. Inside a ``play:`` list:  groove placeholder x4
//                                groove placeholder "build" x4
//                                groove "name not yet defined" x4   (auto-promotes)
//
// Two or more nameless placeholder spans within a section get numeric
// suffixes ("Verse groove 1", "Verse groove 2", …) so they can be told
// apart on the page.

metadata:
  title: "Placeholder Grooves Demo"
  tempo: 120
  time_signature: 4/4

groove placeholder "verse-A"

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "intro":
  bars: 4
  groove: placeholder

section "pre-chorus":
  bars: 4
  groove: placeholder "hookline tease"

section "verse":
  bars: 8
  groove: "verse-A"

section "chorus":
  play:
    groove placeholder x4
    groove placeholder "build" x2
    groove "outro idea" x4
    groove "money beat" x4
    groove placeholder x2
