title: "Break Directive Showcase"
tempo: 112
time_signature: 4/4

// Demonstrates the four forms of the ``break on bar N …`` directive.
// Each section shows a different form; read the section name and compare
// the printed bars against the surrounding groove to verify correctness.

groove "money beat":
  BD: 1, 3
  SN: 2, 4
  HH: *8

groove "driving 16ths":
  BD: 1, 2&, 3
  SN: 2, 4
  HH: *16

fill "crash landing":
  count "3 e & a 4 e & a":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: SN
    4e: SN
    4&: SN
    4a: SN

// ── Form 1: break on bar N ────────────────────────────────────────────────
// Bar 3 should be completely empty (whole-bar rest). Bars 1, 2, 4 play
// the full money beat.

section "whole bar break":
  bars: 4
  groove: "money beat"
  break on bar 3

// ── Form 2: break on bar N beat B ────────────────────────────────────────
// Bars 1-2 are normal. Bar 3 plays beats 1 and 2, then goes silent from
// beat 3 to the end of the bar. Bar 4 is back to normal.

section "break from beat":
  bars: 4
  groove: "money beat"
  break on bar 3 beat 3

// ── Form 3: break on bar N beat B through bar M ───────────────────────────
// Bar 1 is normal. Bar 2 plays beats 1-2 then silences beat 3 onwards.
// Bar 3 is fully silent. Bar 4 returns to the groove.

section "break across bars":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3 through bar 3

// ── Form 4: break on bar N beat B through bar M beat C ────────────────────
// Bar 1 is normal. Bar 2 silences beats 3-4 (from beat 3). Bar 3 silences
// beats 1-2 (up to and including beat 2) then comes back on beat 3. Bar 4
// is normal.

section "break with bounded end":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3 through bar 3 beat 2

// ── Multiple breaks ───────────────────────────────────────────────────────
// Two separate break directives: bar 1 and bar 3 are silent, bars 2 and 4
// are normal.

section "alternating breaks":
  bars: 4
  groove: "money beat"
  break on bar 1
  break on bar 3

// ── Break with fill ───────────────────────────────────────────────────────
// Fill is placed on bar 3, but the break on bar 3 overrides it completely —
// bar 3 should be an empty rest regardless.

section "break overrides fill":
  bars: 4
  groove: "money beat"
  fill "crash landing" at bar 3
  break on bar 3

// ── Longer break spanning a denser groove ─────────────────────────────────
// 8-bar section on driving 16ths. A 3-bar break runs from beat 3 of bar 3
// through beat 2 of bar 5. Only bars 1, 2, partial-bar-3, partial-bar-5,
// bars 6-8 have notes.

section "long break in dense groove":
  bars: 8
  groove: "driving 16ths"
  break on bar 3 beat 3 through bar 5 beat 2
