# Deploying from a laptop

The fallback when GitHub is unavailable, and the only path for infra and the agent. Needs the Azure CLI, logged in with rights on `rg-chatbot`.

## Function App (`func-tfl-mcp`)

Infra (first time, or whenever `infra/main.bicep` changes):

```bash
./infra/deploy.sh
```

Code (whenever `tfl_status.py` or `function_app/function_app.py` changes):

```bash
./scripts/deploy-mcp-tools.sh
```

`deploy-mcp-tools.sh` copies the root `tfl_status.py` into `function_app/` (a gitignored copy) before packaging. For the first deploy sequence, see [infra.md](infra.md).

## Agent (`ca-tfl-status-agent`)

Infra (whenever `infra/main.bicep` changes) plus code (whenever `tfl_status_agent/` changes):

```bash
./scripts/build-push.sh          # builds + pushes the image (needs a clean git tree)
./infra/deploy.sh <git-sha>      # provisions/updates infra with that image
# or, for a code-only change after infra is already provisioned:
./scripts/redeploy.sh <git-sha>
```

`./scripts/ship.sh` does `build-push.sh` then `redeploy.sh` in one go. It refuses to run on a dirty git tree, because `az acr build` builds the working tree, not `HEAD`.

The one-time Entra auth setup for the agent is in [infra.md](infra.md).
