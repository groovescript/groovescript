title: "Break Directive Showcase"
tempo: 112
time_signature: 4/4

// Demonstrates the ``break on bar N …`` directive in all its forms.
//
// ``through``: inclusive end boundary — the named beat/bar IS silenced.
// ``until``:   exclusive end boundary — the named beat/bar is NOT silenced.
// No end clause: break runs to the end of the section.

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

// ── No end clause: break runs to end of section ───────────────────────────

// Bar 3 and bar 4 are empty rests. Bars 1 and 2 play normally.
section "break from bar (no through)":
  bars: 4
  groove: "money beat"
  break on bar 3

// Bar 2 plays beats 1-2 only; beats 3-4 rest. Bars 3-4 fully silent.
section "break from beat (no through)":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3

// ── ``through``: inclusive end ────────────────────────────────────────────

// Bar 2 plays beats 1-2 then rests. Bar 3 fully silent. Bars 1 and 4 normal.
section "through: explicit end bar":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3 through bar 3

// Bar 2 rests from beat 3. Bar 3 rests beats 1-2 (beat 2 = position 1/4
// is silenced), then resumes on beat 3. Bars 1 and 4 normal.
// Beat 2& in bar 3 survives because ``through beat 2`` stops at position 1/4.
section "through: bounded end beat":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3 through bar 3 beat 2

// ── ``until``: exclusive end ──────────────────────────────────────────────

// ``until bar 3`` = bar 3 is the first bar that plays. Bars 1-2 silent.
section "until: exclusive end bar":
  bars: 4
  groove: "money beat"
  break on bar 1 until bar 3

// Bar 2 rests from beat 3. Bar 3 rests everything before beat 3 (so beat 2&
// IS silenced, unlike the ``through beat 2`` version above). Beat 3 onward
// in bar 3 plays. Bars 1 and 4 normal.
section "until: exclusive end beat":
  bars: 4
  groove: "money beat"
  break on bar 2 beat 3 until bar 3 beat 3

// ── through vs until side-by-side ─────────────────────────────────────────
// Both break from beat 3 of bar 1. ``through beat 2`` leaves 2& sounding;
// ``until beat 3`` silences 2& (because 2& < beat 3).

section "through beat 2 (2& survives)":
  bars: 2
  groove: "driving 16ths"
  break on bar 1 beat 3 through bar 1 beat 2

section "until beat 3 (2& silenced)":
  bars: 2
  groove: "driving 16ths"
  break on bar 1 beat 3 until bar 1 beat 3

// ── Longer break on denser groove ─────────────────────────────────────────
// 8-bar section. ``until bar 5 beat 3`` silences bar 3 from beat 3, all of
// bar 4, and bar 5 through beat 2& (everything before beat 3). Beat 3 of
// bar 5 is the first note that sounds again.
section "long break (until)":
  bars: 8
  groove: "driving 16ths"
  break on bar 3 beat 3 until bar 5 beat 3
