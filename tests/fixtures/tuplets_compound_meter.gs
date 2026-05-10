title: "Tuplets in compound meter"
tempo: 90
time_signature: 6/8

// In 6/8 the beat is an 8th note, so a sextuplet over a beat is six 32nds
// in the time of four 32nds (an 8th). The tuplet emitter has to scale slot
// durations by the time signature's beat unit — see regression test
// `test_tuplet_in_6_8_uses_correct_slot_durations_in_lilypond`.
groove "compound sextuplet":
    HH: 1{sextuplet 1 accent, 2, 3, 4 accent, 5, 6}, 2, 3, 4{sextuplet 1 accent, 2, 3, 4 accent, 5, 6}, 5, 6
    BD: 1, 4

groove "compound quintuplet":
    HH: 1{quintuplet 1, 2, 3, 4, 5}, 2, 3, 4{quintuplet 1, 2, 3, 4, 5}, 5, 6
    BD: 1, 4

section "compound sextuplet":
    bars: 1
    groove: "compound sextuplet"

section "compound quintuplet":
    bars: 1
    groove: "compound quintuplet"
