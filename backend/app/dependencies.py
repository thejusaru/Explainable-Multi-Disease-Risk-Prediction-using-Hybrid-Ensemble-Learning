"""Engine selection.

The single place that maps an `EngineKind` to a `RiskEngine` implementation.
Adding a clinical-model engine later means one more branch here.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import EngineKind, get_settings
from app.engines.base import RiskEngine
from app.engines.llm_engine import LLMRiskEngine
from app.engines.local_engine import LocalRiskEngine


@lru_cache
def _build_engine(kind: EngineKind, model: str) -> RiskEngine:
    """Construct and cache one engine per (kind, model) pair.

    Cached so the underlying HTTP client and its connection pool are reused
    across requests rather than rebuilt per call.
    """
    settings = get_settings()
    if kind is EngineKind.local:
        return LocalRiskEngine(
            model=model,
            host=settings.ollama_host,
            timeout=settings.local_timeout_seconds,
        )
    return LLMRiskEngine(model=model)


def resolve_engine(
    kind: EngineKind | None = None, model: str | None = None
) -> RiskEngine:
    """Return the engine for this request.

    Falls back to the configured defaults when the caller does not specify,
    so existing clients keep working unchanged.
    """
    settings = get_settings()
    chosen = kind or settings.default_engine
    chosen_model = model or (
        settings.local_model
        if chosen is EngineKind.local
        else settings.anthropic_model
    )
    return _build_engine(chosen, chosen_model)


def get_risk_engine() -> RiskEngine:
    """The default engine, for callers that do not select one."""
    return resolve_engine()
