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
**[on screen]** OpsMemory dashboard — show the memory stats (incidents, memories, graph nodes) and the incident list.

> **Spoken:** “Hi everyone, this is **OpsMemory** — an operational-memory layer for engineering teams. Every organization has already solved most of its problems at least once, but that knowledge gets lost across docs, postmortems, and meetings. We built OpsMemory to capture it. Instead of a basic ticket tracker, **each incident here is a living knowledge object** that continuously learns and gets smarter as you feed it documents, meetings, and lessons.”

### 0:25 – 0:55 · Tech stack & architecture
**[on screen]** Briefly flash the `docs/architecture.md` diagram or the UI, then click the **Visualize the Cognee Memory** button on the dashboard.

> **Spoken:** “Under the hood, our backend is **FastAPI** with **PostgreSQL and pgvector** serving as our traceable source of truth. But the real magic happens at the center: we use the open-source **Cognee** engine to cognify every piece of data into a connected memory graph. For retrieval, we use a hybrid approach of semantic, graph, and keyword search. Finally, we use **Gemini for embeddings and Groq for reasoning**. We’ve also packaged it to run anywhere—Docker, Helm charts for Kubernetes, and even as an MCP server for agents like Claude.”

### 0:55 – 2:20 · Demo (The App Simulation)
**[on screen]** Walk through this exact app simulation flow:
1. Click **New Incident** -> Title it "SQS DLQ Filling Up"
2. Go to **Data Collection** -> Upload `incident-10.md`
3. Go to **Documentation** -> Show the auto-generated content.
4. Go to **AI Chat** -> Ask a question about the incident.

> **Spoken:** “Let’s look at a live simulation. I’ll create a new incident for an SQS queue failure. 
> 
> *[Action: Create incident & upload doc]* 
> When engineers upload a postmortem into the Data Collection tab, OpsMemory doesn't just store the file. It parses, embeds, and **cognifies** it using Cognee. 
> 
> *[Action: Switch to Documentation tab]*
> The **Documentation** tab is now instantly auto-generated. It extracted the root cause, the resolution, and a detailed summary—with exact citations back to the source. I never typed this; the AI generated it from the evidence.
> 
> *[Action: Mention the Recall.ai Bot]*
> We didn't stop at documents. We built a **Recall.ai Meeting Bot** that you can invite to your postmortem calls. When the meeting ends, a webhook sends the transcript to OpsMemory, an SRE-persona extracts the structured knowledge, and it injects it straight into the Cognee graph without anyone typing a word.
> 
> *[Action: Open AI Chat]*
> Now, if an engineer asks the AI, *'How did we fix the SQS DLQ?'*, it answers directly from this incident’s memory graph, complete with citations and confidence scores.”

### 2:20 – 2:40 · Proof it’s really Cognee
**[on screen]** Click **“Visualize the Cognee Memory”** on the dashboard.

> **Spoken:** “And this isn’t a black box. You can click to visualize the **live Cognee knowledge graph** running behind the platform, proving that the memory is real, connected, and constantly growing.”

### 2:40 – 2:55 · Learning & growth (optional close)
**[on screen]** Back to the dashboard stats ticking up or the main UI.

> **Spoken:** “The biggest lesson we learned building this is that **retrieval quality beats prompt tricks**. By putting a real memory engine like Cognee behind everything, we built an AI that is genuinely trustworthy. Every lesson compounds, and tribal knowledge stops walking out the door. Thank you.”

---

## 2. App Simulation Checklist (What to actually click)

For the "Demo" portion of your video, here is the exact app simulation you should record:

1. **Dashboard**: Show the main UI and the stats at the top.
2. **Create Incident**: Click "New Incident", name it "SQS DLQ Exhausted", and hit Create.
3. **Upload Evidence**: Go to the **Data Collection** tab, click "Upload Document", select `incident-10.md` (or any markdown file you have), and click "Upload & ingest". 
4. **Show the Magic**: Instantly switch to the **Documentation** tab. Scroll through to show how the AI extracted the "Root Cause" and "Resolution" from the file. *Hover over the citation chips to prove it's grounded in evidence.*
5. **The Chat**: Go to the **AI Chat** tab and ask "What caused the SQS DLQ to fill up?". Show how the AI answers instantly with citations.
6. **The Graph**: Go back to the dashboard and click the **Visualize the Cognee Memory** button to show the raw graph nodes.

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
