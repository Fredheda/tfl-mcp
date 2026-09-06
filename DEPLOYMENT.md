# Deployment

One Azure resource: `func-tfl-mcp`, a Python Function App on a Flex
Consumption plan, in the shared `rg-chatbot` resource group (no dedicated
resource group -- see the workspace's `deploying-azure-projects` skill).
Storage account `sttflmcp` backs its deployment package (a Functions
platform requirement, unrelated to the TFL data itself, which isn't
persisted anywhere).

Access control: the Function App's MCP extension system key
(`webhookAuthorizationLevel: "System"` in `function_app/host.json`) -- a
public URL, but every MCP call needs this key. Not network isolation (Flex
Consumption has no internal-ingress equivalent); acceptable here because
TFL line status isn't sensitive data.

## Deploy

Infra (first time, or whenever `infra/main.bicep` changes):
```bash
./infra/deploy.sh
```

Code (whenever `tfl_status.py` or `function_app/function_app.py` changes):
```bash
./scripts/deploy-mcp-tools.sh
```

## First deploy

1. `./infra/deploy.sh` -- provisions the Function App (prints a reminder
   since `FUNCTION_MCP_KEY` isn't set yet).
2. `./scripts/deploy-mcp-tools.sh` -- publishes the code.
3. Fetch the system key:
   ```bash
   az functionapp keys list -g rg-chatbot -n func-tfl-mcp \
     --query systemKeys.mcp_extension -o tsv
   ```
4. Add `FUNCTION_MCP_KEY=<value>` and `FUNCTION_APP_URL=https://func-tfl-mcp.azurewebsites.net`
   to `.env` (gitignored) -- future `infra/deploy.sh` runs pick up the key
   automatically, and any consumer (e.g. the tfl-status-agent, a later
   cycle) needs both values too.

## Verify

```bash
poetry run python scripts/verify_deployed_mcp.py victoria
```
Confirms a live TFL line-status call round-trips through the deployed
Function App, not just that it shows "Running". Uses `mcp`'s own v2 client
directly (`mcp.client.streamable_http`) -- `langchain-mcp-adapters` has no
release compatible with `mcp` v2 as of this writing, so it isn't a
dependency of this repo.
