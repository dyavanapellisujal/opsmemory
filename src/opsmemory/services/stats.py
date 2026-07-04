"""Platform statistics service."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opsmemory.db.base import Base
from opsmemory.db.models import (
    Connector,
    Document,
    Incident,
    Memory,
    OperationalExperience,
    Repository,
    Service,
    Team,
)


class StatsService:
    """Computes platform-wide knowledge statistics.

    Statistics are computed live from the metadata store; as later
    milestones add memories, embeddings, and graph storage, their counts
    are added here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _count(self, model: type[Base]) -> int:
        """Count rows of an ORM model."""
        result = await self._session.execute(select(func.count()).select_from(model))
        return int(result.scalar_one())

    async def collect(self) -> dict[str, int]:
        """Collect all platform statistics.

        Returns:
            Mapping of statistic name to count.
        """
        return {
            "documents": await self._count(Document),
            "repositories": await self._count(Repository),
            "services": await self._count(Service),
            "teams": await self._count(Team),
            "incidents": await self._count(Incident),
            "operational_experiences": await self._count(OperationalExperience),
            "connectors": await self._count(Connector),
            "memories": await self._count(Memory),
        }
