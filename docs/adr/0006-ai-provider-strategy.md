# ADR-0006: Independent, configurable AI providers (Gemini / Groq / Anthropic)

Date: 2026-07-03 · Status: Accepted

## Context

The platform needs two distinct AI capabilities with different economics:
embeddings (high volume, cheap, at ingestion time) and reasoning (low
volume, quality-sensitive, at question time). Teams want to mix providers —
e.g. Gemini embeddings with Groq-hosted Llama for fast reasoning — and swap
them without code changes.

## Decision

- Two independent ports: `EmbeddingProvider` and `LLMProvider`
  (`opsmemory.ai.base`), selected separately via
  `OPSMEMORY_EMBEDDING_PROVIDER` and `OPSMEMORY_LLM_PROVIDER`.
- Implementations: **Gemini** (embeddings + reasoning), **Groq**
  (reasoning; Groq offers no embeddings API — selecting it for embeddings
  fails fast with guidance), **Anthropic** (reasoning), **hashing**
  (deterministic keyless embeddings for dev/tests), **none** (extractive
  answers without any LLM).
- `auto` resolution: embeddings → gemini if keyed else hashing; LLM →
  groq → gemini → anthropic → none, by key presence.
- Gemini/Groq are called over REST with httpx (no SDK lock-in); Cognee
  reuses the same keys via its adapter (ADR-0002).
- Every LLM-dependent feature (chat, teaching extraction) has a
  deterministic fallback, so the platform is fully functional keyless —
  with reduced answer quality, clearly flagged in responses and logs.

## Consequences

- "Groq for both" is impossible today (no embeddings API); the error
  message says exactly that and how to configure the supported split.
- New providers are one class + one factory branch.
- Tests run keyless and offline (hashing + none).
