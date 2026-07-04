"""Application configuration.

All configuration is provided through environment variables (12-factor),
prefixed with ``OPSMEMORY_``. A local ``.env`` file is supported for
development convenience.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment the application is running in."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Central application settings.

    Every subsystem reads its configuration from this object rather than
    from the process environment directly, so configuration remains
    testable and discoverable in one place.
    """

    model_config = SettingsConfigDict(
        env_prefix="OPSMEMORY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # --- API server ---
    api_host: str = Field(default="0.0.0.0", description="Bind address for the API server.")
    api_port: int = Field(default=8000, description="Bind port for the API server.")

    # --- Client (CLI) ---
    api_url: str = Field(
        default="http://localhost:8000",
        description="Base URL the CLI uses to reach the OpsMemory API.",
    )

    # --- Authentication ---
    auth_enabled: bool = Field(
        default=True,
        description="Require authentication on protected routes (disable in tests).",
    )
    auth_session_ttl_hours: int = Field(
        default=168, description="Session lifetime in hours (default 7 days)."
    )
    auth_bootstrap_email: str = Field(
        default="admin@opsmemory.local",
        description="Email of the admin user seeded on first startup.",
    )
    auth_bootstrap_password: str = Field(
        default="opsmemory",
        description="Password for the seeded admin user (change in production).",
    )

    # --- Storage ---
    database_url: str = Field(
        default="postgresql+asyncpg://opsmemory:opsmemory@localhost:5432/opsmemory",
        description="Async SQLAlchemy URL for the primary PostgreSQL database.",
    )
    database_echo: bool = Field(
        default=False, description="Echo SQL statements (development only)."
    )
    graph_db_path: str = Field(
        default="./data/graph",
        description="Filesystem path for the embedded Kuzu graph database.",
    )

    # --- Provider credentials (shared by embeddings, LLM, and Cognee) ---
    gemini_api_key: str = Field(default="", description="Google Gemini API key.")
    groq_api_key: str = Field(default="", description="Groq API key.")
    anthropic_api_key: str = Field(default="", description="Anthropic API key.")

    # --- Memory & embeddings ---
    memory_engine: str = Field(
        default="cognee",
        description=(
            'Central memory engine: "cognee" (default — cognifies every write into a '
            'knowledge graph over the platform Postgres/pgvector) or "native" (the raw '
            "pgvector substrate; used by tests). Cognee still requires an LLM key to "
            "build the graph; without one it transparently uses the substrate."
        ),
    )
    cognee_cognify: bool = Field(
        default=True,
        description="Run Cognee graph cognification on writes (needs an LLM key).",
    )
    cognee_use_platform_postgres: bool = Field(
        default=True,
        description="Point Cognee's relational + vector stores at the OpsMemory database.",
    )
    embedding_provider: str = Field(
        default="auto",
        description=(
            'Embedding provider: "gemini", "hashing" (deterministic, keyless — dev/tests), '
            'or "auto" (gemini when a key is configured, otherwise hashing). '
            "Note: Groq does not offer an embeddings API."
        ),
    )
    embedding_dimension: int = Field(
        default=768,
        description=(
            "Embedding vector dimension. Must match the pgvector column "
            "(vector(768) in the initial memory migration)."
        ),
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001", description="Gemini embedding model name."
    )

    # --- LLM (AI agent reasoning) ---
    llm_provider: str = Field(
        default="auto",
        description=(
            'LLM provider: "groq", "gemini", "anthropic", "none" (extractive fallback), '
            'or "auto" (first of groq → gemini → anthropic with a configured key, else none). '
            "Reasoning and embeddings are selected independently, so any combination works "
            "(e.g. Gemini for both, or Gemini embeddings + Groq reasoning)."
        ),
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile", description="Groq model used for reasoning."
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash", description="Gemini model used for reasoning."
    )
    anthropic_model: str = Field(
        default="claude-sonnet-5", description="Anthropic model used for reasoning."
    )
    llm_max_tokens: int = Field(default=2048, description="Max tokens per LLM response.")

    def resolve_llm_provider(self) -> str:
        """Resolve the effective LLM provider, expanding ``auto``."""
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.groq_api_key:
            return "groq"
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        return "none"

    def resolve_embedding_provider(self) -> str:
        """Resolve the effective embedding provider, expanding ``auto``."""
        if self.embedding_provider != "auto":
            return self.embedding_provider
        return "gemini" if self.gemini_api_key else "hashing"

    # --- Retrieval budgets (PRD defaults) ---
    retrieval_max_memories: int = Field(default=5, description="Max semantic memories.")
    retrieval_max_experiences: int = Field(default=3, description="Max operational experiences.")
    retrieval_max_documents: int = Field(default=5, description="Max supporting documents.")
    retrieval_max_graph_hops: int = Field(default=3, description="Max graph traversal depth.")

    # --- Meeting connector (Recall.ai) ---
    recall_api_key: str = Field(default="", description="Recall.ai API key.")
    recall_region: str = Field(
        default="us-east-1",
        description="Recall.ai region (us-east-1, us-west-2, eu-central-1, ap-northeast-1).",
    )
    recall_webhook_secret: str = Field(
        default="",
        description="Svix signing secret (whsec_...) for Recall webhooks; empty skips checks.",
    )
    recall_bot_name: str = Field(
        default="OpsMemory Notetaker", description="Display name of the meeting bot."
    )

    # --- HTTP docs connector ---
    http_crawl_max_pages: int = Field(default=50, description="Max pages per crawl.")
    http_crawl_max_depth: int = Field(default=3, description="Max link depth per crawl.")
    http_timeout_seconds: float = Field(default=15.0, description="Per-request timeout.")

    @property
    def sync_database_url(self) -> str:
        """Synchronous form of the database URL (used by Alembic offline mode)."""
        return self.database_url.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
