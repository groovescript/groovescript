title: "Variations and Inheritance"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "two bar":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 2&, 4
      SN: 2, 4
      HH: *8

fill "bar 4 fill":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "bar 4 fill" at bar 4 beat 3

section "verse":
  bars: 8
  groove: "two bar"

section "chorus":
  bars: 8
  groove: "money beat"
  variation "chorus lift" at bar 8:
    replace HH with CR at 1
    add SN ghost at 2&
    replace SN with SN accent at 4

section "verse 2":
  like "verse"
