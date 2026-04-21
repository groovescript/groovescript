metadata:
  title: "Groove Extend with Variations"
  tempo: 110
  time_signature: 4/4

// Demonstrates variation actions inside `extend:` bodies. A derived
// groove is declared once and then reused like any other named groove,
// so a section no longer has to stack a `groove: ...` plus a matching
// `variation "..." at bar ...` line every time.

// A basic 8th-note rock pattern, user-defined so the fixture is
// self-contained (no dependency on the built-in library).
groove "rock":
  HH: *8
  BD: 1, 3
  SN: 2, 4

// Derived groove: same rhythm as "rock", but every hi-hat hit becomes a
// ride cymbal hit. `at *` expands to every beat position occupied by
// HH in the base. Bare actions apply to every bar of the base.
groove "rock on ride":
  extend: "rock"
  replace HH with RD at *

// Pattern-line overrides and variation actions compose. The BD row is
// overridden first (1, 2&, 3), then `replace HH with RD at *` runs on
// the merged pattern to produce the ride cymbal version.
groove "push on ride":
  extend: "rock"
  BD: 1, 2&, 3
  replace HH with RD at *

// A two-bar base so we can demonstrate per-bar scoping.
groove "two-bar rock":
  bar 1:
    HH: *8
    BD: 1, 3
    SN: 2, 4
  bar 2:
    HH: *8
    BD: 1, 3
    SN: 2, 4

// Scoped actions: `variation at bar N:` / `variation at bars N, M:`
// limits a bundle of actions to the listed bars only. Bare actions in
// the same extend body still apply to every bar.
groove "two-bar with lift":
  extend: "two-bar rock"
  variation at bar 1:
    replace HH with RD at *
  variation at bar 2:
    add CR at 1

section "verse":
  bars: 4
  groove: "rock on ride"

section "pre-chorus":
  bars: 2
  groove: "push on ride"

section "chorus":
  bars: 4
  groove: "two-bar with lift"
