# Querying and Visualizing Cognee in OpsMemory

OpsMemory (formerly OpsMemory) uses **Cognee** as its central memory engine. Every piece of knowledge ingested is automatically cognified into a structured knowledge graph, backed by a robust PostgreSQL and pgvector substrate.

This guide explains how to directly query Cognee, fetch data from the relational database, and generate visual projections for specific incidents.

## 1. Querying Cognee Directly

You can query the Cognee knowledge graph directly using Python. Cognee supports different search types, such as Graph Completion, to traverse edges and provide contextual answers.

```python
import asyncio
import os
import cognee
from cognee.modules.search.types import SearchType
from opsmemory.core.config import get_settings

async def query_cognee(query: str):
    settings = get_settings()
    
    # Configure Cognee providers
    os.environ.setdefault("LLM_PROVIDER", "gemini")
    os.environ.setdefault("LLM_API_KEY", settings.gemini_api_key)
    os.environ.setdefault("LLM_MODEL", f"gemini/{settings.gemini_model}")
    
    # Run a Graph Completion search
    results = await cognee.search(
        query_text=query,
        query_type=SearchType.GRAPH_COMPLETION,
        top_k=5
    )
    
    print("Graph Results:")
    for res in results:
        # Extract the resolved value or text from the node
        value = getattr(res, "value", None) or getattr(res, "text", None) or res
        print(f"- {value}")

if __name__ == "__main__":
    asyncio.run(query_cognee("What caused the kubernetes OOM evictions?"))
```

## 2. Querying the Database (Source of Truth)

Because OpsMemory uses PostgreSQL as the source of truth, all parsed incidents and extracted `OperationalExperience` nodes live in standard relational tables before they are projected into the graph.

You can query the database directly using SQLAlchemy:

```python
import asyncio
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from opsmemory.api.app import app
from opsmemory.db.models import Incident, OperationalExperience

async def fetch_incident(incident_id: UUID):
    db_session_factory = app.state.session_factory
    
    async with db_session_factory() as db:
        # Fetch an Incident and its related Operational Experiences
        stmt = (
            select(Incident)
            .options(selectinload(Incident.experiences))
            .where(Incident.id == incident_id)
        )
        result = await db.execute(stmt)
        incident = result.scalar_one_or_none()
        
        if incident:
            print(f"Incident: {incident.title}")
            for exp in incident.experiences:
                print(f"  Root Cause: {exp.root_cause}")
                print(f"  Resolution: {exp.resolution}")
        else:
            print("Incident not found.")
```

## 3. Visualizing Data for an Incident

You can visualize the entire knowledge graph, or visualize the memory provenance (how data flows from users to agents to files). 

To visualize the knowledge graph and provenance inside your container, you can run a python script like this:

```python
import asyncio
import os
import cognee
from pathlib import Path
from opsmemory.core.config import get_settings

async def generate_visualizations():
    settings = get_settings()
    
    # 1. Point Cognee to the correct storage path used by OpsMemory
    storage = Path(settings.graph_db_path).parent / "cognee"
    cognee.config.system_root_directory(str(storage / "system"))
    cognee.config.data_root_directory(str(storage / "data"))
    
    # 2. Generate the overarching Knowledge Graph visualization
    graph_path = os.path.abspath("./cognee_graph.html")
    await cognee.visualize_graph(graph_path)
    print(f"Knowledge Graph saved to: {graph_path}")
    
    # 3. Generate Memory Provenance (Data Flow & Origin)
    prov_path = os.path.abspath("./memory_provenance.html")
    await cognee.visualize_memory_provenance(prov_path, include_memory=True)
    print(f"Memory Provenance saved to: {prov_path}")

if __name__ == "__main__":
    asyncio.run(generate_visualizations())
```

Run this inside your API container:
```bash
docker-compose exec api python /workspace/generate_visualizations.py
```
And then copy them out to your host:
```bash
docker cp $(docker-compose ps -q api):/app/cognee_graph.html ./
docker cp $(docker-compose ps -q api):/app/memory_provenance.html ./
```

> **Note:** The `visualize_graph` tool automatically renders the connections for all ingested entities. When you query or view an incident in the UI, OpsMemory retrieves the specific `OperationalExperience` nodes linked to that incident ID in the database and the graph.
