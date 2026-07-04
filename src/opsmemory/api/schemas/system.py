"""Schemas for system endpoints (health, readiness, statistics)."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = Field(description='"ok" when the process is alive.')
    version: str = Field(description="OpsMemory version.")


class ReadyResponse(BaseModel):
    """Readiness response including dependency checks."""

    status: str = Field(description='"ready" when all dependencies are reachable.')
    checks: dict[str, str] = Field(description="Per-dependency check results.")


class StatsResponse(BaseModel):
    """Platform-wide knowledge statistics."""

    documents: int = Field(description="Documents indexed.")
    repositories: int = Field(description="Repositories known.")
    services: int = Field(description="Services known.")
    teams: int = Field(description="Teams known.")
    incidents: int = Field(description="Incidents recorded.")
    operational_experiences: int = Field(description="Operational experiences learned.")
    connectors: int = Field(description="Connectors configured.")
    memories: int = Field(default=0, description="Semantic memories stored.")
    graph_nodes: int = Field(default=0, description="Knowledge graph nodes.")
    graph_edges: int = Field(default=0, description="Knowledge graph edges.")
