"""Engine discovery.

Lets the UI show which engines are usable *right now* — Claude needs a key,
local models need Ollama running with the model pulled — rather than offering a
choice that fails on submit.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import EngineKind, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["meta"])


class EngineOption(BaseModel):
    kind: EngineKind
    label: str
    model: str
    available: bool
    detail: str
    models: list[str] = []


class EnginesResponse(BaseModel):
    default: EngineKind
    engines: list[EngineOption]


async def _list_ollama_models(host: str) -> list[str] | None:
    """Return installed Ollama models, or None when Ollama is unreachable."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{host.rstrip('/')}/api/tags")
        if response.status_code != 200:
            return None
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    return sorted(
        m["name"]
        for m in payload.get("models", [])
        if isinstance(m, dict) and m.get("name")
    )


@router.get("/engines", response_model=EnginesResponse)
async def list_engines() -> EnginesResponse:
    settings = get_settings()

    claude = EngineOption(
        kind=EngineKind.claude,
        label="Claude (cloud)",
        model=settings.anthropic_model,
        available=settings.has_credentials,
        detail=(
            "Schema-enforced output, reads images. Requires an API key."
            if settings.has_credentials
            else "No ANTHROPIC_API_KEY found — set it in backend/.env."
        ),
    )

    installed = await _list_ollama_models(settings.ollama_host)
    if installed is None:
        local = EngineOption(
            kind=EngineKind.local,
            label="Local model (Ollama)",
            model=settings.local_model,
            available=False,
            detail=(
                f"Ollama not reachable at {settings.ollama_host}. "
                "Start it with 'ollama serve'."
            ),
        )
    elif not installed:
        local = EngineOption(
            kind=EngineKind.local,
            label="Local model (Ollama)",
            model=settings.local_model,
            available=False,
            detail=(
                "Ollama is running but has no models. "
                f"Run: ollama pull {settings.local_model}"
            ),
        )
    else:
        # Prefer the configured model; fall back to whatever is installed so the
        # option still works after a default-model rename.
        chosen = (
            settings.local_model
            if settings.local_model in installed
            else installed[0]
        )
        local = EngineOption(
            kind=EngineKind.local,
            label="Local model (Ollama)",
            model=chosen,
            available=True,
            detail=(
                "Runs offline, no API cost. Small models are less reliable at "
                "structured output and cannot read images."
            ),
            models=installed,
        )

    return EnginesResponse(
        default=settings.default_engine, engines=[claude, local]
    )
