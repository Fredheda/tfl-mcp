#!/usr/bin/env bash
# Build the tfl-status agent image natively on linux/amd64 via ACR Tasks
# and push :latest + :<git-sha>. NOTE: az acr build builds the WORKING
# TREE, not the committed SHA -- run with a clean tree.
#
# Usage: ./scripts/build-push.sh
set -euo pipefail
cd "$(dirname "$0")/.."

ACR=acrchatbotfredheda
SHA=$(git rev-parse HEAD)

az acr build --registry "$ACR" --file tfl_status_agent/Dockerfile \
  --image tfl-status-agent:latest --image "tfl-status-agent:$SHA" .

echo "Pushed tfl-status-agent at $SHA"
