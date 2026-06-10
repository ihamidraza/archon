"""Central configuration for Archon.

All settings load from environment variables (and a local ``.env`` file) via
pydantic-settings. Defaults are chosen so the system runs fully locally at zero
cost. Import the shared ``settings`` singleton anywhere in the app:

    from backend.app.core.settings import settings
    print(settings.agent_model)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (…/archon). settings.py lives at backend/app/core/settings.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Strongly-typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Ollama ---
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    # Per-request timeout (seconds) for model calls, so a stuck model can't hang a request.
    request_timeout: float = Field(default=120.0, alias="ARCHON_REQUEST_TIMEOUT")

    # --- Observability / ops ---
    log_level: str = Field(default="INFO", alias="ARCHON_LOG_LEVEL")

    # --- Tiered models ---
    router_model: str = Field(default="llama3.2:3b", alias="ARCHON_ROUTER_MODEL")
    agent_model: str = Field(default="qwen3.6:latest", alias="ARCHON_AGENT_MODEL")
    embed_model: str = Field(default="nomic-embed-text", alias="ARCHON_EMBED_MODEL")
    router_temperature: float = Field(default=0.0, alias="ARCHON_ROUTER_TEMPERATURE")
    agent_temperature: float = Field(default=0.3, alias="ARCHON_AGENT_TEMPERATURE")

    # --- RAG / vector store ---
    chroma_dir: str = Field(default="backend/data/chroma", alias="ARCHON_CHROMA_DIR")
    chroma_collection: str = Field(default="archon_kb", alias="ARCHON_CHROMA_COLLECTION")
    kb_dir: str = Field(default="backend/data/knowledge_base", alias="ARCHON_KB_DIR")
    rag_top_k: int = Field(default=4, alias="ARCHON_RAG_TOP_K")

    # --- Memory / checkpointer ---
    checkpoint_db: str = Field(
        default="backend/data/checkpoints.sqlite", alias="ARCHON_CHECKPOINT_DB"
    )

    # --- Guardrail thresholds ---
    router_confidence_threshold: float = Field(
        default=0.5, alias="ARCHON_ROUTER_CONFIDENCE_THRESHOLD"
    )
    max_output_retries: int = Field(default=1, alias="ARCHON_MAX_OUTPUT_RETRIES")

    # --- API (Phase 8) ---
    api_cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="ARCHON_API_CORS_ORIGINS",
    )
    api_rate_limit: str = Field(default="30/minute", alias="ARCHON_API_RATE_LIMIT")
    api_max_message_chars: int = Field(default=4000, alias="ARCHON_API_MAX_MESSAGE_CHARS")

    # --- LangSmith ---
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_project: str = Field(default="archon", alias="LANGCHAIN_PROJECT")
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com", alias="LANGCHAIN_ENDPOINT"
    )
    langchain_api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")

    # ---- Resolved absolute paths (computed) ----
    @property
    def chroma_path(self) -> Path:
        return self._abs(self.chroma_dir)

    @property
    def kb_path(self) -> Path:
        return self._abs(self.kb_dir)

    @property
    def checkpoint_path(self) -> Path:
        return self._abs(self.checkpoint_db)

    @property
    def cors_origins(self) -> list[str]:
        """CORS allow-list parsed from the comma-separated setting."""
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @staticmethod
    def _abs(value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()


settings = get_settings()
