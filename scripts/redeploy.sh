#!/usr/bin/env bash
# Roll ca-tfl-status-agent to the image built from a given commit.
# Usage: ./scripts/redeploy.sh [git-sha]
set -euo pipefail

RG=rg-chatbot
SHA="${1:-$(git rev-parse HEAD)}"
[ -n "$SHA" ] || { echo "ERROR: could not resolve a SHA" >&2; exit 1; }
echo "Deploying image for commit $SHA"

az containerapp update -n ca-tfl-status-agent -g "$RG" \
  --image "acrchatbotfredheda.azurecr.io/tfl-status-agent:$SHA" --output none

FQDN=$(az containerapp show -n ca-tfl-status-agent -g "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)
echo "Deployed. https://$FQDN"
