#!/usr/bin/env bash
# Publish the Function App's code (infra/deploy.sh provisions the resource
# itself -- this only ships code to it). Requires the `func` CLI (Azure
# Functions Core Tools) installed locally.
#
# Usage: ./scripts/deploy-mcp-tools.sh
set -euo pipefail
cd "$(dirname "$0")/.."

FUNCTION_APP_NAME=func-tfl-mcp

# Copy the canonical shared logic into the function package before
# publishing (single source of truth lives at tfl_status.py, repo root --
# not duplicated by hand).
cp tfl_status.py function_app/tfl_status.py

cd function_app
func azure functionapp publish "$FUNCTION_APP_NAME" --python
