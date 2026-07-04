"""CLI output rendering: rich tables by default, JSON/YAML for automation."""

import json
from enum import StrEnum
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

console = Console()


class OutputFormat(StrEnum):
    """Supported CLI output formats."""

    TABLE = "table"
    JSON = "json"
    YAML = "yaml"


def render(
    data: dict[str, Any] | list[dict[str, Any]],
    fmt: OutputFormat,
    *,
    title: str | None = None,
    columns: list[str] | None = None,
) -> None:
    """Render a mapping or a list of mappings in the requested output format.

    Args:
        data: Key/value data (rendered as field/value rows) or a list of
            records (rendered as a table with one column per key).
        fmt: Output format selected by the user.
        title: Optional table title (ignored for JSON/YAML).
        columns: For record lists, which keys to show as columns (table only).
    """
    # JSON/YAML are for automation: emit plain text with no styling or wrapping.
    if fmt is OutputFormat.JSON:
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    if fmt is OutputFormat.YAML:
        typer.echo(yaml.safe_dump(data, sort_keys=False, default_flow_style=False), nl=False)
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    if isinstance(data, list):
        if not data:
            console.print(f"[dim]No {title or 'results'}.[/dim]")
            return
        keys = columns or list(data[0].keys())
        for key in keys:
            table.add_column(key)
        for row in data:
            table.add_row(*(_format_value(row.get(key)) for key in keys))
    else:
        table.add_column("Field")
        table.add_column("Value")
        for key, value in data.items():
            table.add_row(str(key), _format_value(value))
    console.print(table)


def _format_value(value: Any) -> str:
    """Format a single cell value for table output."""
    if isinstance(value, dict | list):
        return json.dumps(value, default=str)
    return str(value)
