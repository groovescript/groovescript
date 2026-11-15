# Spec: Timed lyrics

Status: implemented (slices 1–4, 2026-10-18; slice 5, 2026-11-15).
User docs: [DSL reference → Timed lyrics](DSL_REFERENCE.md#timed-lyrics).

## Goal

A drummer who also sings needs to see exactly when each syllable lands
against the drum part. GrooveScript should let the chart author pin
syllables to beat positions, using the same beat vocabulary as drum
patterns, and engrave them so the timing can be read at a glance.

## Why `cue` / `text` aren't enough

| Problem with `cue "…" at bar N beat X` | Effect |
|---|---|
| One statement per syllable | A 4-bar vocal line takes about 20 lines of `cue` |
| Rendered as `\markup` attached to a drum note token | Placement is approximate, and a syllable on an offbeat with no drum hit has nothing to anchor to |
| Free italic text above the staff | Collides with cymbal stems, rehearsal marks and fill placeholders; no hyphenation |
| No relationship between syllables | Can't hyphenate, can't validate, can't export to MIDI/MusicXML as lyrics |
| No rhythm of its own | The singer infers rhythm from the drum part |

Cues stay as they are, for section labels like "vocals enter". Lyrics
become a separate feature with first-class timing.

## Decisions taken

1. **Rendering: both styles, switchable.** One style is a dedicated vocal
   rhythm staff, the other is a lyrics line under the drum staff (see
   Rendering).
2. **Authoring: count + words pairs.** This mirrors the fill/groove
   `count:` + `notes:` form.
3. **Scope: onsets only.** There is no pitch, explicit duration, breath
   mark or harmony part in v1 (slice 5 later added holds, stops, breaths
   and backing parts; there is still no pitch). Durations may follow later, and the syntax
   reserves room for them.
4. **Ownership: lyrics belong to the section.** They inherit through
   `like` only when opted in via a new `with lyrics` category, and bars
   that carry lyrics never compact into repeats.

## Syntax

```
section "verse":
  bars: 8
  groove: "money beat"
  lyrics:
    bar 1: "1 2& 3 4&"  "When the mor- ning"
    bar 2: "1 3"        "comes a-"
    bar 3: "1"          "round"
    bar 5: "2 2& 3e 4"  "I can feel it"
```

- `lyrics:` is a section-level block. Each entry is
  `bar N: "<count>" "<words>"`.
- **Count string**: it uses the same tokenizer as fill counts
  (`parser_notation._parse_count_tokens`), so every beat label works
  (`1`, `2&`, `3e`, `4a`, `trip`, `let`), and so do inline whole-beat
  tuplet groups (`2{triplet 1, 2, 3}`). Positions are relative to bar
  N's meter, which also covers meter-variation bars.
- **Words string**: whitespace-separated syllable tokens, matched to
  count onsets by position.
  - A token ending in `-` hyphenates into the next syllable, which may be
    in a later bar. It engraves as a LilyPond `--` hyphen and as
    `syllabic` begin/middle/end in MusicXML.
  - `~` inside a token joins words on one onset (`oh~yeah` → "oh yeah").
  - `_` was reserved in v1 and became the hold mark in slice 5 (below).
- Column alignment between the two strings is encouraged but not
  required, in the same spirit as the existing `count`/`notes` pairs.
- **Pickups**: `bar 0:` means "the bar before this section". Vocal lines
  often start on the 4& before the downbeat. Writing the pickup in the
  section it belongs to keeps it with that section's words, and
  `like … with lyrics` reuses it correctly. The syllables are engraved in
  the previous section's last bar, using that bar's meter.

  ```
  section "chorus":
    lyrics:
      bar 0: "4&"     "And"
      bar 1: "1 2 3"  "here we go"
  ```

### Validation (all `GrooveScriptError`, Rust-style diagnostics)

- Token count ≠ onset count: the error points at both strings and reports
  the two counts.
- A beat label outside bar N's meter.
- Duplicate onsets within a bar.
- `bar N` beyond the section's expanded length (this includes `play:`
  sections and `repeat:`).
