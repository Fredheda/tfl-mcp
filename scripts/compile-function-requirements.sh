#!/usr/bin/env bash
# Regenerate function_app/requirements.txt: an exact pin for the Function App's
# direct dependencies and everything they pull in. No hashes.
#
# pip itself resolves the set (`pip install --dry-run --report`, nothing is
# installed), under a 14-day window (PIP_UPLOADED_PRIOR_TO) and for the Function
# App's runtime: Linux x86-64 wheels, Python 3.13, whatever machine runs this.
# The pip version is the image's (tfl_status_agent/Dockerfile); a guard test keeps
# the two equal. Run it on purpose, review the diff, open a PR.
#
# Usage: ./scripts/compile-function-requirements.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# Direct dependencies of the Function App: the only place their ranges live.
DIRECT=("azure-functions>=2.3.0" "requests>=2.34.2")

# Only files uploaded at least 14 days ago; the window is a constant, not an argument.
export PIP_UPLOADED_PRIOR_TO=P14D

# mktemp -d ignores TMPDIR on macOS, so the path is built by hand.
tmp="$(mktemp -d "${TMPDIR:-/tmp}/function-reqs.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

python3.13 -m venv "$tmp/venv"
py="$tmp/venv/bin/python"
"$py" -m pip install --quiet pip==26.2.2

"$py" -m pip install --ignore-installed --dry-run --quiet \
  --report "$tmp/report.json" \
  --only-binary=:all: \
  --python-version 3.13 --implementation cp --abi cp313 \
  --platform manylinux_2_28_x86_64 \
  --platform manylinux_2_17_x86_64 \
  --platform manylinux2014_x86_64 \
  "${DIRECT[@]}"

"$py" scripts/report_to_pins.py "$tmp/report.json" > "$tmp/requirements.txt"
cp "$tmp/requirements.txt" function_app/requirements.txt
echo "Wrote function_app/requirements.txt: $(grep -c '==' function_app/requirements.txt) pins"
