// Timed lyrics, `staff` style (the default): a small "Vox" rhythm staff
// above the drums carries the syllables. Covers pickups (`bar 0:`),
// `like ... with lyrics` with per-bar overrides, tuplet onsets, a
// `repeat:` section written out because of its words, a placeholder
// groove, and a meter-variation bar.
metadata:
  title: "Lyrics Staff"
  tempo: 120

groove "money beat":
  BD: 1 3
  SN: 2 4
  HH: *8

section "intro":
  bars: 4
  groove: "money beat"

section "verse":
  bars: 4
  groove: "money beat"
  lyrics:
    bar 0: "4&"           "And"
    bar 1: "1 2& 3 4&"    "when the mor- ning"
    bar 2: "1 2{triplet 1, 2, 3} 4" "comes a- round a- gain"
    bar 3: "1 3"          "I can"
    bar 4: "1 1e 2trip 3" "feel it in my"

section "verse two":
  like "verse" with lyrics
  lyrics:
    bar 0: "4"            "So"
    bar 3: "1 2 3"        "we will go"

section "chorus":
  bars: 4
  groove: "money beat"
  repeat: 2
  lyrics:
    bar 1: "1 3"  "la la"
    bar 3: "1"    "hey"
  variation at bar 4:
    time_signature: 2/4
    add SN at 1 2

section "tag":
  bars: 2
  groove: placeholder
  lyrics:
    bar 2: "1 2 3 4" "one more time now"
