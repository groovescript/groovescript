title: "Cross-instrument flams and drags"
tempo: 100
time_signature: 4/4

// Demonstrates the parameterised ``flam:<inst>`` / ``drag:<inst>``
// modifier forms. The grace stroke(s) play on the named drum while the
// main hit lands on the carrier instrument.
//
//   HT 1 flam:SN  → hi-tom hit with a single snare grace before it
//   RD 4 drag:SN  → ride hit with two snare graces before it
//   CR 3 flam:HT  → crash hit with a single hi-tom grace before it
//
// Same-instrument flam/drag (the legacy form) still works unchanged.

// Bar showcase: one cross-inst flam, one cross-inst drag, one same-inst
// flam.  The other hand instruments are revoiced around the ornaments to
// keep each beat playable on two hands.
groove "tom feature":
    BD: 1, 3
    HT: 2 flam:SN
    SN: 1 flam, 4 drag:HT

// Pickup fill: cross-tom flam-drag sequence around the kit.
fill "lead-in":
  count "3 e & a 4 e & a":
    3: HT flam:SN
    3e: MT flam:SN
    3&: FT flam:SN
    3a: SN drag:HT
    4: CR flam:HT
    4e: SN
    4&: SN
    4a: SN

section "intro":
  bars: 2
  groove: "tom feature"

section "verse":
  bars: 4
  groove: "tom feature"
  fill "lead-in" at bar 4 beat 3
