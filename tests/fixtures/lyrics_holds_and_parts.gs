title: "Lyrics: Holds and Parts"
tempo: 96

groove "verse":
  BD: 1, 3&
  SN: 2, 4
  HH: *8

# Holds (_), stops (.), breaths (,), a multi-bar entry, and a backing-vocal
# line that answers the lead.
section "verse":
  bars: 4
  groove: "verse"
  lyrics:
    bar 1:    "1 2& 3 4"       "When the night falls"
    bar 2:    "1 2 3"          "_ , down"
    bars 3-4: "1 2& 3 | 1 3 4" "I can feel it _ ."
  lyrics "BGV":
    bar 2: "3 4"   "ooh _"
    bar 4: "1 2 3" "ah _ ,"

section "chorus":
  bars: 4
  groove: "verse"
  crash in
  lyrics:
    bar 0:    "4&"      "And"
    bar 1:    "1 2 3"   "here we go"
    bar 2:    "1"       "_"
    bars 3-4: "1 3 | 1" "hold on _"
