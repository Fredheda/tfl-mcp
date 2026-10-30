#!/usr/bin/env bash
# Build the deployment zip for the Function App from a source tree.
#
# SRC_ROOT is a directory laid out like this repository at some commit (the
# workflow fills it with `git archive`). The script reads nothing from the
# directory it runs in, so it also packages commits older than this script.
#
# It copies the shared logic file (git-ignored inside function_app/) into the
# function folder, then zips that folder's contents, leaving out local-only
# files, tests and caches. Dependencies are not installed here: the deploy
# asks Azure for a remote build.
#
# Usage: ./scripts/package-functions.sh SRC_ROOT OUT_ZIP
set -euo pipefail

src="${1:?usage: package-functions.sh SRC_ROOT OUT_ZIP}"
out="${2:?usage: package-functions.sh SRC_ROOT OUT_ZIP}"

if [ ! -d "$src/function_app" ]; then
  echo "ERROR: $src/function_app does not exist." >&2
  exit 1
fi
if [ ! -f "$src/tfl_status.py" ]; then
  echo "ERROR: $src/tfl_status.py does not exist." >&2
  exit 1
fi

mkdir -p "$(dirname "$out")"
out="$(cd "$(dirname "$out")" && pwd)/$(basename "$out")"
rm -f "$out"

cp "$src/tfl_status.py" "$src/function_app/tfl_status.py"

cd "$src/function_app"
zip -q -r -X "$out" . \
  -x 'local.settings.json*' '*/local.settings.json*' \
  -x 'tests/*' '*/tests/*' \
  -x '__pycache__/*' '*/__pycache__/*' '*.pyc' \
  -x '.gitignore' '*/.gitignore' \
  -x '.venv/*' '.python_packages/*'
echo "Packaged $out"
