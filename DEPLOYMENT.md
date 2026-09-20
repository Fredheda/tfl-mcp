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
the TFL data it serves (line status, journeys, arrivals) is public, not sensitive.

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
Function App, not just that it shows "Running". It calls `get_tfl_status`
and the three journey tools once each (`find_station`, `get_arrivals`,
`plan_journey`), so a tool missing from the deployed Function App shows
up as a `StopIteration` here. After adding or changing tools, run
`scripts/deploy-mcp-tools.sh` first, then `scripts/ship.sh` for the agent:
the agent fetches tool schemas live at startup, and its system prompt is
baked into the image. Uses
`langchain_mcp_adapters.client.MultiServerMCPClient`. This repo pins
`mcp[cli]<2.0.0` specifically so this works: `langchain-mcp-adapters`'s
latest release (`0.3.2`) hard-pins `mcp<2.0.0` and has no release
compatible with `mcp` v2 as of this writing -- an earlier attempt at this
repo used `mcp` v2 directly (see git history), but that would have meant
hand-writing MCP-to-LangChain tool-wrapping glue instead of using the
ecosystem-standard bridge. Reverted to v1 deliberately.

## tfl-status agent (`tfl_status_agent/`)

A second, independent deployable in this repo: a LangGraph agent that
answers TFL line-status, journey and arrivals questions by calling the
Function App above's MCP tools (plus a local `get_current_time` tool),
exposed over the A2A protocol. Runs as its own Azure resource,
`ca-tfl-status-agent`, in its own Container Apps environment
(`cae-tfl-status`) -- external ingress, since it must be reachable from
multiple independent callers each in their own environment (internal
ingress can't cross Container Apps environments). Access control is
Microsoft Entra ID token validation via Container Apps' built-in auth, not
network isolation or application code -- see
`docs/tfl-mcp/specs/2026-09-06-tfl-status-agent-design.md`.

The agent **streams**: its card advertises `capabilities.streaming: true`,
and while a task runs it publishes `WORKING` status updates (one per
reasoning summary, tool call, tool result, and the final "composing
answer" step, with the kind in the event's `metadata.kind`) before the
final artifact. A caller that opens the call with a streaming-capable
client sees those as they happen; a non-streaming caller gets the same
final task in one response. The model is `gpt-5.6-luna` on the OpenAI
Responses API with reasoning summaries enabled, which is what produces the
reasoning lines.

### Deploy

Entra auth setup (idempotent, one-time or whenever it needs re-running):
```bash
./scripts/setup-agent-auth.sh
```
Prints `AGENT_AAD_CLIENT_ID`/`AGENT_AAD_TENANT_ID` -- add both to `.env`.

Infra (whenever `infra/main.bicep` changes) + code (whenever
`tfl_status_agent/` changes):
```bash
./scripts/build-push.sh          # builds + pushes the image (needs a clean git tree)
./infra/deploy.sh <git-sha>       # provisions/updates infra with that image
# or, for a code-only change after infra is already provisioned:
./scripts/redeploy.sh <git-sha>
```

### Approve a caller

No caller can obtain a token for this agent until explicitly approved --
Entra's `appRoleAssignmentRequired` is set on the app, so an unapproved
principal can't even get a token issued, let alone pass the authConfig
gate:
```bash
./scripts/approve-caller.sh <principal-object-id> [display-name]
```
For a service (the common case -- one deployed agent/app calling this
one), that's the caller's own service-principal object ID, approved for
client-credentials (app-only) tokens -- the same authentication model any
new consumer of this agent should use.

### Local dev / testing

```bash
poetry run uvicorn tfl_status_agent.server:app --port 8002   # local server, no auth locally
poetry run python scripts/verify_agent_card.py                # discovery check
poetry run python scripts/ask_tfl_status_agent.py "victoria line status"   # real end-to-end call, prints progress lines live (--blocking for the old single response)
```
A real end-to-end call (A2A -> LangGraph -> MCP tool -> live TFL API) takes
15-20+ seconds -- `ask_tfl_status_agent.py` already sets a 60s client
timeout for this reason (see its own docstring). Against the deployed
agent, pass its FQDN and a bearer token as extra arguments; see
`scripts/ask_tfl_status_agent.py --help`-equivalent usage in its docstring.

### Verify a live deployment

```bash
curl -i https://<tfl-status-agent-fqdn>/.well-known/agent-card.json
```
Expect `401` unauthenticated. With a valid, approved caller's token in the
`Authorization: Bearer` header, expect `200` with the agent card.

Also try: "fastest way from Waterloo to King's Cross right now", "next
Victoria line trains at Oxford Circus", and "Waterloo to King's Cross,
arriving by 9am tomorrow" (this one exercises `get_current_time` and the
image's `tzdata`).
