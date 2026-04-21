# GrooveScript

A Python CLI that compiles GrooveScript (`.gs`) drum notation files into
[LilyPond](https://lilypond.org/) source, then renders them to print-ready
PDF sheet music.

GrooveScript is a text-based DSL optimised for fast transcription of drum
charts: reusable grooves and fills, section-based song structure,
time-anchored variations, placeholder fills for incremental chart-building,
and full support for changing meters.

## Get started

**No terminal? No problem.** Write charts in the browser and render them to PDF from your phone:

1. **[Open the web editor →](https://groovescript.github.io/groovescript/)** — write `.gs` files with syntax highlighting, no install required
2. **[Use the charts template →](https://github.com/groovescript/charts-template)** — one click to create a private GitHub repo that automatically renders every chart you commit to a PDF

The template repo includes step-by-step instructions for the full iPhone workflow.

---

## Core concepts

- **Grooves** — named, reusable drum patterns that repeat for the duration of a section. Define once, reference everywhere.
- **Fills** — short departures from the groove, placed at a specific bar and beat within a section (e.g., a bar-4 snare roll before the chorus).
- **Variations** — time-anchored tweaks applied on top of the groove at a particular bar: add, remove, replace, or substitute individual notes without rewriting the whole pattern.
- **Sections** — the top-level song-structure units (intro, verse, chorus, bridge, …). Each section declares how many bars it runs, which groove it uses, and any fills or variations that occur inside it.

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

## Quick taste

```groovescript
title: "Simple Rock"
tempo: 120

groove "money beat":
  BD: 1, 3
  SN: 2, 4
  HH: *8

fill "bar 4 fill":
  count "3 e & a 4":
    3:  SN
    3e: SN
    3&: SN
    3a: SN
    4:  BD, CR

section "intro":
  bars: 4
  groove: "money beat"
  fill "bar 4 fill" at bar 4 beat 3

section "chorus":
  bars: 8
  groove: "money beat"
  variation "chorus lift" at bar 8:
    replace HH with CR at 1
    add SN ghost at 2&
    replace SN with SN accent at 4
  variation "open-hat-4&" at bar 4   // built-in library variation
```

Named variations can also be defined once at the top level and reused
across any number of sections and bars:

```groovescript
variation "crash-on-one":
  add CR at 1

section "chorus":
  bars: 8
  groove: "money beat"
  variation "crash-on-one" at bars 1, 5   // reuse the same variation twice

section "outro":
  bars: 4
  groove: "money beat"
  variation "crash-on-one" at bar 1       // …and again in another section
```

GrooveScript also ships a built-in variation library (e.g. `open-hat-4`,
`flam-backbeat`, `drop-kick`, `ride-instead`) — see
[`src/groovescript/variation_library.gs`](src/groovescript/variation_library.gs)
for the full catalogue. User-defined variations with the same name take
precedence over library entries.

More complete fixtures live under `tests/fixtures/`, each with its compiled
`.ly` and rendered `.pdf` committed alongside the `.gs` source.

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
