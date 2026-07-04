# --- Build stage: install dependencies with uv ---
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra cognee

COPY src ./src
COPY README.md alembic.ini ./
COPY migrations ./migrations
COPY samples ./samples
RUN uv sync --frozen --no-dev --extra cognee

# --- Runtime stage ---
FROM python:3.13-slim

RUN groupadd -r opsmemory && useradd -r -g opsmemory opsmemory

WORKDIR /app
COPY --from=builder /app /app

# Writable home for the embedded Kuzu graph (derived data, rebuildable).
RUN mkdir -p /app/data && chown -R opsmemory:opsmemory /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    OPSMEMORY_GRAPH_DB_PATH=/app/data/graph

# USER opsmemory
USER root
EXPOSE 8000

CMD ["uvicorn", "opsmemory.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
