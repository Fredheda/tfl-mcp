#!/usr/bin/env bash
# Guarded build+redeploy of HEAD for the tfl-status agent, the laptop
# fallback to the Deploy agent workflow. Refuses to run on a dirty git tree so
# that what ships is a commit you can name.
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
