title: "Dynamics Test"
tempo: 120
dsl_version: 1

groove "verse groove":
        HH: *8
        BD: 1, 3
        SN: 2, 4

groove "chorus groove":
        HH: *8
        BD: 1, 2&, 3, 4&
        SN: 2, 4
        CR: 1

fill "chorus fill":
    count "3 e & a 4":
        3:  SN
        3e: SN
        3&: SN
        3a: SN
        4:  BD, CR

section "verse":
    bars: 4
    groove: "verse groove"
    # 2-bar crescendo leading into the chorus (bars 3-4)
    crescendo from bar 3 to bar 4

section "chorus":
    bars: 8
    groove: "chorus groove"
    fill "chorus fill" at bar 8 beat 3
    # partial-bar crescendo on beat 3 of bar 4, ending on beat 1 of bar 5
    cresc from bar 4 beat 3 to bar 5 beat 1
    # 1-bar decrescendo on the last bar before the outro (shorthand form)
    decrescendo bar 7

section "outro":
    bars: 4
    groove: "verse groove"
    # partial-bar decrescendo: beat 3 to end of bar 4
    decresc from bar 3 beat 3 to bar 4
    # inline fill with its own crescendo
    fill at bar 4:
        count "1 e & a 2 e & a 3 e & a 4 e & a":
            1: SN
            1e: SN
            1&: SN
            1a: SN
            2: SN
            2e: SN
            2&: SN
            2a: SN
            3: SN
            3e: SN
            3&: SN
            3a: SN
            4: BD, CR
        cresc from bar 1 to bar 1
