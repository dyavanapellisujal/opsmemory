# Development Guide

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker (for PostgreSQL and image builds)
- Helm (for chart linting)

## Setup

```bash
make install        # uv sync — creates .venv with all dev tools
cp .env.example .env
```

## Everyday workflow

```bash
make db-up          # start pgvector PostgreSQL in Docker
make migrate        # apply Alembic migrations
make api            # run the API with auto-reload  (http://localhost:8000/docs)

uv run opsmemory health
uv run opsmemory stats -o json
```

## Quality gates

Every milestone must pass all gates before it is considered complete:

```bash
make check          # lint + typecheck + test + helm-lint
make docker-build   # container image builds
```

Individually:

| Gate | Command |
|------|---------|
| Lint | `make lint` (ruff check + format check) |
| Types | `make typecheck` (mypy strict) |
| Tests | `make test` (pytest, async) |
| Helm | `make helm-lint` |
| Image | `make docker-build` |

## Database migrations

Schema changes are migration-driven — never create tables manually.

```bash
# 1. Edit ORM models under src/opsmemory/db/models/
# 2. Autogenerate a migration (requires a running, up-to-date database):
make revision m="add memory tables"
# 3. Review the generated file under migrations/versions/ — always.
# 4. Apply and verify round-trip:
make migrate
uv run alembic downgrade -1 && uv run alembic upgrade head
```

Notes:

- Tests run against in-memory SQLite for speed; cross-dialect types live in
  `opsmemory/db/types.py`. Migrations themselves target PostgreSQL.
- `uv run alembic check` verifies models and migrations are in sync.

## Testing conventions

- Async tests via `pytest-asyncio` (`asyncio_mode = auto` — no decorators needed).
- API tests use `httpx.ASGITransport` against the app factory; the test app's
  session factory is swapped for SQLite in `tests/conftest.py`.
- CLI tests use Typer's `CliRunner` with `respx` mocking the HTTP layer.
- Every new feature ships with tests in the same milestone.

## Project conventions

- `src/` layout; import root is `opsmemory`.
- Strict typing (`mypy --strict`) and Google-style docstrings on all public
  functions, classes, and modules (enforced by ruff's `D` rules).
- Configuration only via `opsmemory.core.config.Settings` — never read
  `os.environ` elsewhere.
- Architectural decisions are recorded in `docs/adr/` before or with the
  code that implements them.
