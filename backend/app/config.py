"""Runtime configuration, read once from the environment."""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


def _load_dotenv() -> None:
    """Load `backend/.env` into the environment if it exists.

    Hand-rolled rather than pulling in python-dotenv for this. Real environment
    variables always win, so an exported key is never overridden by a stale file.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


class EngineKind(str, Enum):
    """Which risk engine to run. Selectable per request."""

    claude = "claude"
    local = "local"


class Settings(BaseModel):
    default_engine: EngineKind = EngineKind.claude

    anthropic_model: str = "claude-opus-5"

    local_model: str = "qwen2.5:7b"
    ollama_host: str = "http://localhost:11434"
    local_timeout_seconds: float = 300.0

    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def has_credentials(self) -> bool:
        """Whether an Anthropic API key is present in the environment.

        Only checks env vars. The SDK also resolves `ant auth login` profiles,
        so False here does not guarantee failure — it only drives the UI hint.
        """
        return bool(
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )


@lru_cache
def get_settings() -> Settings:
    origins = os.environ.get("CORS_ORIGINS")

    raw_engine = (os.environ.get("RISK_ENGINE") or "claude").strip().lower()
    try:
        default_engine = EngineKind(raw_engine)
    except ValueError:
        # An unrecognised value should not stop the server booting.
        default_engine = EngineKind.claude

    return Settings(
        default_engine=default_engine,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"),
        local_model=os.environ.get("LOCAL_MODEL", "qwen2.5:7b"),
        ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        local_timeout_seconds=float(
            os.environ.get("LOCAL_TIMEOUT_SECONDS", "300")
        ),
        cors_origins=(
            [o.strip() for o in origins.split(",") if o.strip()]
            if origins
            else ["http://localhost:3000"]
        ),
    )
