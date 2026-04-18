# Contributing to GrooveScript

## Running the tests

```bash
uv run pytest
```

## End-to-end verification

After any change that affects compiled output:

1. Run the test suite: `uv run pytest`
2. Compile an affected fixture:
   `uv run groovescript compile tests/fixtures/<name>.gs -o tests/fixtures/<name>.ly`
3. Render to PDF: `lilypond -o tests/fixtures/<name> tests/fixtures/<name>.ly`
4. Commit the `.gs`, `.ly`, and `.pdf` together.

## Adding a test fixture

Place the `.gs` source under `tests/fixtures/`, compile it to `.ly`, render to `.pdf`, and commit all three files together.

## Bug reports and feature requests

Please open an issue at [GitHub Issues](https://github.com/groovescript/groovescript/issues).
