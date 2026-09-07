#!/usr/bin/env bash
# Guarded build+redeploy for the tfl-status agent. Refuses to run on a
# dirty git tree (az acr build builds the working tree, not HEAD).
#
# Usage: ./scripts/ship.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: working tree is dirty. Commit or stash before shipping." >&2
  exit 1
fi

./scripts/build-push.sh
./scripts/redeploy.sh
