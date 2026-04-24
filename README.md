# GrooveScript

A Python CLI that compiles GrooveScript (`.gs`) drum notation files into
[LilyPond](https://lilypond.org/) source, then renders them to print-ready
PDF sheet music.

GrooveScript is a text-based DSL optimized for fast transcription of drum
charts: reusable grooves and fills, section-based song structure,
time-anchored variations, placeholder fills for incremental chart-building,
and full support for changing meters.

## Core concepts

- **Sections** — the top-level song-structure units (intro, verse, chorus, bridge, …). Each section declares how many bars it runs, which groove it uses, and any fills or variations that occur inside it.
- **Grooves** — named, reusable drum patterns that repeat for the duration of a section. Define once, reference everywhere.
- **Fills** — short departures from the groove, placed at a specific bar and beat within a section (e.g., a bar-4 snare roll before the chorus).
- **Variations** — time-anchored tweaks applied on top of the groove at a particular bar: add, remove, replace, or substitute individual notes without rewriting the whole pattern.

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

From here, iterate: fill in the grooves (step 2 of the tutorial), swap
placeholder fills for real ones (step 3), add variations (step 4), and
cues (step 5).

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

More complete fixtures live under `tests/fixtures/`, each with its compiled
`.ly` and rendered `.pdf` committed alongside the `.gs` source.

## Get started

**No terminal? No problem.** Write charts in the browser and render them to PDF from your phone:

1. **[Open the web editor →](https://groovescript.github.io/groovescript/)** — write `.gs` files with syntax highlighting, no install required
2. **[Use the charts template →](https://github.com/groovescript/charts-template)** — one click to create a private GitHub repo that automatically renders every chart you commit to a PDF

The template repo includes step-by-step instructions for the full iPhone workflow.

---

## Documentation

- **[`GETTING_STARTED.md`](docs/GETTING_STARTED.md)** — install GrooveScript and
  render your first chart.
- **[`TUTORIAL.md`](docs/TUTORIAL.md)** — guided walkthrough that builds up a
  multi-section chart step by step (metadata, form, grooves, placeholder
  fills, variations, real fills).
- **[`DSL_REFERENCE.md`](docs/DSL_REFERENCE.md)** — comprehensive, topic-indexed
  reference for every language feature. This is the one to search while
  you're writing a chart.

See [GitHub Issues](https://github.com/groovescript/groovescript/issues) for bugs and roadmap.

## Security

**Only compile `.gs` files you trust.**

GrooveScript compiles source files on your local machine and passes the
generated LilyPond output to the `lilypond` binary for rendering. A malicious
`.gs` file could embed arbitrary content in the generated `.ly` file; depending
on your LilyPond version and configuration, that content may be able to read or
write files on your system. Never compile `.gs` files received from untrusted
sources without inspecting them first.

## Installation

```bash
./setup.sh
```

This installs `uv`, `lilypond` (via `brew` on macOS or `apt` on Linux), and
Python dependencies in one shot. See
[`GETTING_STARTED.md`](docs/GETTING_STARTED.md) for the full walkthrough.

## Usage

Charts live in the `charts/` directory. Two wrapper scripts in the repo
root handle the common workflow:

```bash
# Create charts/my-song.gs from a template
./scaffold-chart my-song

# Compile charts/my-song.gs → charts/my-song.ly → charts/my-song.pdf
./build-pdf my-song
```

`./scaffold-chart -t <template>` picks a non-default starting template;
run `./scaffold-chart -h` to list available templates.

## Web editor

**[Open the Web Editor →](https://groovescript.github.io/groovescript/)**
Write and edit `.gs` files in the browser with syntax highlighting, then
copy or share to your version-control workflow. No installation required.

## Editor integration

A Vim / Neovim syntax-highlighting plugin lives in
[`editors/vim/`](editors/vim/README.md). The README there covers
installation on macOS via Homebrew Vim/MacVim/Neovim, using vim-plug or
Vim's native package loader.

## Development

```bash
# Run the test suite
uv run pytest

# Compile a fixture and render it end-to-end
uv run groovescript compile tests/fixtures/full_song_example.gs \
  -o tests/fixtures/full_song_example.ly
lilypond -o tests/fixtures/full_song_example tests/fixtures/full_song_example.ly

# Compile with --compact to collapse long runs of identical bars into a
# single repeat block (e.g. 12 identical bars become "Play 12x" rather than
# three "Play 4x" blocks). Section boundaries, fills, variations, cues,
# bar text, dynamic spans, and time-signature changes are still respected.
uv run groovescript compile input.gs -o output.ly --compact

# Lint a .gs file (parse + compile check, no LilyPond output)
uv run groovescript lint input.gs

# Export a .gs file to MIDI
uv run groovescript midi input.gs -o output.mid

# Export a .gs file to MusicXML (experimental — less tested than LilyPond output)
uv run groovescript musicxml input.gs -o output.xml
```

Source layout:

```
src/groovescript/
  cli.py              # argparse entry point (compile, lint, midi, musicxml, --watch)
  parser.py           # Lark grammar → AST (via Transformer)
  ast_nodes.py        # AST dataclasses
  compiler.py         # AST → IR (flat event list per bar)
  lilypond.py         # IR → LilyPond source
  midi.py             # IR → MIDI file bytes (Format 1, GM drums on channel 10)
  musicxml.py         # IR → MusicXML
  lint.py             # Style checker used by `lint --style`
  grammar.lark        # Lark EBNF grammar
  groove_library.gs     # Built-in groove library
  fill_library.gs       # Built-in fill library
  variation_library.gs  # Built-in variation library
  library.py            # Loader for groove / fill / variation libraries
  lilypond_template.ly  # Static LilyPond boilerplate
tests/
  fixtures/           # .gs / .ly / .pdf reference files
```
