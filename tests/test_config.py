"""Tests for application configuration."""

import pytest

from opsmemory.core.config import Environment, Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.api_port == 8000
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPSMEMORY_ENVIRONMENT", "production")
    monkeypatch.setenv("OPSMEMORY_API_PORT", "9000")
    monkeypatch.setenv("OPSMEMORY_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")
    settings = Settings(_env_file=None)
    assert settings.environment is Environment.PRODUCTION
    assert settings.api_port == 9000
    assert settings.database_url.endswith("/x")


def test_sync_database_url() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@db:5432/x")
    assert settings.sync_database_url == "postgresql+psycopg://u:p@db:5432/x"
