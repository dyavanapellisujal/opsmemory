"""Provider ports (interfaces) for embeddings and LLM reasoning."""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Turns text into fixed-dimension vectors for semantic retrieval."""

    name: str
    dimension: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Input strings (non-empty).

        Returns:
            One vector of ``dimension`` floats per input, in order.
        """
        ...


class LLMProvider(Protocol):
    """Generates reasoning/synthesis completions over curated context."""

    name: str
    model: str

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str:
        """Generate a completion.

        Args:
            system: System prompt (role and constraints).
            user: User content, including assembled evidence.
            max_tokens: Response token budget.

        Returns:
            The model's text response.
        """
        ...
