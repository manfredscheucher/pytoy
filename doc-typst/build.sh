#!/usr/bin/env bash
# Build the toyasm PDF manual from the Typst sources in this folder.
#
# Requires Typst (https://typst.app). On macOS: `brew install typst`.
# Output: toyasm.pdf next to this script.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v typst >/dev/null 2>&1; then
  echo "error: 'typst' not found. Install it (e.g. 'brew install typst')." >&2
  exit 1
fi

typst compile main.typ toyasm.pdf
echo "built: doc-typst/toyasm.pdf"
