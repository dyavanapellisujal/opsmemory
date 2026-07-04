"""Provider factories: build embedding/LLM providers from configuration."""

from opsmemory.ai.base import EmbeddingProvider, LLMProvider
from opsmemory.ai.providers import (
    AnthropicLLMProvider,
    GeminiEmbeddingProvider,
    GeminiLLMProvider,
    GroqLLMProvider,
    HashingEmbeddingProvider,
    ProviderError,
)
from opsmemory.core.config import Settings
from opsmemory.core.logging import get_logger

logger = get_logger(__name__)


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Build the configured embedding provider.

    Raises:
        ProviderError: If an unknown or unsupported provider is configured
            (e.g. ``groq``, which offers no embeddings API).
    """
    provider = settings.resolve_embedding_provider()
    if provider == "gemini":
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_embedding_model,
            dimension=settings.embedding_dimension,
        )
    if provider == "hashing":
        logger.warning(
            "Using the keyless 'hashing' embedding provider — retrieval quality will be "
            "poor. Configure OPSMEMORY_GEMINI_API_KEY for real semantic embeddings."
        )
        return HashingEmbeddingProvider(dimension=settings.embedding_dimension)
    if provider == "groq":
        raise ProviderError(
            "Groq does not offer an embeddings API. Use OPSMEMORY_EMBEDDING_PROVIDER=gemini "
            "(Groq can still handle reasoning via OPSMEMORY_LLM_PROVIDER=groq)."
        )
    raise ProviderError(f"Unknown embedding provider: {provider!r}")


def build_llm_provider(settings: Settings) -> LLMProvider | None:
    """Build the configured LLM provider, or ``None`` for extractive mode.

    Raises:
        ProviderError: If an unknown provider is configured.
    """
    provider = settings.resolve_llm_provider()
    if provider == "groq":
        return GroqLLMProvider(api_key=settings.groq_api_key, model=settings.groq_model)
    if provider == "gemini":
        return GeminiLLMProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if provider == "anthropic":
        return AnthropicLLMProvider(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model
        )
    if provider == "none":
        logger.warning(
            "No LLM provider configured — chat answers will be extractive summaries of "
            "retrieved evidence. Configure OPSMEMORY_GROQ_API_KEY or OPSMEMORY_GEMINI_API_KEY."
        )
        return None
    raise ProviderError(f"Unknown LLM provider: {provider!r}")
