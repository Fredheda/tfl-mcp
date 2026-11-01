# Infrastructure and one-time setup

Everything lives in the shared `rg-chatbot` resource group (no dedicated resource group). `infra/main.bicep` defines it; `infra/deploy.sh` applies it.

## Function App (`func-tfl-mcp`)

A Python Function App on a Flex Consumption plan. Storage account `sttflmcp` backs its deployment package; that is a Functions platform requirement, unrelated to the TfL data, which is not persisted anywhere.

**Access control:** the Function App's MCP extension system key (`webhookAuthorizationLevel: "System"` in `function_app/host.json`). The URL is public, but every MCP call needs this key. This is not network isolation (Flex Consumption has no internal-ingress equivalent); it is acceptable here because the TfL data it serves (line status, journeys, arrivals) is public, not sensitive.

### First deploy

1. `./infra/deploy.sh` provisions the Function App (it prints a reminder, since `FUNCTION_MCP_KEY` is not set yet).
2. `./scripts/deploy-mcp-tools.sh` publishes the code.
3. Fetch the system key:
   ```bash
   az functionapp keys list -g rg-chatbot -n func-tfl-mcp \
     --query systemKeys.mcp_extension -o tsv
   ```
4. Add `FUNCTION_MCP_KEY=<value>` and `FUNCTION_APP_URL=https://func-tfl-mcp.azurewebsites.net` to `.env` (gitignored). Future `infra/deploy.sh` runs pick up the key automatically, and any consumer of the hosted server (including the agent) needs both values too.

The GitHub deploy identity is a separate one-time step: see [github.md](github.md).

## Agent (`ca-tfl-status-agent`)

A LangGraph agent exposed over A2A. It runs as its own Azure resource, `ca-tfl-status-agent`, in its own Container Apps environment (`cae-tfl-status`), with external ingress, because it must be reachable from multiple independent callers each in their own environment (internal ingress cannot cross Container Apps environments). Access control is Microsoft Entra ID token validation via Container Apps' built-in auth, not network isolation or application code. It scales to zero (`minReplicas: 0`).

The agent streams: its card advertises `capabilities.streaming: true`, and while a task runs it publishes `WORKING` status updates (one per reasoning summary, tool call, tool result, and the final "composing answer" step, with the kind in the event's `metadata.kind`) before the final artifact. A streaming-capable caller sees them as they happen; a non-streaming caller gets the same final task in one response. The model is `gpt-5.6-luna` on the OpenAI Responses API with reasoning summaries enabled, which is what produces the reasoning lines.

The design is written up in the spec `docs/tfl-mcp/specs/completed/2026-09-06-tfl-status-agent-design.md` (author's workspace notes, not in this repo).

### Entra auth setup

Idempotent; run once, or whenever it needs re-running:

```bash
./scripts/setup-agent-auth.sh
```

It prints `AGENT_AAD_CLIENT_ID` and `AGENT_AAD_TENANT_ID`. Add both to `.env`. Then provision the agent with `./infra/deploy.sh <git-sha>` (see [local.md](local.md)). To let a caller in, see [operations.md](operations.md).
