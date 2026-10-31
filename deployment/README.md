# Deployment

Two deployables share the `rg-chatbot` resource group:

- **Function App** `func-tfl-mcp`: the hosted MCP server (`function_app/`, built on the root `tfl_status.py`).
- **Agent** `ca-tfl-status-agent`: the A2A agent (`tfl_status_agent/`), a Container App in its own environment `cae-tfl-status`, gated by Microsoft Entra ID. It calls the Function App.

PRs run CI (see [github.md](github.md)); a merge runs nothing. Deploys are manual.

## What to run, by what changed

| Changed | Run |
|---|---|
| `infra/main.bicep` | `./infra/deploy.sh` (add `<git-sha>` to also roll the agent image) |
| `tfl_status.py` or `function_app/` | **Deploy functions** workflow ([github.md](github.md)), or `./scripts/deploy-mcp-tools.sh` ([local.md](local.md)) |
| `tfl_status_agent/` or its system prompt | `./scripts/ship.sh`, or `./scripts/redeploy.sh <git-sha>` after `build-push.sh` ([local.md](local.md)) |
| Tools added or changed | Function App first, then the agent |

## Files

- [github.md](github.md): CI and security checks, the Deploy functions workflow, rollback, one-time GitHub OIDC setup.
- [local.md](local.md): deploying from a laptop (Function App and agent).
- [infra.md](infra.md): Azure resources, access control, first deploy, Entra auth setup.
- [operations.md](operations.md): verify a deployment, approve an agent caller, rollback.
- [expirations.md](expirations.md): secrets and tokens that expire.

Running it on your machine instead: [../docs/development.md](../docs/development.md).
