#!/usr/bin/env bash
# Provision (or update) the Function App from infra/main.bicep. Idempotent
# -- safe to re-run any time infra changes.
#
# Usage: ./infra/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

RG=rg-chatbot

[ -f .env ] && { set -a; source .env; set +a; }

for var in OPENAI_API_KEY FUNCTION_MCP_KEY AGENT_AAD_CLIENT_ID AGENT_AAD_TENANT_ID; do
  [ -n "${!var:-}" ] || echo "WARNING: $var is empty in .env (needed for the tfl-status agent)"
done

az deployment group create \
  --resource-group "$RG" \
  --template-file infra/main.bicep \
  --parameters functionMcpKey="${FUNCTION_MCP_KEY:-}" \
    agentImageTag="${1:-latest}" \
    agentOpenaiApiKey="${OPENAI_API_KEY:-}" \
    agentAadClientId="${AGENT_AAD_CLIENT_ID:-}" \
    agentAadTenantId="${AGENT_AAD_TENANT_ID:-}" \
  --query "properties.provisioningState" -o tsv

FQDN=$(az functionapp show -n func-tfl-mcp -g "$RG" --query properties.defaultHostName -o tsv)
echo "Function App: https://$FQDN"

AGENT_FQDN=$(az containerapp show -n ca-tfl-status-agent -g "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv 2>/dev/null || true)
[ -n "$AGENT_FQDN" ] && echo "tfl-status agent: https://$AGENT_FQDN"

if [ -z "${FUNCTION_MCP_KEY:-}" ]; then
  echo ""
  echo "FUNCTION_MCP_KEY is unset -- this looks like a first deploy. Next steps:"
  echo "  1. ./scripts/deploy-mcp-tools.sh"
  echo "  2. FUNCTION_MCP_KEY=\$(az functionapp keys list -g $RG -n func-tfl-mcp --query systemKeys.mcp_extension -o tsv)"
  echo "  3. Add FUNCTION_MCP_KEY=<value> to .env so future deploys and consumers can read it"
fi
