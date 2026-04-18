title: "Full Song Example"
tempo: 126
time_signature: 4/4

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

groove "driving verse":
    bar 1:
      BD: 1, 3
      SN: 2, 4
      HH: *8
    bar 2:
      BD: 1, 2&, 3, 4
      SN: 2, 4
      HH: *8

fill "turnaround":
  count "3 e & a 4":
    3: SN
    3e: SN
    3&: SN
    3a: SN
    4: BD, CR

section "intro":
  bars: 8
  groove: "money beat"
  fill "turnaround" at bar 8 beat 3

section "verse":
  bars: 16
  groove: "driving verse"
  repeat: 8
  fill "turnaround" at bar 16 beat 3

section "chorus":
  bars: 16
  groove: "money beat"
  variation "chorus lift" at bar 8:
    replace HH with CR at 1
    add SN ghost at 2&
    replace SN with SN accent at 4
  fill "turnaround" at bar 16 beat 3

section "verse 2":
  like "verse" with fills

section "chorus 2":
  like "chorus" with variations, fills

section "bridge":
  bars: 8
  groove: "driving verse"
  repeat: 2
  variation "bridge accent" at bar 4:
    add CR accent at 1
  fill "turnaround" at bar 8 beat 3

section "outro":
  bars: 8
  groove: "money beat"
  fill "turnaround" at bar 8 beat 3
