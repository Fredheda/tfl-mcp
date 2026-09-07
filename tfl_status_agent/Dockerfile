# Build context is the repo root: `docker build -f tfl_status_agent/Dockerfile .`
FROM python:3.13-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir "poetry>=2.0,<3.0" \
    && poetry config virtualenvs.in-project true

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-interaction --no-ansi

COPY tfl_status_agent/ ./tfl_status_agent/

FROM python:3.13-slim

WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/tfl_status_agent ./tfl_status_agent
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8002
CMD ["uvicorn", "tfl_status_agent.server:app", "--host", "0.0.0.0", "--port", "8002"]
