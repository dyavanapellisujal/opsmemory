"""OpsMemory CLI entry point.

Command groups mirror the PRD's CLI structure: ingest, connectors, search,
ask, teach, graph, services, incidents, repositories, jobs, stats, config,
and an interactive shell.
"""

import re
import time
from enum import IntEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.panel import Panel

import opsmemory
from opsmemory.cli.client import APIClient, APIClientError
from opsmemory.cli.output import OutputFormat, console, render
from opsmemory.core.config import get_settings

app = typer.Typer(
    name="opsmemory",
    help="OpsMemory — The Operational Memory Layer for Engineering Teams.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

config_app = typer.Typer(help="Inspect and validate OpsMemory configuration.")
connectors_app = typer.Typer(help="Manage knowledge source connectors.")
app.add_typer(config_app, name="config")
app.add_typer(connectors_app, name="connectors")


class ExitCode(IntEnum):
    """CLI exit codes (UNIX conventions, per the PRD)."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_ARGUMENTS = 2
    AUTHENTICATION_FAILURE = 3
    CONNECTOR_ERROR = 4
    RETRIEVAL_ERROR = 5
    MEMORY_UPDATE_FAILED = 6


OutputOption = Annotated[OutputFormat, typer.Option("--output", "-o", help="Output format.")]


def _client() -> APIClient:
    """Build the API client from settings."""
    return APIClient(get_settings())


def _fail(exc: APIClientError, code: ExitCode = ExitCode.GENERAL_ERROR) -> typer.Exit:
    """Print an API error and return an Exit to raise."""
    console.print(f"[red]error:[/red] {exc.message}")
    return typer.Exit(code=code)


def _find_connector(client: APIClient, name: str) -> dict[str, Any]:
    """Resolve a connector by name via the API."""
    for connector in client.get("/api/v1/connectors"):
        if connector["name"] == name:
            return dict(connector)
    console.print(f"[red]error:[/red] no connector named {name!r}")
    raise typer.Exit(code=ExitCode.CONNECTOR_ERROR)


def _wait_for_job(client: APIClient, job_id: str) -> dict[str, Any]:
    """Poll a job until it finishes, rendering progress."""
    with console.status("Ingesting..."):
        while True:
            job = client.get(f"/api/v1/jobs/{job_id}")
            if job["status"] in ("completed", "failed"):
                return dict(job)
            time.sleep(1.0)


# --- System commands -------------------------------------------------------


@app.command()
def version() -> None:
    """Show the OpsMemory version."""
    console.print(f"OpsMemory v{opsmemory.__version__}")


@app.command()
def health(output: OutputOption = OutputFormat.TABLE) -> None:
    """Check API liveness and readiness."""
    client = _client()
    try:
        live = client.get("/health")
        ready = client.get("/ready")
    except APIClientError as exc:
        raise _fail(exc) from exc
    render({**live, **ready}, output, title="OpsMemory Health")
    if ready.get("status") != "ready":
        raise typer.Exit(code=ExitCode.GENERAL_ERROR)


@app.command()
def stats(output: OutputOption = OutputFormat.TABLE) -> None:
    """Show platform knowledge statistics."""
    try:
        data = _client().get("/api/v1/stats")
    except APIClientError as exc:
        raise _fail(exc) from exc
    render(data, output, title="OpsMemory Statistics")


@config_app.command("show")
def config_show(output: OutputOption = OutputFormat.TABLE) -> None:
    """Show the resolved configuration (API keys redacted)."""
    settings = get_settings()
    data = settings.model_dump(mode="json")
    for key in list(data):
        if key.endswith("_api_key") and data[key]:
            data[key] = "***"
    data["resolved_llm_provider"] = settings.resolve_llm_provider()
    data["resolved_embedding_provider"] = settings.resolve_embedding_provider()
    render(data, output, title="OpsMemory Configuration")


@config_app.command("validate")
def config_validate() -> None:
    """Validate configuration and show the resolved AI providers."""
    settings = get_settings()
    console.print(
        f"[green]Configuration valid.[/green] environment={settings.environment} "
        f"llm={settings.resolve_llm_provider()} "
        f"embeddings={settings.resolve_embedding_provider()} "
        f"memory={settings.memory_engine}"
    )


# --- Ingestion --------------------------------------------------------------


@app.command()
def ingest(
    target: Annotated[str, typer.Argument(help="Local directory or documentation URL.")],
    name: Annotated[str | None, typer.Option(help="Connector name (derived if omitted).")] = None,
    wait: Annotated[bool, typer.Option(help="Wait for ingestion to finish.")] = True,
    output: OutputOption = OutputFormat.TABLE,
) -> None:
    """Ingest a local folder or a documentation website.

    Registers (or reuses) a connector for the target and synchronizes it.
    """
    client = _client()
    if target.startswith(("http://", "https://")):
        connector_type, config = "http_docs", {"url": target}
    else:
        path = Path(target).expanduser().resolve()
        if not path.is_dir():
            console.print(f"[red]error:[/red] {target} is not a directory or URL")
            raise typer.Exit(code=ExitCode.INVALID_ARGUMENTS)
        connector_type, config = "local_files", {"path": str(path)}
    connector_name = name or re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")[:60]

    try:
        existing = [c for c in client.get("/api/v1/connectors") if c["name"] == connector_name]
        if existing:
            connector = existing[0]
        else:
            connector = client.post(
                "/api/v1/connectors",
                json={"name": connector_name, "type": connector_type, "config": config},
            )
        sync = client.post(f"/api/v1/connectors/{connector['id']}/sync")
    except APIClientError as exc:
        raise _fail(exc, ExitCode.CONNECTOR_ERROR) from exc

    if not wait:
        render({"connector": connector_name, "job_id": sync["job_id"]}, output)
        return
    job = _wait_for_job(client, sync["job_id"])
    if job["status"] == "failed":
        console.print(f"[red]Ingestion failed:[/red] {job.get('error')}")
        raise typer.Exit(code=ExitCode.CONNECTOR_ERROR)
    render({"connector": connector_name, **job["stats"]}, output, title="Ingestion complete")


# --- Connectors -------------------------------------------------------------


@connectors_app.command("list")
def connectors_list(output: OutputOption = OutputFormat.TABLE) -> None:
    """List configured connectors."""
    try:
        data = _client().get("/api/v1/connectors")
    except APIClientError as exc:
        raise _fail(exc) from exc
    render(data, output, title="Connectors", columns=["name", "type", "status", "last_sync_at"])


@connectors_app.command("add")
def connectors_add(
    name: str,
    type_: Annotated[str, typer.Argument(metavar="TYPE", help="local_files or http_docs.")],
    path: Annotated[str | None, typer.Option(help="Directory for local_files.")] = None,
    url: Annotated[str | None, typer.Option(help="Start URL for http_docs.")] = None,
    output: OutputOption = OutputFormat.TABLE,
) -> None:
    """Register a new connector."""
    config: dict[str, Any] = {}
    if path:
        config["path"] = str(Path(path).expanduser().resolve())
    if url:
        config["url"] = url
    try:
        connector = _client().post(
            "/api/v1/connectors", json={"name": name, "type": type_, "config": config}
        )
    except APIClientError as exc:
        raise _fail(exc, ExitCode.CONNECTOR_ERROR) from exc
    render(connector, output, title="Connector registered")


@connectors_app.command("remove")
def connectors_remove(name: str) -> None:
    """Remove a connector by name."""
    client = _client()
    connector = _find_connector(client, name)
    try:
        client.delete(f"/api/v1/connectors/{connector['id']}")
    except APIClientError as exc:
        raise _fail(exc, ExitCode.CONNECTOR_ERROR) from exc
    console.print(f"Removed connector [bold]{name}[/bold].")


@connectors_app.command("sync")
def connectors_sync(
    name: str,
    wait: Annotated[bool, typer.Option(help="Wait for ingestion to finish.")] = True,
    output: OutputOption = OutputFormat.TABLE,
) -> None:
    """Trigger synchronization for a connector."""
    client = _client()
    connector = _find_connector(client, name)
    try:
        sync = client.post(f"/api/v1/connectors/{connector['id']}/sync")
    except APIClientError as exc:
        raise _fail(exc, ExitCode.CONNECTOR_ERROR) from exc
    if not wait:
        render({"connector": name, "job_id": sync["job_id"]}, output)
        return
    job = _wait_for_job(client, sync["job_id"])
    render({"connector": name, "status": job["status"], **(job.get("stats") or {})}, output)


@connectors_app.command("status")
def connectors_status(output: OutputOption = OutputFormat.TABLE) -> None:
    """Show connector health."""
    client = _client()
    try:
        rows = []
        for connector in client.get("/api/v1/connectors"):
            check = client.get(f"/api/v1/connectors/{connector['id']}/health")
            rows.append(
                {
                    "name": connector["name"],
                    "type": connector["type"],
                    "healthy": check["healthy"],
                    "message": check["message"],
                }
            )
    except APIClientError as exc:
        raise _fail(exc) from exc
    render(rows, output, title="Connector status")


# --- Knowledge --------------------------------------------------------------


@app.command()
def search(query: str, output: OutputOption = OutputFormat.TABLE) -> None:
    """Search organizational knowledge (hybrid retrieval, no LLM)."""
    try:
        result = _client().post("/api/v1/search", json={"query": query})
    except APIClientError as exc:
        raise _fail(exc, ExitCode.RETRIEVAL_ERROR) from exc
    if output is not OutputFormat.TABLE:
        render(result, output)
        return
    console.print(f"[bold]Intent:[/bold] {result['intent']}")
    if result["memories"]:
        rows = [
            {"score": f"{m['score']:.2f}", "kind": m["kind"], "content": m["content"][:120]}
            for m in result["memories"]
        ]
        render(rows, output, title="Memories")
    if result["experiences"]:
        rows = [
            {"problem": e["problem"][:80], "resolution": (e["resolution"] or "")[:80]}
            for e in result["experiences"]
        ]
        render(rows, output, title="Operational experiences")
    if result["documents"]:
        rows = [{"title": d["title"], "source": d["source"]} for d in result["documents"]]
        render(rows, output, title="Documents")
    if result["graph_facts"]:
        rows = [
            {"from": g["source"], "relation": g["relation"], "to": g["target"]}
            for g in result["graph_facts"]
        ]
        render(rows, output, title="Relationships")


@app.command()
def ask(question: str, output: OutputOption = OutputFormat.TABLE) -> None:
    """Ask a natural-language question (retrieval + AI reasoning)."""
    try:
        result = _client().post("/api/v1/chat", json={"message": question})
    except APIClientError as exc:
        raise _fail(exc, ExitCode.RETRIEVAL_ERROR) from exc
    if output is not OutputFormat.TABLE:
        render(result, output)
        return
    console.print(Panel(result["answer"], title="OpsMemory", border_style="cyan"))
    console.print(f"[dim]confidence: {result['confidence']:.2f} · intent: {result['intent']}[/dim]")
    if result["citations"]:
        rows = [{"kind": c["kind"], "title": c["title"]} for c in result["citations"]]
        render(rows, output, title="Evidence")


@app.command()
def teach(
    content: Annotated[str | None, typer.Argument(help="The lesson to teach.")] = None,
    file: Annotated[Path | None, typer.Option(help="Read the lesson from a file.")] = None,
    author: Annotated[str | None, typer.Option(help="Contributor name.")] = None,
    output: OutputOption = OutputFormat.TABLE,
) -> None:
    """Teach OpsMemory a new operational experience."""
    if file is not None:
        content = file.read_text(encoding="utf-8")
    if not content:
        content = typer.prompt("Describe the operational experience")
    try:
        result = _client().post("/api/v1/experiences", json={"content": content, "author": author})
    except APIClientError as exc:
        raise _fail(exc, ExitCode.MEMORY_UPDATE_FAILED) from exc
    render(
        {
            "result": result["message"],
            "problem": result["problem"],
            "root_cause": result["root_cause"],
            "resolution": result["resolution"],
            "lesson": result["lessons_learned"],
            "confidence": result["confidence"],
        },
        output,
        title="Learned",
    )


@app.command()
def graph(
    entity: str,
    dependencies: Annotated[bool, typer.Option(help="Show only depends_on edges.")] = False,
    depth: Annotated[int, typer.Option(min=1, max=5)] = 2,
    output: OutputOption = OutputFormat.TABLE,
) -> None:
    """Explore the knowledge graph around an entity."""
    path = (
        f"/api/v1/graph/services/{entity}/dependencies?depth={depth}"
        if dependencies
        else f"/api/v1/graph/{entity}?depth={depth}"
    )
    try:
        result = _client().get(path)
    except APIClientError as exc:
        raise _fail(exc, ExitCode.RETRIEVAL_ERROR) from exc
    rows = [
        {"from": e["source"], "relation": e["relation"], "to": e["target"]} for e in result["edges"]
    ]
    render(rows, output, title=f"Graph around {result['entity']}")


@app.command()
def services(output: OutputOption = OutputFormat.TABLE) -> None:
    """List known services."""
    try:
        data = _client().get("/api/v1/services")
    except APIClientError as exc:
        raise _fail(exc) from exc
    render(data, output, title="Services", columns=["name", "owner_team", "environment"])


@app.command()
def incidents(output: OutputOption = OutputFormat.TABLE) -> None:
    """List incidents."""
    try:
        data = _client().get("/api/v1/incidents")
    except APIClientError as exc:
        raise _fail(exc) from exc
    render(data, output, title="Incidents", columns=["title", "severity", "status"])


@app.command()
def repositories(output: OutputOption = OutputFormat.TABLE) -> None:
    """List repositories."""
    try:
        data = _client().get("/api/v1/repositories")
    except APIClientError as exc:
        raise _fail(exc) from exc
    render(data, output, title="Repositories", columns=["name", "provider", "url"])


@app.command()
def jobs(output: OutputOption = OutputFormat.TABLE) -> None:
    """List ingestion jobs."""
    try:
        data = _client().get("/api/v1/jobs")
    except APIClientError as exc:
        raise _fail(exc) from exc
    render(data, output, title="Jobs", columns=["id", "status", "stats", "finished_at"])


@app.command()
def shell() -> None:
    """Interactive shell: ask questions, teach with 'teach: <lesson>'."""
    console.print(
        f"[bold cyan]OpsMemory v{opsmemory.__version__}[/bold cyan] — "
        "ask anything; prefix with 'teach:' to contribute; 'exit' to quit."
    )
    client = _client()
    while True:
        try:
            line = console.input("[bold]> [/bold]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.lower() in {"exit", "quit"}:
            break
        try:
            if line.lower().startswith("teach:"):
                result = client.post("/api/v1/experiences", json={"content": line[6:].strip()})
                console.print(f"[green]{result['message']}[/green]")
            else:
                result = client.post("/api/v1/chat", json={"message": line})
                console.print(Panel(result["answer"], border_style="cyan"))
                console.print(f"[dim]confidence: {result['confidence']:.2f}[/dim]")
        except APIClientError as exc:
            console.print(f"[red]error:[/red] {exc.message}")


if __name__ == "__main__":
    app()
