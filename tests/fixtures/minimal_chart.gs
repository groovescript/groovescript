// Minimal chart — the smallest useful chart you can write: just a title, a
// tempo, and sections with bar counts. Every section renders as a placeholder
// groove (empty bars + "Section groove" label). ``fill at bar N`` (no body)
// marks a fill without committing to the notes yet.

title: "Minimal Chart"
tempo: 120

section "intro":
  bars: 4

section "verse":
  bars: 8
  fill at bar 8

section "chorus":
  bars: 8
  fill at bar 4
  fill at bar 8

section "outro":
  bars: 4
