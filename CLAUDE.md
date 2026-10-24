# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> This repo lives inside a multi-repo workspace with its own root `CLAUDE.md`
> (`../CLAUDE.md`, one level up) covering workspace-wide conventions — where
> specs/plans go, the git rule, shared MCP/skill usage. Keep that file's
> per-project facts about this repo in sync whenever they drift from what's
> true here.

**Git:** you may run git freely up to a commit, and push a feature branch and
open a PR. Ask first for `pull`, `fetch`, `rebase`, `reset`, force-push, or
anything on `main`. Reviewing and merging PRs is the user's alone — hand over
the PR URL. Commit messages are 2 lines at most, with no `Co-Authored-By`
trailer. Full rule in the root `CLAUDE.md` linked above.

**Response style:** use the `caveman` skill for responses in this repo —
invoke it before replying, not just when asked.

## What this is

TFL MCP tools: `get_tfl_status` (named lines), `get_disrupted_lines` (all
currently-disrupted lines), `find_station`, `plan_journey` (routes reflecting
live disruption; now / depart-at / arrive-by) and `get_arrivals`. Runs locally
over stdio (`tfl.py`) or deployed as an Azure Function App (`function_app/`).
`tfl_status_agent/` is an A2A agent over these tools; it adds a local
`get_current_time` tool.

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

`function_app/` is a separate deployable. It has its own isolated venv, never
installed through Poetry: `python3.13 -m venv function_app/.venv &&
function_app/.venv/bin/pip install -r function_app/requirements.txt pytest==9.1.1`.
`function_app/tfl_status.py` is a gitignored copy of the root `tfl_status.py`,
made by `scripts/deploy-mcp-tools.sh`; the root file is the single source of truth.

CI (`.github/workflows/ci.yml`) runs all of the above on every pull request and
every push to `main`, as three checks: `backend-test`, `backend-lint`, and
`function-app-test`.

## Deploying

Infra: `infra/deploy.sh`. Code: `scripts/deploy-mcp-tools.sh`. See
`DEPLOYMENT.md`.

`tfl_status_agent/server.py` calls `load_dotenv()` before its other imports
because they read env vars at import time; ruff's E402 is ignored for that
file in `pyproject.toml`.
