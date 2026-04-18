#!/usr/bin/env bash
set -euo pipefail

# GrooveScript development environment setup
# Installs uv, lilypond, and Python dependencies.

echo "==> Setting up GrooveScript development environment"

# ── 1. Install / detect uv ──────────────────────────────────────────────────

if command -v uv &>/dev/null; then
    echo "    uv is already installed: $(uv --version)"
else
    echo "    Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Ensure uv is on PATH for the rest of this script
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    echo "    uv installed: $(uv --version)"
fi

# ── 2. Install / detect lilypond ─────────────────────────────────────────────

if command -v lilypond &>/dev/null; then
    echo "    lilypond is already installed: $(lilypond --version 2>&1 | head -1)"
else
    echo "    Installing lilypond..."
    if [[ "$(uname -s)" == "Darwin" ]]; then
        # macOS — use Homebrew
        if ! command -v brew &>/dev/null; then
            echo "    ERROR: Homebrew is required on macOS. Install it from https://brew.sh"
            exit 1
        fi
        brew install lilypond
    elif command -v apt-get &>/dev/null; then
        # Debian / Ubuntu
        sudo apt-get update -qq && sudo apt-get install -y lilypond
    else
        echo "    ERROR: Could not detect a supported package manager (brew or apt-get)."
        echo "           Please install lilypond manually: https://lilypond.org/download.html"
        exit 1
    fi
    echo "    lilypond installed: $(lilypond --version 2>&1 | head -1)"
fi

# ── 3. Install Python dependencies ──────────────────────────────────────────

echo "    Running uv sync..."
uv sync
echo ""
echo "==> Done! You can now run:"
echo "      uv run pytest                          # run tests"
echo "      uv run groovescript compile FILE.gs     # compile a chart"
echo "      ./scaffold-chart my-song                # create a new chart"
