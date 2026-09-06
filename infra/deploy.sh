#!/usr/bin/env bash
# Provision (or update) the Function App from infra/main.bicep. Idempotent
# -- safe to re-run any time infra changes.
#
# Usage: ./infra/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

RG=rg-chatbot

[ -f .env ] && { set -a; source .env; set +a; }

az deployment group create \
  --resource-group "$RG" \
  --template-file infra/main.bicep \
  --parameters functionMcpKey="${FUNCTION_MCP_KEY:-}" \
  --query "properties.provisioningState" -o tsv

FQDN=$(az functionapp show -n func-tfl-mcp -g "$RG" --query defaultHostName -o tsv)
echo "Function App: https://$FQDN"

if [ -z "${FUNCTION_MCP_KEY:-}" ]; then
  echo ""
  echo "FUNCTION_MCP_KEY is unset -- this looks like a first deploy. Next steps:"
  echo "  1. ./scripts/deploy-mcp-tools.sh"
  echo "  2. FUNCTION_MCP_KEY=\$(az functionapp keys list -g $RG -n func-tfl-mcp --query systemKeys.mcp_extension -o tsv)"
  echo "  3. Add FUNCTION_MCP_KEY=<value> to .env so future deploys and consumers can read it"
fi
