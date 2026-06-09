"""Phase 0 smoke test: verify the local environment is ready.

Checks:
  1. Settings load from .env without error.
  2. Ollama server is reachable.
  3. The configured router / agent / embed models are available locally.

Run with:  make env-check   (or)   uv run python -m backend.scripts.env_check
"""

from __future__ import annotations

import sys

import httpx

from backend.app.core.settings import settings

OK = "✅"
BAD = "❌"
WARN = "⚠️ "


def _tags() -> list[str]:
    """Return the list of locally available Ollama model tags."""
    resp = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
    resp.raise_for_status()
    return [m["name"] for m in resp.json().get("models", [])]


def main() -> int:
    print("Archon environment check\n" + "-" * 40)

    # 1. Settings
    print(f"{OK} Settings loaded")
    print(f"     router_model = {settings.router_model}")
    print(f"     agent_model  = {settings.agent_model}")
    print(f"     embed_model  = {settings.embed_model}")
    print(f"     ollama_url   = {settings.ollama_base_url}")
    print(f"     tracing_v2   = {settings.langchain_tracing_v2}")

    # 2. Ollama reachable
    try:
        available = _tags()
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} Could not reach Ollama at {settings.ollama_base_url}: {exc}")
        print("     Start it with:  ollama serve")
        return 1
    print(f"{OK} Ollama reachable — {len(available)} model(s) installed")

    # 3. Required models present (matched loosely by prefix to tolerate :latest tags)
    required = {
        "router": settings.router_model,
        "agent": settings.agent_model,
        "embed": settings.embed_model,
    }
    missing = []
    for role, want in required.items():
        base = want.split(":")[0]
        if any(tag == want or tag.split(":")[0] == base for tag in available):
            print(f"{OK} {role:<6} model present: {want}")
        else:
            print(f"{BAD} {role:<6} model MISSING: {want}  (pull with: ollama pull {want})")
            missing.append(want)

    # 4. LangSmith key sanity (non-fatal)
    import os

    if settings.langchain_tracing_v2 and not os.getenv("LANGCHAIN_API_KEY", "").startswith("ls"):
        print(f"{WARN}LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY looks unset/placeholder")

    print("-" * 40)
    if missing:
        print(f"{BAD} Environment NOT ready — install missing models above.")
        return 1
    print(f"{OK} Environment ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
