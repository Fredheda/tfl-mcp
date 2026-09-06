#!/usr/bin/env bash
# Idempotent: creates (or reuses) the Entra app registration representing
# the tfl-status agent's API, defines its TflStatus.Caller app role, and
# requires role assignment for anyone to obtain a token for it. Prints the
# client ID + tenant ID infra/deploy.sh needs.
#
# Usage: ./scripts/setup-agent-auth.sh
set -euo pipefail

APP_NAME="tfl-status-agent-api"
TENANT_ID=$(az account show --query tenantId -o tsv)

EXISTING_APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)

if [ -z "$EXISTING_APP_ID" ]; then
  echo "Creating Entra app registration '$APP_NAME'..."
  # Identifier URI must be set in a second call, from the app's own appId --
  # this tenant enforces Entra's identifier-URI security policy, which
  # rejects an arbitrary string like "api://tfl-status-agent" (must contain
  # a tenant-verified domain, the tenant ID, or the app's own ID instead).
  # See https://aka.ms/identifier-uri-formatting-error.
  APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
  az ad app update --id "$APP_ID" --identifier-uris "api://$APP_ID" --app-roles '[
    {
      "allowedMemberTypes": ["Application"],
      "description": "Caller apps that may invoke the tfl-status agent.",
      "displayName": "TflStatus.Caller",
      "id": "3f6e6f1e-3f7a-4f0e-9a3a-2f6a2f7e6f1e",
      "isEnabled": true,
      "value": "TflStatus.Caller"
    }
  ]'
  az ad sp create --id "$APP_ID" > /dev/null
else
  echo "Reusing existing Entra app registration '$APP_NAME' ($EXISTING_APP_ID)."
  APP_ID="$EXISTING_APP_ID"
fi

SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
az rest --method PATCH \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID" \
  --body '{"appRoleAssignmentRequired": true}'

echo ""
echo "AGENT_AAD_CLIENT_ID=$APP_ID"
echo "AGENT_AAD_TENANT_ID=$TENANT_ID"
echo "(add both to .env for infra/deploy.sh)"
echo ""
echo "App ID URI (audience for tokens/bicep allowedAudiences): api://$APP_ID"
