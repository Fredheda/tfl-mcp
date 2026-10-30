#!/usr/bin/env bash
# Push a package zip to the Function App and check that it serves functions.
#
# The app is on the Flex Consumption plan, which accepts only package
# deployment; Python needs a remote build so dependencies are installed for
# Linux on Azure's side. After the push the function list can stay empty for a
# short while, so it is polled until at least one function shows up. An empty
# list at the timeout fails the deploy. A failing `function list` call counts
# as "not yet", not as fatal.
#
# Usage: ./scripts/deploy-functions.sh ZIP [TIMEOUT_SECONDS=300] [INTERVAL_SECONDS=5]
# Needs a live `az` session (ci-azure-login.sh in CI).
set -euo pipefail

APP=func-tfl-mcp
RG=rg-chatbot

zip="${1:?usage: deploy-functions.sh ZIP [TIMEOUT_SECONDS] [INTERVAL_SECONDS]}"
timeout="${2:-300}"
interval="${3:-5}"

if [ ! -f "$zip" ]; then
  echo "ERROR: package $zip does not exist." >&2
  exit 1
fi

if ! az functionapp deployment source config-zip -g "$RG" -n "$APP" \
  --src "$zip" --build-remote true; then
  echo "ERROR: pushing the package to $APP failed." >&2
  exit 1
fi

deadline=$((SECONDS + timeout))
while true; do
  names=$(az functionapp function list -g "$RG" -n "$APP" \
    --query "[].name" -o tsv 2>/dev/null || true)
  if [ -n "$names" ]; then
    while IFS= read -r name; do
      echo "function: $name"
    done <<<"$names"
    exit 0
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "ERROR: $APP lists no functions ${timeout}s after the deploy." >&2
    exit 1
  fi
  sleep "$interval"
done
