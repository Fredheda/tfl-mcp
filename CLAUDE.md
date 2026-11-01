# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> This repo lives inside a multi-repo workspace with its own root `CLAUDE.md`
> (`../CLAUDE.md`, one level up) covering workspace-wide conventions — where
> specs/plans go, the git rule, shared MCP/skill usage. Keep that file's
> per-project facts about this repo in sync whenever they drift from what's
> true here.

**Git:** you may run git freely up to a commit, and push a feature branch and
open a PR. `fetch` and `pull` are fine too (default to `pull --ff-only`). Ask
first for `rebase`, `reset`, force-push, deleting branches, or anything on
`main`. Reviewing and merging PRs is the user's alone — hand over the PR URL.
Other Claude sessions share this workspace: work in your own git worktree,
never the main checkout. Create one with `git worktree add
../.worktrees/<repo>-<slug> -b <branch> origin/main` (or the `EnterWorktree`
tool) and remove it after the PR merges; details in the "Parallel sessions"
section of the root `CLAUDE.md`. Commit messages are 2 lines at most, with no
`Co-Authored-By` trailer. Full rule in the root `CLAUDE.md` linked above.
PR titles and descriptions must not mention Claude Code or link the Claude
session (no "Generated with Claude Code" footer).
After opening a PR, wait for CI to pass (`gh pr checks --watch`), then read
every automated review comment (inline: `gh api repos/Fredheda/tfl-mcp/pulls/<n>/comments`;
summary: `gh pr view <n> --comments`) and address each one, minor notes and
documentation findings included, before handing the PR URL over for review.
Address means fix it in the PR, or reply on the PR with the reason it stays.
Never skip one silently. Each push triggers a new review: read it again.

**Response style:** Use the `caveman` skill. Talk terse at all times, with or
without the skill: chat, Jira comments, GitHub PR and issue text, commits,
specs, plans, docs. Short plain sentences, no filler. Keep code, commands and
error strings exact. Security warnings and irreversible-action confirmations
stay in full clear sentences. Details: workspace `CLAUDE.md`, "Response style".

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

Open PRs as drafts (`gh pr create --draft`). A draft runs only the light CI;
run `scripts/ci-local.sh`, then `gh pr ready` starts the rest and the AI
review. CI runs on PRs only, as `backend` and `function-app-test`. The `main`
ruleset requires those two plus `gitleaks`, `bandit` and `workflow-lint` from
`security.yml`; the workflows are described in `deployment/github.md`.

Env var names (`.env`, see `.env.example`): `OPENAI_API_KEY`, `FUNCTION_APP_URL`,
`FUNCTION_MCP_KEY`; after `scripts/setup-agent-auth.sh` also `AGENT_AAD_CLIENT_ID`
and `AGENT_AAD_TENANT_ID`.

## Gotchas

- `function_app/` is a separate deployable with its own isolated venv, never
  installed through Poetry: `python3.13 -m venv function_app/.venv &&
  function_app/.venv/bin/pip install -r function_app/requirements.txt pytest==9.1.1`.
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
