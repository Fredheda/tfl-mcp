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
if [ ! -x function_app/.venv/bin/pytest ]; then
  python3.13 -m venv function_app/.venv
  function_app/.venv/bin/pip install -r function_app/requirements.txt pytest==9.1.1
fi
(cd function_app && .venv/bin/pytest tests -v)

echo "== all local CI checks passed"
