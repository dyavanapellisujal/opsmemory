"""Concrete embedding and LLM provider implementations.

Gemini and Groq are called over their public REST APIs with httpx to keep
the dependency surface small; Anthropic uses its official SDK (already a
project dependency). The hashing embedder is deterministic and keyless for
development and tests.
"""

import hashlib
import math
import struct
from typing import Any

import httpx

from opsmemory.core.errors import OpsMemoryError

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class ProviderError(OpsMemoryError):
    """Raised when an AI provider call fails."""

    code = "AI_PROVIDER_ERROR"
    status_code = 502


class HashingEmbeddingProvider:
    """Deterministic, keyless embeddings for development and tests.

    Vectors are derived from SHA-256 digests of word tokens so similar texts
    (sharing words) produce similar vectors. Not semantically meaningful —
    use Gemini in real deployments.
    """

    name = "hashing"

    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension

    def _token_vector(self, token: str) -> list[float]:
        """Derive a stable pseudo-random contribution in [-1, 1] for one token."""
        digest = hashlib.sha256(token.encode()).digest()
        values: list[float] = []
        while len(values) < self.dimension:
            digest = hashlib.sha256(digest).digest()
            values.extend(v / 2**31 - 1.0 for v in struct.unpack("<8I", digest))
        return values[: self.dimension]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts by summing token vectors and normalizing."""
        results: list[list[float]] = []
        for text in texts:
            acc = [0.0] * self.dimension
            for token in text.lower().split():
                for i, v in enumerate(self._token_vector(token)):
                    acc[i] += v
            norm = math.sqrt(sum(v * v for v in acc)) or 1.0
            results.append([v / norm for v in acc])
        return results


class GeminiEmbeddingProvider:
    """Gemini embeddings via the ``batchEmbedContents`` REST endpoint."""

    name = "gemini"

    def __init__(self, api_key: str, model: str, dimension: int, timeout: float = 30.0) -> None:
        if not api_key:
            raise ProviderError("Gemini embedding provider selected but no API key configured")
        self._api_key = api_key
        self._model = model
        self.dimension = dimension
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts with Gemini."""
        requests = [
            {
                "model": f"models/{self._model}",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": self.dimension,
            }
            for text in texts
        ]
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{GEMINI_BASE_URL}/models/{self._model}:batchEmbedContents",
                headers={"x-goog-api-key": self._api_key},
                json={"requests": requests},
            )
        if response.status_code != 200:
            raise ProviderError(
                f"Gemini embeddings failed: HTTP {response.status_code}",
                details={"body": response.text[:500]},
            )
        embeddings: list[list[float]] = [item["values"] for item in response.json()["embeddings"]]
        return [_normalize(vec) for vec in embeddings]


class GroqLLMProvider:
    """Groq chat completions via its OpenAI-compatible REST API."""

    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise ProviderError("Groq LLM provider selected but no API key configured")
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str:
        """Generate a completion with Groq."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        if response.status_code != 200:
            raise ProviderError(
                f"Groq completion failed: HTTP {response.status_code}",
                details={"body": response.text[:500]},
            )
        content: str = response.json()["choices"][0]["message"]["content"]
        return content


class GeminiLLMProvider:
    """Gemini chat completions via the ``generateContent`` REST endpoint."""

    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise ProviderError("Gemini LLM provider selected but no API key configured")
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str:
        """Generate a completion with Gemini."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{GEMINI_BASE_URL}/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self._api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens},
                },
            )
        if response.status_code != 200:
            raise ProviderError(
                f"Gemini completion failed: HTTP {response.status_code}",
                details={"body": response.text[:500]},
            )
        body: dict[str, Any] = response.json()
        try:
            parts = body["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError) as exc:
            raise ProviderError(
                "Gemini returned an unexpected response shape",
                details={"body": str(body)[:500]},
            ) from exc


class AnthropicLLMProvider:
    """Anthropic Claude completions via the official SDK."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ProviderError("Anthropic LLM provider selected but no API key configured")
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str:
        """Generate a completion with Claude."""
        message = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in message.content if block.type == "text")


def _normalize(vector: list[float]) -> list[float]:
    """L2-normalize a vector so cosine similarity equals dot product."""
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
