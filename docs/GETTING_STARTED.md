# Getting started with GrooveScript

This guide walks you from zero to a rendered drum chart PDF. For a deeper
walkthrough of every language feature, see [`TUTORIAL.md`](TUTORIAL.md). For
a searchable reference of the DSL, see [`DSL_REFERENCE.md`](DSL_REFERENCE.md).

## 1. Install

The quickest way to get everything set up is the one-shot setup script:

```bash
./setup.sh
```

It installs `uv` (if missing), `lilypond` (via `brew` on macOS or `apt` on
Linux), and runs `uv sync` to pull Python dependencies.

If you prefer to do it manually, GrooveScript needs Python ≥ 3.11 and the
external `lilypond` binary for PDF rendering:

```bash
# Python deps
uv sync

# LilyPond
brew install lilypond          # macOS
sudo apt-get install -y lilypond  # Debian/Ubuntu
```

## 2. Scaffold your first chart

The repo ships with a `./scaffold-chart` script that creates a new chart
from a template under `charts/`:

```bash
./scaffold-chart first
```

That writes `charts/first.gs` based on the default `rock` template.
(`./scaffold-chart -h` lists the other templates; pick one with
`./scaffold-chart -t <template> <name>`.)

Open `charts/first.gs` in an editor. You'll see a complete, valid chart
with a title, a reusable groove, and one section — something like:

```groovescript
title: "First"
tempo: 120

groove "money beat":
    BD: 1, 3
    SN: 2, 4
    HH: *8

section "verse":
  bars: 4
  groove: "money beat"
```

Tweak anything you like, then move on.

## 3. Build the PDF

The `./build-pdf` script compiles `charts/<name>.gs` to LilyPond and then
renders it to PDF in one shot:

```bash
./build-pdf first
```

Open `charts/first.pdf` — you should see a rock groove with a boxed
"VERSE" rehearsal mark, title, tempo, and time signature.

Under the hood `./build-pdf` runs `uv run groovescript compile` followed
by `lilypond -o`, but you should almost never need to invoke those
directly.

## 4. What to read next

- **Want a guided walkthrough of the language?** Read
  [`TUTORIAL.md`](TUTORIAL.md). It builds up a real chart piece by piece,
  introducing metadata, form, grooves, placeholder fills, variations, and
  real fills in order.
- **Looking up a specific feature?** Search [`DSL_REFERENCE.md`](DSL_REFERENCE.md).
  It's organized by topic (metadata, instruments, beat labels, grooves,
  fills, sections, variations, modifiers) and is the authoritative reference
  for the DSL.
- **Editor integration.** A Vim / Neovim syntax-highlighting plugin lives in
  [`editors/vim/`](editors/vim/README.md).
- **More examples.** The `tests/fixtures/` directory has `.gs` files with
  their compiled `.ly` and rendered `.pdf` committed alongside.
