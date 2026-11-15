# Contributing to GrooveScript

## Running the tests

```bash
uv run pytest
```

## How the compiler is organised

```
.gs source → parser (Lark LALR) → AST → compiler → IR (IRSong → IRBar[]) → emitters
                                                                       ├─ lilypond.py → .ly → lilypond → .pdf
                                                                       ├─ midi.py     → .mid
                                                                       └─ musicxml.py → .xml
```

```
src/groovescript/
  cli.py                 # argparse entry point (compile, lint, midi, musicxml, fmt, --watch)
  parser.py              # Public parse entry point; CURRENT_DSL_VERSION lives here
  parser_preprocess.py   # Source rewrites that run before Lark (optional commas, quoting)
  parser_transformer.py  # Lark Transformer: parse tree → AST
  parser_notation.py     # Instrument / beat-label / count / notes token parsing
  parser_errors.py       # Lark exceptions → GrooveScriptError diagnostics
  grammar.lark           # Lark EBNF grammar
  ast_nodes.py           # AST dataclasses
  compiler.py            # AST → IR (flat event list per bar)
  lilypond.py            # IR → LilyPond source
  lilypond_template.ly   # Static LilyPond boilerplate
  midi.py                # IR → MIDI file bytes (Format 1, GM drums on channel 10)
  musicxml.py            # IR → MusicXML
  lyrics.py              # Implied-duration rhythm for timed lyrics (shared by emitters)
  lint.py                # Style checker used by `lint --style`
  fmt.py                 # `fmt`: canonical layout, verified against compiled output
  errors.py              # GrooveScriptError and Rust-style diagnostic rendering
  web.py                 # Browser entry point used by the web editor (never raises)
  library.py             # Loader for the built-in libraries below
  groove_library.gs      # Built-in groove library
  fill_library.gs        # Built-in fill library
  variation_library.gs   # Built-in variation library
editors/
  vim/                   # Vim / Neovim syntax plugin
  web/                   # Browser editor (CodeMirror + Pyodide + Verovio)
tests/
  fixtures/              # .gs / .ly / .pdf reference files
templates/               # Starter charts used by ./scaffold-chart
docs/                    # User documentation and design specs
```

[`CLAUDE.md`](CLAUDE.md) lists the design constraints the compiler must
not violate (Fraction beat positions, inferred per-bar subdivision,
instrument mutex groups, …). Read it before changing the compiler.

## Checklist after each change

After any change that affects compiled output:

1. Run the test suite: `uv run pytest`
2. Compile each new or affected fixture:
   `uv run groovescript compile tests/fixtures/<name>.gs -o tests/fixtures/<name>.ly`
3. Render it to PDF: `lilypond -o tests/fixtures/<name> tests/fixtures/<name>.ly`
   (install LilyPond with `apt-get install -y lilypond` or `brew install lilypond` if needed)
4. Update the docs if user-visible behaviour changed (`README.md`,
   `docs/DSL_REFERENCE.md`, and `docs/TUTORIAL.md` where relevant).
5. If you added instruments, modifiers or keywords, update the Vim syntax
   file (`editors/vim/syntax/groovescript.vim`) and the web editor
   highlighter (`editors/web/gs-mode.js`). New MIDI drum notes also need a
   voice in `editors/web/drumkit.js`.
6. Commit the `.gs`, `.ly`, `.pdf`, docs and code changes together.

`tests/test_fixtures_fresh.py` fails whenever a committed `.ly` under
`tests/fixtures/`, `templates/` or `charts/` no longer matches the
compiler's output. Recompile and re-render the PDF rather than editing
the test.

## Adding a test fixture

Place the `.gs` source under `tests/fixtures/`, compile it to `.ly`, render to `.pdf`, and commit all three files together.

## Fixing a bug

Add a regression test that reproduces the exact scenario, asserts the
correct behaviour (not just the absence of a crash), and carries a short
docstring saying what it guards against. Put it next to the existing
tests for that area.

## Bug reports and feature requests

Please open an issue at [GitHub Issues](https://github.com/groovescript/groovescript/issues).
