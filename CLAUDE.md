# CLAUDE.md

Repo-specific facts for Claude Code. The workspace `CLAUDE.md` (`../CLAUDE.md`) owns everything else: response style, git and worktrees, ways of working (tickets and tiers, production deploys, PR size, test first, the PR loop), tooling, Jira, specs and plans. Keep this file true.

PR titles and descriptions never mention Claude Code. `scripts/ci-local.sh` is this repo's local CI script: green before `gh pr ready`.

## What this is

TFL MCP tools (`get_tfl_status`, `get_disrupted_lines`, `find_station`,
`plan_journey`, `get_arrivals`), run locally over stdio (`tfl.py`) or deployed
as an Azure Function App (`function_app/`). `tfl_status_agent/` is an A2A agent
over these tools; it adds a local `get_current_time` tool. The README has the
overview; local setup is in `docs/development.md`; deploys are in `deployment/`.

## Commands

Run from the repo root unless noted. Python 3.13, Poetry 2.x.

| Task | Command |
|------|---------|
| Install | `poetry install` |
| Local stdio server | `poetry run python tfl.py` |
| Tests | `poetry run pytest tests/ -v` |
| Function app tests | `cd function_app && .venv/bin/pytest tests -v` (isolated venv, see below) |
| Lint + format check | `poetry run ruff check . && poetry run ruff format --check .` |
| Type check | `poetry run pyright` |
| All CI checks | `scripts/ci-local.sh` (the gate before `gh pr ready`) |

CI runs on PRs only, as `backend` and `function-app-test`; `function-app-test`
and the AI review wait for `gh pr ready`. The `main` ruleset requires those two
plus `gitleaks`, `bandit` and `workflow-lint` from `security.yml`. The
workflows, the review and the local security commands: `deployment/github.md`
and `docs/development.md`.

Env var names (`.env`, see `.env.example`; meanings in `docs/development.md`):
`OPENAI_API_KEY`, `FUNCTION_APP_URL`, `FUNCTION_MCP_KEY`, optional
`TFL_STATUS_AGENT_PUBLIC_URL`; after `scripts/setup-agent-auth.sh` also
`AGENT_AAD_CLIENT_ID` and `AGENT_AAD_TENANT_ID`, read by `infra/deploy.sh`.

## Gotchas

- `function_app/` is a separate deployable with its own isolated venv, never
  installed through Poetry (commands: `docs/development.md`, "Checks").
- `function_app/tfl_status.py` is a gitignored copy of the root `tfl_status.py`,
  made by `scripts/deploy-mcp-tools.sh`. The root file is the single source of truth.
- The repo pins `mcp[cli]<2.0.0` on purpose: `langchain-mcp-adapters` (latest
  `0.3.2`) hard-pins `mcp<2.0.0`, and the agent and `scripts/verify_deployed_mcp.py`
  use it via `MultiServerMCPClient`. Do not move to `mcp` v2 until the adapter does.
- `tfl_status_agent/server.py` calls `load_dotenv()` before its other imports
  because they read env vars at import time; ruff's E402 is ignored for that
  file in `pyproject.toml`.
- After adding or changing tools, deploy the Function App first, then the
  agent (it fetches tool schemas at startup; its system prompt is baked into the image).
- The pip-audit step in `security.yml` ignores two advisories fixed only by
  bumping the pinned `langchain` (to 1.3.9) / `langgraph-sdk` (to 0.4.4);
  remove the `--ignore-vuln` flags when those pins move. `langchain` 1.3.9
  needs `langgraph` >=1.2.4, so the exactly pinned `langchain`, `langgraph`,
  `langgraph-prebuilt` and `langchain-openai` have to move together: expect to
  bump them by hand in one PR if Dependabot's grouped PR does not.
- Dependabot (`.github/dependabot.yml`) opens weekly version-update PRs: one
  grouped PR per ecosystem for minor and patch updates, majors separate, only
  releases older than 14 days. Alerts and security updates are repo settings.
  Dependabot PRs get no secrets, so the AI review skips them.

## Pointers

- Local dev, the agent's local testing, security checks: `docs/development.md`.
- Deploying (Function App via the manual **Deploy functions** workflow, agent
  via the manual **Deploy agent** workflow, which builds the image if needed;
  `scripts/ship.sh` is the laptop fallback; rollback, verification, expiry
  dates): `deployment/`.
- Every workflow run waits in GitHub for the owner's approval (`production`
  requires him as reviewer; `gh run watch` keeps polling until his click).
  Rule: workspace `CLAUDE.md`, "Production deploys".
