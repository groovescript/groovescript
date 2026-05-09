title: "Tuplets showcase"
tempo: 100
time_signature: 4/4

// Whole-beat sextuplet on beat 2 with accents on slots 1 and 4 (Bonham-style
// kick figure on the same sextuplet grid played on the snare).
groove "sextuplet beat":
    HH: 1, 2{sextuplet 1 accent, 2, 3, 4 accent, 5, 6}, 3, 4
    SN: 2, 4
    BD: 1, 3

// Two 16th-note triplets back-to-back filling beat 3.
groove "16th triplet":
    HH: 1, 2, 3{triplet/8 1, 2, 3}, 3&{triplet/8 1, 2, 3}, 4
    SN: 2, 4
    BD: 1, 3

// Quintuplet on beat 1 — 5 hits in the time of a quarter, all on hi-hat.
groove "quintuplet":
    HH: 1{quintuplet 1, 2, 3, 4, 5}, 2, 3, 4
    SN: 2, 4
    BD: 1, 3

// Septuplet on beat 4 — 7 hits in the time of a quarter (jazz fill style).
groove "septuplet":
    HH: 1, 2, 3, 4{septuplet 1, 2, 3, 4, 5, 6, 7}
    SN: 2
    BD: 1, 3

// Nonuplet on beat 1 — 9 hits in the time of two 8ths (an eighth's worth
// of nine 32nd-note divisions).
groove "nonuplet":
    HH: 1{nonuplet 1, 2, 3, 4, 5, 6, 7, 8, 9}, 2, 3, 4
    SN: 2, 4
    BD: 1, 3

// Star shorthand: hi-hat sextuplets on every beat with a typical money-beat
// kick / snare pattern underneath.
groove "sextuplet star":
    HH: *sextuplet
    SN: 2, 4
    BD: 1, 3

// Tom-tour sextuplet fill written in count+notes form.
fill "tom run":
    count: "1 2{sextuplet 1, 2, 3, 4, 5, 6} 3 4"
    notes: "BD HT MT FT BD HT MT BD (BD CR)"

section "sextuplet on 2":
    bars: 1
    groove: "sextuplet beat"

section "16th-note triplets":
    bars: 1
    groove: "16th triplet"

section "quintuplet":
    bars: 1
    groove: "quintuplet"

section "septuplet":
    bars: 1
    groove: "septuplet"

section "nonuplet":
    bars: 1
    groove: "nonuplet"

section "sextuplet star":
    bars: 2
    groove: "sextuplet star"

section "tom-run fill":
    bars: 2
    groove: "sextuplet beat"
    fill "tom run" at bar 2
