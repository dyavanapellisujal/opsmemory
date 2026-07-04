# ADR-0004: Toolchain — uv, src layout, ruff, mypy strict, pytest-asyncio

Date: 2026-07-03 · Status: Accepted

## Context

The project targets Python 3.13+, strong typing, high test coverage, and
repeatable builds across local, CI, and container environments.

## Decision

- **uv** for dependency and environment management (`uv.lock` committed;
  Docker build uses `uv sync --frozen`).
- **src layout** (`src/opsmemory`) so tests always run against the installed
  package, never the working directory.
- **ruff** for linting *and* formatting, including pydocstyle (`D`,
  Google convention) to enforce the "every public symbol documented" rule.
- **mypy --strict** with the pydantic plugin.
- **pytest + pytest-asyncio** (`asyncio_mode = auto`); unit tests run on
  in-memory SQLite via cross-dialect types, migrations are validated
  against real PostgreSQL.
- Verified before adoption: the full future dependency set (cognee 1.2.2,
  kuzu 0.11.3, FastAPI, SQLAlchemy 2, pgvector) resolves on Python 3.13.

## Consequences

- One-command reproducible setup (`make install`) and fast CI.
- SQLite-based tests require dialect-portable column types
  (`opsmemory/db/types.py`), a small tax for a large speed win.
