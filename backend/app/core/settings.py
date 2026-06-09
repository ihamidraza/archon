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

    # --- LangSmith ---
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_project: str = Field(default="archon", alias="LANGCHAIN_PROJECT")

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

    @staticmethod
    def _abs(value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()


settings = get_settings()
