title: "Break Directive Showcase"
tempo: 112
time_signature: 4/4

// Demonstrates the four forms of the ``break on bar N …`` directive.
// When no ``through`` clause is given, the break runs to the end of the
// section. A ``through`` clause gives an explicit end bar (and optional
// end beat).

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
// Bar 3 and bar 4 should be empty rests — the break runs to end of section.
// Bars 1 and 2 play the full money beat.

section "break from bar (no through)":
  bars: 4
  groove: "money beat"
  break on bar 3

// ── Form 2: break on bar N beat B ────────────────────────────────────────
// Bar 2 plays beats 1-2 only; beats 3-4 are rests. Bars 3 and 4 are
// fully silent. Bar 1 is normal.

section "break from beat (no through)":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3

// ── Form 3 (through): break on bar N beat B through bar M ─────────────────
// Bar 2 plays beats 1-2 then rests. Bar 3 is fully silent. Bars 1 and 4
// are normal.

section "break with explicit end bar":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3 through bar 3

// ── Form 4 (through): break on bar N beat B through bar M beat C ──────────
// Bar 2 rests from beat 3 onward. Bar 3 rests beats 1-2, then resumes on
// beat 3. Bars 1 and 4 are normal.

section "break with bounded end beat":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3 through bar 3 beat 2

// ── Single-bar break via through ──────────────────────────────────────────
// ``through bar N`` with the same N as the start limits the break to one
// bar. Bars 1, 2, 4 are normal; bar 3 is a rest.

section "single bar break (through same bar)":
  bars: 4
  groove: "money beat"
  break on bar 3 through bar 3

// ── Two bounded breaks ────────────────────────────────────────────────────
// Bars 1 and 3 are silent; bars 2 and 4 are normal.

section "alternating breaks":
  bars: 4
  groove: "money beat"
  break on bar 1 through bar 1
  break on bar 3 through bar 3

// ── Break overrides fill ──────────────────────────────────────────────────
// A fill is placed on bar 3 but the bounded break silences it — bar 3
// should be an empty rest regardless.

section "break overrides fill":
  bars: 4
  groove: "money beat"
  fill "crash landing" at bar 3
  break on bar 3 through bar 3

// ── Longer break on denser groove ─────────────────────────────────────────
// 8-bar section on driving 16ths. ``break on bar 3 beat 3 through bar 5
// beat 2`` silences bar 3 from beat 3, all of bar 4, and bar 5 through
// beat 2. Bars 1-2, partial bar 3, partial bar 5, and bars 6-8 have notes.

section "long break in dense groove":
  bars: 8
  groove: "driving 16ths"
  break on bar 3 beat 3 through bar 5 beat 2
