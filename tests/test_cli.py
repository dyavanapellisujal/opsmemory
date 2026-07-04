"""Tests for the CLI commands."""

import json

import httpx
import respx
from httpx import Response
from typer.testing import CliRunner

import opsmemory
from opsmemory.cli.main import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert opsmemory.__version__ in result.output


def test_config_show_json() -> None:
    result = runner.invoke(app, ["config", "show", "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "database_url" in data


def test_config_validate() -> None:
    result = runner.invoke(app, ["config", "validate"])
    assert result.exit_code == 0
    assert "Configuration valid" in result.output


@respx.mock
def test_stats_json() -> None:
    respx.get("http://localhost:8000/api/v1/stats").mock(
        return_value=Response(200, json={"documents": 3, "services": 2})
    )
    result = runner.invoke(app, ["stats", "--output", "json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"documents": 3, "services": 2}


@respx.mock
def test_health_healthy() -> None:
    respx.get("http://localhost:8000/health").mock(
        return_value=Response(200, json={"status": "ok", "version": "0.1.0"})
    )
    respx.get("http://localhost:8000/ready").mock(
        return_value=Response(200, json={"status": "ready", "checks": {"database": "ok"}})
    )
    result = runner.invoke(app, ["health", "--output", "yaml"])
    assert result.exit_code == 0
    assert "status: ready" in result.output


@respx.mock
def test_health_api_unreachable_exits_nonzero() -> None:
    respx.get("http://localhost:8000/health").mock(side_effect=httpx.ConnectError)
    result = runner.invoke(app, ["health"])
    assert result.exit_code == 1
