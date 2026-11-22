# GrooveScript

A Python CLI that compiles GrooveScript (`.gs`) drum notation files into
[LilyPond](https://lilypond.org/) source, then renders them to print-ready
PDF sheet music.

GrooveScript is a text-based DSL optimized for fast transcription of drum
charts: reusable grooves and fills, section-based song structure,
time-anchored variations, and placeholder grooves and fills for
incremental chart-building.

## Core concepts

- **Sections** — the top-level song-structure units (intro, verse, chorus, bridge, …). Each section declares how many bars it runs, which groove it uses, and any fills or variations that occur inside it.
- **Grooves** — named, reusable drum patterns that repeat for the duration of a section. Define once, reference everywhere.
- **Fills** — short departures from the groove, placed at a specific bar and beat within a section (e.g., a bar-4 snare roll before the chorus).
- **Variations** — time-anchored tweaks applied on top of the groove at a particular bar: add, remove, replace, or re-articulate individual notes (or substitute the whole bar) without rewriting the groove.
- **Cues and lyrics** — annotations for the reader: text cues ("vocals in", "guitar solo") at a bar/beat, and timed lyrics pinned to exact beat positions for drummers who sing.

## Minimal chart

The smallest useful chart you can write — just a title, a tempo, and the
form as a list of sections with bar counts. Every section renders as a
placeholder groove (empty bars with a "Section groove" label), so you
can print the form out and pencil the groove in later. `fill at bar N`
(no body) marks a fill slot without committing to the notes:

```groovescript
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
```

From here, iterate: the [tutorial](docs/TUTORIAL.md) starts from a chart
like this one and walks through filling in grooves, swapping placeholder
fills for real ones, adding variations, and placing cues.

Transcribed and placeholder grooves can be mixed within one section;
see the [Placeholder grooves](docs/DSL_REFERENCE.md#placeholder-grooves)
reference for the full set of forms.

## Quick taste

```groovescript
title: "Simple Rock"
tempo: 120

groove "money beat":
  kick:  1, 3
  snare: 2, 4
  hihat: *8

fill "bar 4 fill":
  count "3 e & a 4":
    3:  snare
    3e: snare
    3&: snare
    3a: snare
    4:  kick, crash

section "intro":
  bars: 4
  groove: "money beat"
  fill "bar 4 fill" at bar 4 beat 3

section "chorus":
  bars: 8
  groove: "money beat"
```

See [`DSL_REFERENCE.md`](docs/DSL_REFERENCE.md) for the full language,
and [Documentation](#documentation) for worked examples.

## Get started

**No terminal? No problem.** Write charts in the browser and render them to PDF from your phone:

1. **[Open the web editor →](https://groovescript.github.io/groovescript/)** — write `.gs` files with syntax highlighting, live error checking, a score preview and playback; no install required
2. **[Use the charts template →](https://github.com/groovescript/charts-template)** — one click to create a private GitHub repo that automatically renders every chart you commit to a PDF

The template repo includes step-by-step instructions for the full iPhone workflow.

**Prefer working locally?** Install the CLI (below) and follow
[`GETTING_STARTED.md`](docs/GETTING_STARTED.md).

## Documentation

| Doc | Read it when… |
|---|---|
| [`GETTING_STARTED.md`](docs/GETTING_STARTED.md) | You want to install GrooveScript and render your first chart. |
| [`TUTORIAL.md`](docs/TUTORIAL.md) | You want a guided walkthrough that builds up a multi-section chart step by step (form, grooves, fills, variations, cues). |
| [`DSL_REFERENCE.md`](docs/DSL_REFERENCE.md) | You're writing a chart and need the exact syntax or rules for a feature. Topic-indexed; the one to search. |
| [`editors/vim/`](editors/vim/README.md) | You want syntax highlighting in Vim / Neovim. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | You're changing GrooveScript itself (tests, fixtures, source layout). |
| [`LYRICS_SPEC.md`](docs/LYRICS_SPEC.md) | You want the design rationale behind timed lyrics (a design spec, not user docs). |

Worked examples — tuplet groups, mixed subdivisions, meter changes,
dynamic spans, swing feel, timed lyrics and more — live under
[`tests/fixtures/`](tests/fixtures/), each `.gs` committed with its
compiled `.ly` and rendered `.pdf`. Starter charts live under
[`templates/`](templates/).

See [GitHub Issues](https://github.com/groovescript/groovescript/issues) for bugs and roadmap.

## Installation

```bash
./setup.sh
```

This installs `uv`, `lilypond` (via `brew` on macOS or `apt` on Linux), and
Python dependencies in one shot. See
[`GETTING_STARTED.md`](docs/GETTING_STARTED.md) for the manual steps.

## Usage

### Wrapper scripts

Charts live in the `charts/` directory. Two wrapper scripts in the repo
root handle the common workflow:

```bash
# Create charts/my-song.gs from a template (default: rock)
./scaffold-chart my-song
./scaffold-chart -t funk my-song    # pick another template; -h lists them

# Compile charts/my-song.gs → charts/my-song.ly → charts/my-song.pdf
./build-pdf my-song
./build-pdf -v my-song              # show each step
```

### Command-line interface

The wrappers call the `groovescript` CLI, which you can also run directly:

```bash
# .gs → LilyPond (render to PDF with: lilypond -o output output.ly)
uv run groovescript compile input.gs -o output.ly

# Parse + compile check only, no output. --style adds stylistic warnings
# (unused grooves/fills, mixed groove styles, dangling `like` refs, …)
uv run groovescript lint input.gs
uv run groovescript lint --style input.gs

# Export to MIDI (GM drums on channel 10)
uv run groovescript midi input.gs -o output.mid

# Export to MusicXML (experimental — less tested than LilyPond output)
uv run groovescript musicxml input.gs -o output.xml

# Rewrite files in the canonical layout (see below)
uv run groovescript fmt song.gs other.gs
uv run groovescript fmt --check *.gs      # exit 1 if any file needs formatting
uv run groovescript fmt --diff song.gs    # show what would change
```

Every subcommand except `fmt` accepts `--watch` to re-run on each save until Ctrl-C.
`compile` also takes:

- `--no-compact` — by default, runs of identical bars collapse into one
  repeat block (12 identical bars print as "Play 12x" rather than three
  "Play 4x" blocks). Section boundaries, fills, variations, cues, bar text,
  dynamic spans and time-signature changes still break a run.
  `--no-compact` keeps the implicit 4-bar phrase chunking instead.
- `--lyrics-style staff|line|off` — how [timed lyrics](docs/DSL_REFERENCE.md#timed-lyrics)
  are engraved: a small vocal rhythm staff above the drums (`staff`, the
  default), a lyrics line under the drums (`line`), or left out (`off`).
  Overrides the chart's `lyrics_style:` metadata. `musicxml` accepts
  `--lyrics-style off` to drop the vocal part.

### Formatting (`fmt`)

`groovescript fmt` rewrites a chart's layout without touching its meaning:
two-space indentation by nesting level (worked out from the structure, not
the old indentation), single spaces around `:` and `,`, the values of
consecutive pattern lines aligned in one column, and at most one blank line
in a row, with one above each groove, fill and section. Comments, strings,
and your choice of commas or spaces in beat lists are kept. Before writing
anything it compiles the chart both ways and refuses if the PDF, MIDI or
MusicXML output would differ, so formatting is always safe. It only formats
charts that compile; fix any errors first. `-` reads stdin and writes
stdout, for editor integrations.

## Web editor

**[Open the Web Editor →](https://groovescript.github.io/groovescript/)**
Write and edit `.gs` files in the browser, then copy or share them into
your version-control workflow. No installation required.

The editor runs the real GrooveScript compiler in your browser (via
[Pyodide](https://pyodide.org/)), so as you type you get:

- **Errors and warnings in place** — the same diagnostics as
  `groovescript lint --style`, underlined in the text, with a problems bar
  at the bottom (tap it to jump to the next one).
- **A live score preview** — the chart engraved from its MusicXML export
  with [Verovio](https://www.verovio.org/). It sits beside the editor on
  wide screens; on a phone, tap **Preview** / **Edit** to switch. The PDF
  from LilyPond remains the reference rendering; the preview is for
  proofreading as you go, so spacing and some symbols differ.
- **Completion and hover** — suggestions as you type: groove, fill,
  section and variation names inside quotes (the chart's own first, then
  the built-in library), keywords and snippets at the start of a line
  (`section`, `fill at bar`, `rit from bar … to bar …`, …), instruments,
  and modifiers after a beat. Ctrl-Space opens the list anywhere. Hover a
  name to see its definition, an instrument for its aliases, or a
  modifier or keyword for a one-line explanation; Ctrl/⌘-click or F12
  jumps to where a groove, fill or section is defined.
- **Format** — tidies the layout exactly like `groovescript fmt`
  (also Shift+Alt+F); undo reverts it in one step.
- **Playback** — **▶ Play** (or Ctrl/⌘+Enter) plays the chart's MIDI on a
  built-in synthesized kit, highlighting each note as it sounds. Tap any
  bar in the score to play from there. Edits made during playback are
  picked up without stopping.
- **Downloads** — the chart's `.mid` and `.musicxml` exports.

The first visit downloads the compiler runtime (about 6 MB) and the score
engraver (about 2 MB). After that the editor works **offline**: compiling,
the preview, playback and formatting all run from the cached copy, and the
latest version loads automatically whenever you're online. On a phone, use
**Add to Home Screen** (Safari) or **Install app** (Chrome) to open it like
an app. Editing still works even if the compiler can't load.

To work on the editor itself, see [Development](#development).

## Editor integration

A Vim / Neovim syntax-highlighting plugin lives in
[`editors/vim/`](editors/vim/README.md). The README there covers
installation on macOS via Homebrew Vim/MacVim/Neovim, using vim-plug or
Vim's native package loader.

## Security

**Only compile `.gs` files you trust.**

GrooveScript compiles source files on your local machine and passes the
generated LilyPond output to the `lilypond` binary for rendering. A malicious
`.gs` file could embed arbitrary content in the generated `.ly` file; depending
on your LilyPond version and configuration, that content may be able to read or
write files on your system. Never compile `.gs` files received from untrusted
sources without inspecting them first.

## Development

```bash
# Run the test suite
uv run pytest

# Compile a fixture and render it end-to-end
uv run groovescript compile tests/fixtures/full_song_example.gs \
  -o tests/fixtures/full_song_example.ly
lilypond -o tests/fixtures/full_song_example tests/fixtures/full_song_example.ly

# Cut a release (patch by default; --minor / --major also supported).
# Bumps pyproject.toml, commits, pushes, tags vX.Y.Z, creates a GitHub release.
./release
./release --help     # full flag list (--title, --notes, --notes-file, --dry-run)

# Where main can't be pushed to directly (it is protected) or tags can't be
# pushed, e.g. a Claude Code cloud session, release through a PR instead:
./release --pr       # bump on release/vX.Y.Z and open a "Bump version" PR
# Merging that PR runs the Release workflow (.github/workflows/release.yml),
# which creates the tag and the GitHub release. To do that step by hand
# (cloud sessions can't create releases), run on an up-to-date main:
./release --publish
```

To work on the web editor locally:

```bash
cd editors/web
npm ci                                                 # also fetches Pyodide + Verovio
uv run python scripts/build_py_bundle.py               # bundle src/groovescript for the browser
python3 -m http.server 8000                            # then open http://localhost:8000/?local-deps
npm test
```

`?local-deps` loads Pyodide and Verovio from `node_modules/` instead of
the jsDelivr CDN. The compiler bundle (`editors/web/py/`) is generated,
not committed; the Pages deploy builds it from `src/` every time.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the source layout, the
fixture workflow and the checklist to follow after each change.
