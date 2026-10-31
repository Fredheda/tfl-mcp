#!/usr/bin/env bash
# Decide which commit the `Deploy agent` workflow builds and deploys, and
# refuse anything that should not reach production. Everything here needs only
# git, so the workflow runs it before it logs in to Azure.
#
# Prints the full 40-character SHA on stdout. Exits 1 with an `ERROR:` line on
# stderr when the input is not a full lowercase SHA, is not a commit of this
# repository, or is not on origin/main.
#
# Usage: ./scripts/resolve-agent-sha.sh [SHA]   (empty = head of origin/main)
set -euo pipefail

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

echo "$sha"
