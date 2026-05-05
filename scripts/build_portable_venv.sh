#!/usr/bin/env bash
# ============================================================================
# build_portable_venv.sh - Build a relocatable portable venv on macOS
# ============================================================================
# Creates a `uv venv --relocatable` venv, installs the freshly-built
# code-puppy wheel from dist/, and zips the venv into a distributable archive.
# ============================================================================
set -euo pipefail

VERSION="${1:?usage: $0 VERSION [VENV_PATH] [ZIP_OUT]}"
VENV_PATH="${2:-.venv-portable}"
ZIP_OUT="${3:-code-puppy-venv-mac.zip}"

echo "Creating portable venv with uv (--relocatable)..."
uv venv --relocatable --python 3.13 "$VENV_PATH"

WHEEL=$(ls dist/*.whl 2>/dev/null | head -1 || true)
if [ -z "$WHEEL" ]; then
    echo "No wheel found in dist/" >&2
    exit 1
fi

echo "Installing $WHEEL into portable venv..."
uv pip install --python "$VENV_PATH/bin/python" "$WHEEL"

echo "Zipping venv to $ZIP_OUT..."
rm -f "$ZIP_OUT"
( cd "$VENV_PATH" && zip -qr "../$ZIP_OUT" . )

SIZE=$(du -h "$ZIP_OUT" | cut -f1)
echo "Built: $ZIP_OUT ($SIZE) for code-puppy v$VERSION"
