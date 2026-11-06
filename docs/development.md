# Development

How to run and check tfl-mcp on your machine. For deploying, see [deployment/](../deployment/README.md).

## Prerequisites

- Python 3.13 and [Poetry](https://python-poetry.org/) 2.x.
- An `OPENAI_API_KEY`, only if you run the agent in `tfl_status_agent/`.

## Environment variables

Copy `.env.example` to `.env` (gitignored) at the repo root.

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | The agent (`tfl_status_agent/`). It refuses to start without it. |
| `FUNCTION_APP_URL` | The agent and `scripts/verify_deployed_mcp.py`: the hosted MCP server. The agent refuses to start without it. |
| `FUNCTION_MCP_KEY` | The same callers: the MCP extension system key of the Function App. |
| `TFL_STATUS_AGENT_PUBLIC_URL` | Optional. The URL the agent card advertises. Defaults to `http://localhost:8002`. |
| `AGENT_AAD_CLIENT_ID`, `AGENT_AAD_TENANT_ID` | `infra/deploy.sh`, after `scripts/setup-agent-auth.sh` printed them. The agent's Entra app registration; not needed to run anything locally. |

## Install and run the MCP server

```sh
poetry install
poetry run python tfl.py       # stdio MCP server
```

`tfl.py` exposes five tools:

- `get_tfl_status(lines)`: status for one or more named line ids (for example `victoria`, `dlr`, `mildmay`).
- `get_disrupted_lines(modes)`: every line currently disrupted, across tube, DLR, Overground and Elizabeth line by default.
- `find_station(query, modes)`: an `id` and a `journey_id` per station for a place name. Needed before the next two.
- `plan_journey(origin, destination, preference, step_free, when, when_is)`: up to three journey options between two `journey_id`s from `find_station`, reflecting live disruption. `when` is local London time (`2026-09-21T09:00`); omit it to travel now.
- `get_arrivals(stop_id, line_ids)`: the next trains arriving at a station, soonest first.

To use it from Claude Desktop, add a stdio server entry to its MCP configuration:

```json
{
  "mcpServers": {
    "tfl": {
      "command": "poetry",
      "args": ["run", "python", "tfl.py"],
      "cwd": "/path/to/tfl-mcp"
    }
  }
}
```

Any other MCP client works the same way; see the [MCP documentation](https://modelcontextprotocol.io/docs/develop/build-server).

## Run the agent locally

The agent calls the hosted MCP server, so `FUNCTION_APP_URL` and `FUNCTION_MCP_KEY` must be set.

```sh
poetry run uvicorn tfl_status_agent.server:app --port 8002        # local server, no auth locally
poetry run python scripts/verify_agent_card.py                    # discovery check
poetry run python scripts/ask_tfl_status_agent.py "victoria line status"   # real end-to-end call
```

`ask_tfl_status_agent.py` prints progress lines live; pass `--blocking` for the old single response. A real end-to-end call (A2A, LangGraph, MCP tool, live TfL API) takes 15 to 20 seconds or more, so the script sets a 60-second client timeout. Against a deployed agent, pass its FQDN and a bearer token as extra arguments; the script's docstring has the exact usage.

## Checks

```sh
poetry run pytest tests/ -v
poetry run ruff check . && poetry run ruff format --check .
poetry run pyright
```

The Function App has its own isolated environment, never installed through Poetry:

```sh
python3.13 -m venv function_app/.venv
function_app/.venv/bin/pip install -r function_app/requirements.txt pytest==9.1.1
cd function_app && .venv/bin/pytest tests -v
```

The root `tfl_status.py` is the single source of truth; the Function App's copy and the other repo rules are in `CLAUDE.md`, "Gotchas".

`scripts/ci-local.sh` runs all of the above in the order CI does and stops at the first failure; run it before `gh pr ready`. GitHub Actions runs the same checks on pull requests (drafts run only the light ones); see [deployment/github.md](../deployment/github.md).

### Security checks locally

```sh
poetry run pip install pip-audit==2.10.1 bandit==1.9.4
poetry run pip-audit --local
poetry run bandit -r . -lll -x ./tests,./function_app/tests,./.venv,./function_app/.venv
gitleaks git . --redact
```

## Changing tools

Deploy the Function App first, then the agent (why: `CLAUDE.md`, "Gotchas"). How: [deployment/README.md](../deployment/README.md).
