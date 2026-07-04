# OpsMemory — Demo Flow, Script & Documentation

> **OpsMemory** is the operational-memory layer for engineering teams. Every
> incident becomes a continuously-growing knowledge hub that gets smarter with
> every document, meeting, and lesson — powered by the open-source **Cognee**
> knowledge-graph memory engine.

---

## 1. The 3‑minute video script

Total ≈ 2:55. Each block has **[on screen]** (what to show) and **“spoken”**
(what to say). Aim for a calm, steady pace (~150 wpm).

### 0:00 – 0:25 · About the project
**[on screen]** OpsMemory dashboard — the memory stats (incidents, memories,
graph nodes) and the incident list.

> “This is **OpsMemory** — an operational-memory layer for engineering teams.
> Every organization already solved most of its problems once; the knowledge
> just gets lost across docs, postmortems, and meetings. OpsMemory captures it.
> Instead of a ticket tracker, **each incident is a living knowledge object**
> that keeps getting smarter as you feed it documents, meetings, and lessons.”

### 0:25 – 0:55 · Tech stack & architecture
**[on screen]** Briefly show `docs/architecture.md` diagram, then the
`/api/v1/visualize/graph` Cognee graph button on the dashboard.

> “The backend is **FastAPI on Python 3.13**, with **PostgreSQL + pgvector** as
> the source of truth, an embedded **Kuzu** knowledge graph, and — at the
> center — the open-source **Cognee** engine, which cognifies every write into
> a connected memory graph. Retrieval is hybrid: semantic, graph, keyword, and
> metadata. Reasoning uses **Gemini for embeddings and Groq for generation**,
> fully configurable. It ships as a container, a Helm chart, a CLI, and an MCP
> server — so agents like Claude can query the org’s memory directly.”

### 0:55 – 2:20 · Demo (the core)
**[on screen]** Walk through the live flow below.

> “Let’s watch an incident get smarter. I’ll create an incident —
> *Postgres deadlocks in orders-db*.”
> *(create incident)*
>
> “On the **Data Collection** tab I upload the postmortem — a real Markdown
> file with the SQL we ran.”
> *(upload `incident-01.md`)*
>
> “OpsMemory parses, chunks, embeds, and **cognifies** it. The **Documentation**
> tab is now auto-generated — overview, root cause, resolution, and a
> **Detailed Summary** with the exact commands — every section **cited** back
> to its source. I never wrote this page; it’s regenerated from evidence.”
> *(open Documentation tab, show cited sections + code block)*
>
> “Now I invite the **meeting bot** to our incident review.”
> *(Invite Meeting Bot; note: for the recording, use a pre-processed meeting)*
> “When the meeting ends, Recall.ai sends a webhook, OpsMemory downloads the
> transcript, and an SRE-persona prompt extracts structured incident knowledge
> that **enriches this same incident** — new timeline events, lessons, and an
> operational experience. Meetings are evidence, not standalone notes.”
>
> “Then I just **ask**: *Have we seen Postgres deadlocks before?*”
> *(AI Chat tab)*
> “It answers from this incident’s memory with the root cause, the fix, and
> citations — and the global assistant surfaces **related incidents** it found
> through the knowledge graph.”
> *(show answer + related incidents + confidence)*

### 2:20 – 2:45 · Proof it’s really Cognee
**[on screen]** Click **“Visualize the Cognee Memory”** on the dashboard.

> “And this isn’t a black box — this button renders the **live Cognee knowledge
> graph** behind the platform, so you can verify the memory is real and
> growing.”

### 2:45 – 2:55 · Learning & growth (optional close)
**[on screen]** Back to the dashboard stats ticking up.

> “The biggest lesson building this: **retrieval quality beats prompt tricks**.
> Putting a real memory engine — Cognee — behind everything, with strict
> source citations, is what makes the AI trustworthy. Every lesson compounds.”

---

## 2. Live demo checklist (exact clicks)

Pre-flight:
1. `docker compose up -d --build` (or `make lab`); sign in at
   `http://localhost:8000` with `admin@opsmemory.local` / `opsmemory`.
2. Ensure `OPSMEMORY_GEMINI_API_KEY` + `OPSMEMORY_GROQ_API_KEY` are set so
   answers use real models and Cognee cognifies.
3. Have a postmortem file ready (e.g. `samples/test_incidents/docs/incident-01.md`).
4. (Meetings) Recall requires a live meeting; for a clean recording, invite the
   bot to a short real meeting **before** filming, so the transcript is already
   processed when you demo — or narrate the flow over the Meeting Intelligence page.