- A bar listed twice in one `lyrics:` block.
- `_` inside a word (slice 5: it must stand alone as the hold mark).
- `bar 0:` on the song's first section, since there is no preceding bar.
- A `bar 0:` onset that collides with an onset the previous section
  already puts in its last bar.

Lyrics may sit on placeholder bars. The singer still needs the words
when the groove is TBD, which matches how fills and cues already overlay
placeholders. Lyric onsets **do not** affect the drum bar's inferred
subdivision.

### Inheritance

- `like "verse"` does **not** copy lyrics, because a second verse almost
  always has different words.
- `like "verse" with lyrics` copies them. It combines with the other
  categories (`with fills, lyrics`).
- Merge rule: when the inheritor has its own `lyrics:` block, its
  `bar N:` entries **replace** the parent's entry for the same bar, and
  the parent's other bars are kept. This keyed-by-bar override is
  needed because concatenating lists would trip the duplicate-onset
  check. This is the one exception to "list fields concatenate".

## IR

```python
@dataclass
class LyricSyllable:
    position: Fraction      # beat position within the bar, like Event
    text: str               # "~" already turned into a space
    hyphen_after: bool

IRBar.lyrics: list[LyricSyllable]   # sorted by position; empty by default
IRSong.has_lyrics: bool             # drives emitter layout decisions
```

The compiler resolves section lyrics onto absolute bars after
inheritance and `play:` expansion, the same way as the existing cue
resolution (`_resolve_inheritance`, `compile_song`).

## Rendering (LilyPond)

Style is chosen by precedence: CLI flag, then metadata, then the default.

- Metadata: `lyrics_style: staff | line`
- CLI: `compile … --lyrics-style {staff,line,off}`. `off` prints a
  drums-only chart from the same source.
- Default: `staff` (confirmed).

Both styles build a hidden rhythm from the onsets. **Implied duration**:
each syllable lasts until the next onset, or to the bar line if it is the
last one in the bar. Gaps before the first onset become rests (staff) or
skips (line). This is a display convention, not a claim about how long the
note is held. Duration support will replace it later. Bars without lyrics
get a full-bar rest or skip. Durations are cut with the existing
`_slot_run_to_lily_durations` on a per-bar lyric grid. That grid is the
LCM of onset needs and is independent of the drum grid, in the same way
fill bars are.

### `staff` style

- A `RhythmicStaff` (one line) **above** the DrumStaff, slightly smaller,
  labelled "Vox". The syllables are engraved under it with
  `\new Lyrics \lyricsto`.
- `\RemoveAllEmptyStaves` on the vocal staff, so instrumental-only
  systems don't waste a line.
- Both staves sit in one `<< >>` with a shared timeline, so bar lines and
  horizontal spacing line up. This needs a template change: a
  `{{VOCAL_STAFF}}` placeholder in `lilypond_template.ly` next to the
  existing `\new DrumStaff`.

### `line` style

- A `NullVoice` inside the DrumStaff carries the implied rhythm, and a
  `Lyrics` context `\lyricsto` that voice sits **below** the drum staff.
  NullVoice affects horizontal spacing but prints nothing, so an offbeat
  syllable gets a real column even when no drum note is there.

### Compaction and repeats

- Any bar with lyrics is ineligible for implicit compaction and for
  `repeat:`/percent-repeat grouping. This matches the current rule for
  `bar.cues` in `lilypond.py`, so `has_annotations` gains
  `or bar.lyrics`.
- A section with `repeat:` that has lyrics in only some passes is still
  written out in full for the passes that carry lyrics.

## Other outputs

- **MIDI**: one lyric meta event (`FF 05`) per syllable at its tick, on a
  dedicated "Lyrics" track. A trailing hyphen is kept in the text, which
  is the karaoke convention. This is cheap, and lyrics then show up in
  DAWs.
- **MusicXML**: a separate "Voice" part made of unpitched/slash notes
  that use the implied durations, each carrying `<lyric>` with
  `<syllabic>`. Lyrics can't be attached to drum notes, because the onset
  often has no drum note. `--lyrics-style` doesn't apply here; use `off`
  to suppress the part.
