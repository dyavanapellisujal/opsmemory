# ADR-0008: Incident as the knowledge hub; session auth; living documentation

Date: 2026-07-04 · Status: Accepted

## Context

The OpsMemory experience reframes the product around incidents: each incident
is a continuously-growing knowledge object that many sources (documents,
meetings, manual entries) enrich over time, rather than a ticket. It also
requires authentication and a generated-not-edited documentation view.

## Decisions

### 1. Incident is the primary memory object
`Document`, `Memory`, `Meeting`, and `OperationalExperience` gained a nullable
`incident_id`. Every incident-scoped ingestion links its derived
memories/experiences to the incident, so retrieval can be scoped to one
incident (incident chat) or mapped back to incidents (global assistant,
suggestions). Incidents are the source of truth (ADR-0003); the graph and
vectors remain derived. `IncidentLink` records accepted AI suggestions as
directed edges with rationale + shared-service citations.

### 2. Enrichment reuses existing pipelines — nothing is bypassed
Document upload runs the same parse → chunk → embed → relationship pipeline;
manual "operational experience / root cause / resolution" entries route
through the **Teaching Pipeline** (duplicate detection reinforces confidence
instead of creating duplicate memory — "always merge into existing memory").
Meetings attach by adopting the knowledge the Meeting Connector already
extracted. `TeachingService.teach()` and `MemoryItem` gained an
`incident_id` so the hub linkage flows through unchanged pipelines.

### 3. Living documentation is generated, never edited
`generate_documentation()` deterministically assembles cited sections
(Overview, Timeline, Root Cause, Resolution, Lessons, Architecture
Decisions, Action Items, Services, Infrastructure, References, Evidence)
from the incident's evidence bundle. It is regenerated on every ingestion
and stored on `Incident.documentation`. Deterministic assembly keeps it
testable and traceable; each section carries typed `Source` citations
(meeting / document / experience / manual) that link back to the origin.

### 4. Authentication: server-side sessions behind a provider interface
Opaque bearer tokens back server-side `Session` rows (only the token SHA-256
is stored; logout deletes the row). Password hashing is PBKDF2-HMAC-SHA256
(standard library — no new dependency). An `AuthProvider` protocol
(`PasswordAuthProvider` today) keeps OAuth (Google/GitHub/Microsoft)
a drop-in addition. `OPSMEMORY_AUTH_ENABLED` gates protection so tests and
keyless dev stay open; a bootstrap admin is seeded on first startup.

### 5. Meeting Intelligence: meetings are evidence, not standalone objects
A meeting always enriches an incident. Invited with an ``incident_id`` it
enriches that incident; invited without one, the AI names and auto-creates a
new incident from the transcript (`_incident_title` picks a concise
engineering title, never "Meeting Summary"). The webhook acks immediately
and a background pipeline (transcript → extract → resolve/create incident →
enrich → living docs) runs with per-stage retries. Each incident has a
`IncidentEvent` timeline and lifecycle `Notification`s (polled by the SPA).
Intelligent scalar merge (`_merge_text`) fills blanks / appends new content
and never overwrites; the living-documentation regeneration handles the rest.

**Meeting deletion is now a full cascade** (superseding the earlier deferral):
delete transcript, summary, meeting-derived memories, meeting-authored
experiences and their memories, and the meeting's graph nodes, then
regenerate the incident's documentation and append a timeline event. Memory
gained `delete_for_meeting`/`delete_for_experience`; the graph gained
`delete_node`.

## Consequences
- Adding a new ingestion source is a connector + a Data Collection entry;
  the incident hub, documentation, suggestions, and chat are source-agnostic.
- Frontend renders connectors from a list, so new sources need no redesign.
- All new endpoints require auth when enabled; the SPA holds a bearer token.