Flow:
1. **Dashboard** → note the stat tiles.
2. **New incident** → “Postgres deadlocks in orders-db”, SEV3 → Create.
3. **Data Collection** tab → **Upload Document** → *Upload file* → pick the
   `.md`/`.pdf` postmortem → Upload & ingest. (Toast: “Learned — N memories”.)
4. **Documentation** tab → show Overview, Root Cause, Resolution, and
   **Detailed Summary** (full content + SQL) with source chips. Click a chip.
5. **Data Collection** → **Invite Meeting Bot** (or show a processed meeting) →
   point out the **Timeline** filling in on the Documentation tab.
6. **AI Chat** tab → “What caused this and how did we fix it?” → show the
   grounded answer + citations + confidence.
7. **Assistant** (global) → “Have we experienced Postgres deadlocks before?” →
   show the answer + **Related incidents**.
8. **Dashboard** → **Visualize the Cognee Memory** → the live graph.

---

## 3. About the project (written)

Engineering orgs regenerate the same investigations because past solutions
aren’t discoverable. OpsMemory turns fragmented signals — docs, runbooks, ADRs,
postmortems, and **incident meetings** — into a connected, queryable
organizational memory. It is **not** a doc search engine or a plain RAG bot:

- **Incidents are the primary memory object.** Documents, meetings, memories,
  and operational experiences all link to an incident and enrich it over time.
- **Living documentation.** Regenerated from evidence on every ingestion, with
  a per-section **source citation** back to the originating document/meeting.
- **Meeting Intelligence.** A Recall.ai bot joins Google Meet / Zoom / Teams;
  on `bot.done`, OpsMemory downloads the transcript and an SRE-persona prompt
  extracts structured incident knowledge that enriches the incident (or
  auto-creates and AI-names a new one).
- **Continuous learning.** Teaching pipeline with duplicate detection —
  repeated lessons reinforce confidence instead of duplicating memory.

## 4. Tech stack & architecture

```
Connectors (files, HTTP docs, Recall.ai meetings)
      │  parse → chunk → relationships
      ▼
PostgreSQL + pgvector  ── source of truth / traceable substrate (ADR-0003)
      │
      ▼
Cognee  ── central memory engine: cognifies every write into a knowledge graph (ADR-0002)
Kuzu    ── embedded relationship graph
      │
      ▼
Hybrid Retrieval (semantic + graph + keyword + metadata, intent-routed)
      │
      ▼
AI Agent  ── Gemini embeddings + Groq reasoning, citations + confidence (ADR-0006)
      │
      ▼
REST API · Web app (SPA) · CLI · MCP server
```

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2.
- **Memory:** Cognee (central, compulsory) over PostgreSQL + pgvector; Kuzu graph.
- **AI:** configurable per role — Gemini (embeddings + optional reasoning), Groq
  (reasoning), Anthropic; keyless fallbacks for dev/tests.
- **Auth:** session tokens behind a provider-agnostic interface (OAuth-ready).
- **Delivery:** Docker Compose, Helm chart + Kind lab (`make lab`), Typer CLI,
  and an MCP server (`opsmemory-mcp`) exposing memory as tools to AI agents.
- **Quality:** ruff, mypy (strict), pytest (116 tests) — all green; migrations
  validated on real PostgreSQL.

Design decisions are recorded as ADRs in [`docs/adr/`](adr/): Kuzu (0001),
Cognee-as-engine (0002), Postgres source-of-truth (0003), provider strategy
(0006), incident hub + auth (0008).

## 5. Learning & growth

- **A real memory engine beats prompt engineering.** Wiring Cognee behind every
  write, with pgvector as the traceable substrate, made answers grounded and
  verifiable — the “Visualize the Cognee Memory” button proves it live.
- **Evidence-first UX builds trust.** Regenerated, cited documentation means
  users see *why* an answer is what it is, not just the answer.
- **Ports over vendors.** Cognee, the graph store, and AI providers all sit
  behind interfaces, so the platform degrades gracefully (keyless mode) and
  swaps components without touching the core.
- **Ops reality.** Real deployment taught concrete lessons — e.g. a
  `ReadWriteOnce` volume + rolling update needs a `Recreate` strategy, and an
  ingress `custom-http-errors` annotation can mask a backend 503 as a 404.
