#!/usr/bin/env bash
# Decide which commit the `Deploy functions` workflow deploys, and refuse
# anything that should not reach production. Everything here needs only git,
# so the workflow runs it before it logs in to Azure.
#
# Prints the full 40-character SHA on stdout. Exits 1 with an `ERROR:` line on
# stderr when the input is not a full lowercase SHA, is not a commit of this
# repository, is not on origin/main, or predates the files a deploy needs.
#
# Usage: ./scripts/resolve-deploy-sha.sh [SHA]   (empty = head of origin/main)
set -euo pipefail

# Paths that must exist at the commit for the package to be buildable.
REQUIRED_PATHS=(
  function_app/function_app.py
  function_app/host.json
  function_app/requirements.txt
  tfl_status.py
)

sha="$(printf '%s' "${1:-}" | tr -d '[:space:]')"
if [ -z "$sha" ]; then
  sha="$(git rev-parse --verify 'origin/main^{commit}')"
fi

if ! printf '%s' "$sha" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "ERROR: '$sha' is not a full 40-character commit SHA." >&2
  exit 1
fi
if ! git cat-file -e "$sha^{commit}" 2>/dev/null; then
  echo "ERROR: $sha is not a commit in this repository." >&2
  exit 1
fi
if ! git merge-base --is-ancestor "$sha" origin/main; then
  echo "ERROR: $sha is not on main; only merged commits can be deployed." >&2
  exit 1
fi
for path in "${REQUIRED_PATHS[@]}"; do
  if ! git cat-file -e "$sha:$path" 2>/dev/null; then
    echo "ERROR: $sha has no $path; it predates the function app." >&2
    exit 1
  fi
done

echo "$sha"
