#!/usr/bin/env bash
# Assigns the TflStatus.Caller app role to one service principal or user.
# Usage: ./scripts/approve-caller.sh <principal-id> [display-name]
set -euo pipefail

PRINCIPAL_ID="${1:?Usage: approve-caller.sh <principal-id> [display-name]}"
LABEL="${2:-$PRINCIPAL_ID}"

APP_NAME="tfl-status-agent-api"
APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)
[ -n "$APP_ID" ] || { echo "ERROR: run setup-agent-auth.sh first" >&2; exit 1; }

SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
ROLE_ID=$(az ad app show --id "$APP_ID" --query "appRoles[?value=='TflStatus.Caller'].id" -o tsv)

az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID/appRoleAssignedTo" \
  --body "{\"principalId\": \"$PRINCIPAL_ID\", \"resourceId\": \"$SP_ID\", \"appRoleId\": \"$ROLE_ID\"}"

echo "Approved $LABEL ($PRINCIPAL_ID) to call the tfl-status agent."
