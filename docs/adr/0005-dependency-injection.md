# ADR-0005: Dependency injection via FastAPI Depends + app.state composition root

Date: 2026-07-03 · Status: Accepted

## Context

The engineering standards call for dependency injection ("Dependency
Injector or equivalent"). The `dependency-injector` library adds a container
DSL, wiring decorators, and a compiled dependency that historically lags new
Python releases.

## Decision

Use **constructor injection with FastAPI's `Depends` as the composition
mechanism**:

- Services (e.g. `StatsService`) take their dependencies as constructor
  arguments and know nothing about FastAPI.
- `opsmemory/api/dependencies.py` is the composition root: it builds
  request-scoped objects from long-lived resources stored on `app.state`
  (engine, session factory, settings), created in the lifespan handler.
- Tests substitute any dependency by replacing the `app.state` attribute or
  overriding the provider — no monkeypatching.
- The CLI and future worker compose the same service classes directly.

## Consequences

- Zero extra dependencies; fully typed; idiomatic FastAPI.
- If wiring complexity ever outgrows this (e.g. many worker entry points),
  a container library can be introduced without changing service classes,
  because services only use constructor injection.
