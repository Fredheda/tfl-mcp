#!/usr/bin/env bash
# Check, without a token, that the rolled agent advertises its public address
# and still sits behind its auth gate.
# Usage: ./scripts/check-agent.sh [timeout_seconds=300] [interval_seconds=5]
#
#   1. TFL_STATUS_AGENT_PUBLIC_URL must equal https://<ingress fqdn>. The agent
#      card's own `url` is built from it, and callers dial that address, not the
#      one they fetched the card from; a localhost default passes discovery and
#      breaks every caller.
#   2. An unauthenticated request for the card must return 401: the new
#      revision answers and Entra token validation is on. 200 means the gate
#      was lost and fails at once; anything else is retried until the timeout
#      (the app may still be starting from zero replicas).
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=lib/images.sh
source scripts/lib/images.sh

timeout="${1:-300}"
interval="${2:-5}"
deadline=$((SECONDS + timeout))

IFS='|' read -r _ app _ <<<"${IMAGES[0]}"
fqdn=$(az containerapp show -n "$app" -g "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)
public_url=$(az containerapp show -n "$app" -g "$RG" \
  --query "properties.template.containers[0].env[?name=='TFL_STATUS_AGENT_PUBLIC_URL'].value | [0]" -o tsv)
if [ "$public_url" != "https://$fqdn" ]; then
  echo "ERROR: TFL_STATUS_AGENT_PUBLIC_URL is '$public_url', expected 'https://$fqdn'; the agent card would advertise the wrong address." >&2
  exit 1
fi
echo "$app advertises https://$fqdn"

while true; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://$fqdn/.well-known/agent-card.json" || true)
  case "$code" in
    401)
      echo "Card request without a token: 401 (auth gate on)"
      exit 0 ;;
    200)
      echo "ERROR: the agent card was served without a token; the auth gate is off." >&2
      exit 1 ;;
  esac
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "ERROR: timed out after ${timeout}s waiting for $app to answer 401 (last status: $code)." >&2
    exit 1
  fi
  sleep "$interval"
done
