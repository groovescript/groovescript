// Timed lyrics, `line` style: syllables sit on a lyrics line under the
// drum staff, aligned to a hidden rhythm (each syllable lasts until the
// next onset).
metadata:
  title: "Lyrics Basic"
  tempo: 96
  lyrics_style: line

groove "money beat":
  BD: 1 3
  SN: 2 4
  HH: *8

section "verse":
  bars: 8
  groove: "money beat"
  lyrics:
    bar 1: "1 2& 3 4&"  "When the mor- ning"
    bar 2: "1 3"        "comes a-"
    bar 3: "1"          "round"
    bar 5: "2 2& 3e 4"  "I can feel it"
    bar 6: "1 3"        "oh~yeah oh"
