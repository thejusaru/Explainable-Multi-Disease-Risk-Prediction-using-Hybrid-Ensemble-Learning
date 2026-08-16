"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import analysis, engines

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()

app = FastAPI(
    title="Health Risk Projection API",
    description=(
        "Estimates future disease risk at ages 25/30/35/40/45 from a medical "
        "report or patient profile. Not a diagnostic device."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(analysis.router)
app.include_router(engines.router)


@app.get("/api/health", tags=["meta"])
async def health() -> dict:
    """Liveness plus a credential hint, so a misconfigured key is obvious early."""
    return {
        "status": "ok",
        "default_engine": settings.default_engine.value,
        "claude_model": settings.anthropic_model,
        "local_model": settings.local_model,
        "credentials_detected": settings.has_credentials,
    }
