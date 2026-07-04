"""Tests for AI providers and the provider factory."""

import pytest
import respx
from httpx import Response

from opsmemory.ai.factory import build_embedding_provider, build_llm_provider
from opsmemory.ai.providers import (
    GeminiEmbeddingProvider,
    GeminiLLMProvider,
    GroqLLMProvider,
    HashingEmbeddingProvider,
    ProviderError,
)
from opsmemory.core.config import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


async def test_hashing_embeddings_deterministic_and_similarity_ordered() -> None:
    provider = HashingEmbeddingProvider(dimension=64)
    [a1], [a2] = await provider.embed(["redis outage"]), await provider.embed(["redis outage"])
    assert a1 == a2

    [redis1, redis2, unrelated] = await provider.embed(
        ["redis authentication failure", "redis failure", "kubernetes networking guide"]
    )

    def dot(x: list[float], y: list[float]) -> float:
        return sum(a * b for a, b in zip(x, y, strict=True))

    assert dot(redis1, redis2) > dot(redis1, unrelated)


@respx.mock
async def test_gemini_embeddings_calls_batch_endpoint() -> None:
    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
    ).mock(
        return_value=Response(
            200, json={"embeddings": [{"values": [3.0, 4.0]}, {"values": [1.0, 0.0]}]}
        )
    )
    provider = GeminiEmbeddingProvider(api_key="k", model="gemini-embedding-001", dimension=2)
    vectors = await provider.embed(["a", "b"])
    assert route.called
    assert vectors[0] == pytest.approx([0.6, 0.8])  # normalized
    assert route.calls[0].request.headers["x-goog-api-key"] == "k"


@respx.mock
async def test_groq_llm_complete() -> None:
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": "the answer"}}]})
    )
    provider = GroqLLMProvider(api_key="k", model="llama-3.3-70b-versatile")
    assert await provider.complete("sys", "user", max_tokens=100) == "the answer"


@respx.mock
async def test_gemini_llm_complete_and_error() -> None:
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    ).mock(
        return_value=Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "hello"}]}}]},
        )
    )
    provider = GeminiLLMProvider(api_key="k", model="gemini-2.5-flash")
    assert await provider.complete("sys", "user", max_tokens=10) == "hello"


@respx.mock
async def test_groq_llm_http_error_raises_provider_error() -> None:
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(429, text="rate limited")
    )
    provider = GroqLLMProvider(api_key="k", model="m")
    with pytest.raises(ProviderError):
        await provider.complete("s", "u", max_tokens=10)


def test_factory_auto_resolution_prefers_groq_then_gemini() -> None:
    both = _settings(groq_api_key="g1", gemini_api_key="g2")
    assert both.resolve_llm_provider() == "groq"
    assert both.resolve_embedding_provider() == "gemini"

    gemini_only = _settings(gemini_api_key="g2")
    assert gemini_only.resolve_llm_provider() == "gemini"

    keyless = _settings()
    assert keyless.resolve_llm_provider() == "none"
    assert keyless.resolve_embedding_provider() == "hashing"
    assert build_llm_provider(keyless) is None
    assert build_embedding_provider(keyless).name == "hashing"


def test_factory_gemini_for_both_roles() -> None:
    settings = _settings(gemini_api_key="k", llm_provider="gemini", embedding_provider="gemini")
    llm = build_llm_provider(settings)
    emb = build_embedding_provider(settings)
    assert llm is not None and llm.name == "gemini"
    assert emb.name == "gemini"


def test_factory_rejects_groq_embeddings_with_guidance() -> None:
    settings = _settings(groq_api_key="k", embedding_provider="groq")
    with pytest.raises(ProviderError, match="does not offer an embeddings API"):
        build_embedding_provider(settings)
