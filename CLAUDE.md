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
After opening a PR, wait for CI to pass (`gh pr checks --watch`), then read the
LLM review comments and address them, before handing the PR URL over for review.

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

`.github/workflows/claude-review.yml` posts an AI security-first review when a
PR is opened and on every push to it; the repo owner can also request one by
commenting `@claude`. It is comment-only and authenticates with the
`CLAUDE_CODE_OAUTH_TOKEN` repo secret, which expires about 2027-10-24: renew
with `claude setup-token`, then `gh secret set CLAUDE_CODE_OAUTH_TOKEN`. If
subscription auth is refused, switch the action input to `anthropic_api_key`.

## Deploying

Infra: `infra/deploy.sh`. Code: the manual **Deploy functions** workflow on
GitHub (`main` only; rollback = an older SHA), with `scripts/deploy-mcp-tools.sh`
as the laptop fallback. See `DEPLOYMENT.md`.

`tfl_status_agent/server.py` calls `load_dotenv()` before its other imports
because they read env vars at import time; ruff's E402 is ignored for that
file in `pyproject.toml`.
