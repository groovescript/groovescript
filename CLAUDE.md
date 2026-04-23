# GrooveScript

Python CLI that compiles `.gs` drum notation files -> LilyPond -> PDF sheet music.

## Companion docs

- `README.md` -- user-facing language reference and getting-started guide

## Architecture

```
src/groovescript/
  cli.py              # argparse entry point (compile, lint, --watch)
  parser.py           # Lark grammar -> parse tree -> AST (via Transformer)
  ast_nodes.py        # Dataclasses for AST
  compiler.py         # AST -> IR (flat event list per bar)
  lilypond.py         # IR -> LilyPond source
  midi.py             # IR -> MIDI file bytes (Format 1, GM drums on channel 10)
  lilypond_template.ly # Static LilyPond boilerplate (loaded by lilypond.py)
  grammar.lark        # Lark EBNF grammar
  groove_library.gs    # Built-in groove library (parsed at runtime)
  fill_library.gs      # Built-in fill library (parsed at runtime)
  variation_library.gs # Built-in variation library (parsed at runtime)
  library.py           # Loader for groove / fill / variation libraries
  lint.py             # Style checker used by `lint --style`
tests/
  fixtures/           # .gs / .ly / .pdf reference files
  test_parser.py
  test_compiler.py
  test_lilypond.py
docs/                 # Documentation
charts/               # Real (non-test) charts: .gs source + compiled .ly + .pdf
```

**Pipeline**: `.gs` source -> parser (Lark LALR) -> AST -> compiler -> IR (`IRSong` -> `IRBar[]`) -> LilyPond emitter -> `.ly` file

**IR**: flat list of `Event(bar, beat_position, instrument, modifiers)` sorted by time. Beat positions are `fractions.Fraction`. Each `IRBar` carries its own inferred `subdivision`.

## Design constraints (must not violate)

- IR beat positions use `fractions.Fraction` -- not float, not int grid
- Per-bar subdivision is inferred from bar content, not declared; one of `{1,2,3,4}` slots-per-beat; mixing straight 16ths with triplets in one bar is rejected
- Fill bars have independent subdivision from surrounding groove bars
- Variation actions are `add`, `remove`, `replace`, `substitute`, `modify add`, `modify remove`. `modify add <mod> to <instrument> at <beats>` / `modify remove <mod> from <instrument> at <beats>` target existing hits on the named instrument without re-stating beat positions
- Groove `extend:` bodies accept variation actions in addition to pattern-line overrides. Bare actions apply to every bar of the base; wrap them in `variation at bar N:` / `variation at bars N, M:` blocks to scope to specific bars. Pattern-line merge runs before actions are applied. Chains accumulate: `C extend: "B"` inherits `B`'s already-resolved `extend_variations` and appends its own on top
- File order = arrangement order
- A section is either classic (`bars:` + `groove:`) or play-list (`play:`) -- mutually exclusive
- Section `like "parent"` inherits the basic arrangement only (scalars, inline grooves, section-level dynamic spans, crash-in flag). `like "parent" with fills|variations|cues` opts into additional categories. Categories are order-insensitive, commas optional, duplicates rejected. Scalar fields use inheritor's value when set, list fields concatenate. Dynamic spans defined inside a groove or fill travel with that groove/fill wherever it's referenced
- Errors raise `GrooveScriptError` with Rust-style diagnostics; CLI catches and renders, no tracebacks
- Preprocessors (`_preprocess_commas`, `_quote_unquoted_count_notes`) run before Lark sees the text
- LilyPond boilerplate lives in `lilypond_template.ly` with `{{HEADER}}`, `{{SCORE_HEADER}}`, `{{SCORE_PRELUDE}}`, `{{BODY}}` placeholders
- DSL version: bump `CURRENT_DSL_VERSION` in `parser.py` on breaking changes

## Commands

```bash
uv run pytest                                          # Run tests
uv run groovescript compile input.gs -o output.ly      # Compile .gs -> .ly
uv run groovescript compile input.gs -o output.ly --watch  # Re-compile on save
uv run groovescript compile input.gs -o output.ly --compact  # Collapse identical bars across implicit phrase boundaries
uv run groovescript lint input.gs                      # Lint (parse+compile, no output)
uv run groovescript lint --style input.gs              # Also report stylistic warnings
uv run groovescript lint --watch input.gs              # Re-lint on save
uv run groovescript midi input.gs -o output.mid        # Export .gs -> .mid
uv run groovescript midi input.gs -o output.mid --watch  # Re-export on save
uv run groovescript musicxml input.gs -o output.xml    # Export .gs -> MusicXML
uv run groovescript musicxml input.gs -o output.xml --watch  # Re-export on save
lilypond -o output output.ly                           # Render to PDF
```

## Dependencies

- `lark` (Python package; managed by `uv`)
- `lilypond` (external binary for PDF rendering)

## End-to-end verification after each change

After implementing a change that affects compiled output, always:

1. Run the test suite: `uv run pytest`
2. Compile any new or affected fixture:
   `uv run groovescript compile tests/fixtures/<name>.gs -o tests/fixtures/<name>.ly`
3. Render it to PDF: `lilypond -o tests/fixtures/<name> tests/fixtures/<name>.ly`
4. Update relevant docs if user-visible behavior changed (`README.md`, `CLAUDE.md`)
5. Update the Vim syntax plugin (`editors/vim/syntax/groovescript.vim`) if new instruments, modifiers, or keywords were added
6. Commit `.gs`, `.ly`, `.pdf`, updated docs, and code changes together

## Regression tests for bug fixes

When fixing a bug, always add a regression test that would have caught the bug
before the fix was applied. The test should:

1. Reproduce the exact scenario that triggered the bug
2. Assert the *correct* behaviour, not just the absence of a crash
3. Include a short docstring noting it is a regression test and what it guards against
4. Live next to existing tests for the same module/feature area

## PDF fixtures

- Always render `.ly` → `.pdf` with `lilypond` and commit the PDF alongside the `.gs` and `.ly`
- If `lilypond` is not installed, install it (`apt-get install -y lilypond`) before rendering
- This applies to both `tests/fixtures/` and `charts/`
