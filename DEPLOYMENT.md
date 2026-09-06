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
Function App, not just that it shows "Running". Uses
`langchain_mcp_adapters.client.MultiServerMCPClient` -- the same
library/pattern Portfolio's `backend/agent/mcp_tools.py` already uses.
This repo pins `mcp[cli]<2.0.0` specifically so this works:
`langchain-mcp-adapters`'s latest release (`0.3.2`) hard-pins `mcp<2.0.0`
and has no release compatible with `mcp` v2 as of this writing -- an
earlier attempt at this repo used `mcp` v2 directly (see git history), but
that would have meant hand-writing MCP-to-LangChain tool-wrapping glue for
every future agent that needs MCP tools, instead of using the
ecosystem-standard bridge. Reverted to v1 deliberately.
