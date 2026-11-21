#!/usr/bin/env bash
# Runs every check .github/workflows/ci.yml runs, in the same order, and stops
# at the first failure. Run it before `gh pr ready`.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== backend: tests, lint, format, types"
poetry run pytest tests/ -v
poetry run ruff check .
poetry run ruff format --check .
poetry run pyright

# function_app/ is a separate deployable with its own isolated venv.
echo "== function_app tests"
python3.13 -m venv --clear function_app/.venv
function_app/.venv/bin/pip install pip==26.2.2
function_app/.venv/bin/pip install --no-deps -r function_app/requirements.txt
function_app/.venv/bin/pip check
PIP_UPLOADED_PRIOR_TO=P14D function_app/.venv/bin/pip install pytest==9.1.1
(cd function_app && .venv/bin/pytest tests -v)

echo "== all local CI checks passed"