- **lint `--style`**: warns about a trailing hyphen on the last syllable
  of a section, and about `cue` text that looks like lyrics (more than 3
  cues in one section placed at beats). The second is a migration nudge.

## Tooling and docs

- Vim syntax: add the `lyrics` keyword and `lyrics_style` metadata key.
- `README.md` and `docs/DSL_REFERENCE.md`: add a "Timed lyrics" section
  and point the "Vocal cues" section at it.
- `CLAUDE.md`: add a design-constraint bullet covering the onsets-only
  model, the implied-duration convention, `with lyrics`, and the
  compaction rule.
- The change is additive, so `CURRENT_DSL_VERSION` stays the same.

## Delivery (thin slices)

1. **Parse → IR → line style.** Grammar, AST (`Section.lyrics`),
   validation, IR, NullVoice + Lyrics emission, and the compaction rule.
   Fixture: `tests/fixtures/lyrics_basic.gs` (.ly/.pdf).
2. **Staff style + switch.** RhythmicStaff, the template placeholder,
   `lyrics_style` metadata, `--lyrics-style` flag, and
   `\RemoveAllEmptyStaves`. Fixture: `lyrics_staff.gs`.
3. **Inheritance + pickups.** `with lyrics`, the per-bar override rule,
   `bar 0:` pickups, and play:/placeholder/meter-variation coverage.
4. **Exports + lint.** MIDI lyric events, the MusicXML vocal part, and the
   lint warnings.
5. **Holds, multi-bar entries, breaths, backing vocals** (done).
   Fixtures: `lyrics_holds_and_parts.gs` (staff) and
   `lyrics_holds_and_parts_line.gs` (line).

## Slice 5 design

**Marks.** Three tokens stand alone in the words string and take an onset
like a syllable, so the count and words still pair one to one:

- `_` (hold): the sounding syllable continues through the onset. No new
  syllable; the rhythm ties into the onset and the held syllable gets an
  extender (`__` in LilyPond, `<extend>` in MusicXML). On beat 1 it
  continues the previous bar's last syllable, so words ring over bar
  lines. Must follow something sounding: the previous onset in the bar,
  or the previous bar's last syllable/hold when on beat 1.
- `.` (stop): the sounding syllable ends; a rest until the next onset.
  Must follow a syllable or hold in the same bar (a syllable already ends
  at the bar line, so a stop that opens a bar would mean nothing).
- `,` (breath): ends the syllable like `.` and prints a breath mark
  (`\breathe` on the staff; a breath glyph after the syllable in `line`
  style, where the rhythm voice prints nothing; `<breath-mark>` on the
  note that stops in MusicXML). Allowed anywhere.

Marks sing nothing, so MIDI emits no lyric event for them. The implied
duration rule is unchanged: every onset (syllable, hold or mark) ends the
previous span. IR: `LyricSyllable.kind` (`syllable`/`hold`/`stop`/
`breath`), validated in sung order by `_validate_lyric_flow`.

**Multi-bar entries.** `bars N-M: "c1 | c2 | …" "words"`: the count
splits on `|` into exactly M−N+1 parts (an empty part is a bar with no
lyrics) and the words are dealt out in order. The parser expands the
entry into one `LyricLine` per bar, so everything downstream (duplicate
bars, pickups, inheritance) works unchanged.

**Backing vocals.** `lyrics "<name>":` opens a named part; the unnamed
block is the lead. `LyricLine.part` carries the name. Each part is a
separate stream: `IRBar.lyrics` stays the lead and
`IRBar.vocal_parts[name]` holds the others; `IRSong.lyric_parts` lists
them lead first, then in order of appearance. Duplicate-bar checks,
pickups, flow validation and `like … with lyrics` (keyed by part and bar)
all apply per part. Staff style adds a labelled RhythmicStaff per part;
line style adds a NullVoice and a Lyrics line per part (italic, with a
`stanza` label); MIDI adds a "Lyrics: <name>" track; MusicXML adds a part
named after it. A bar with lyrics in *any* part never compacts.

## Open questions

None at present.
