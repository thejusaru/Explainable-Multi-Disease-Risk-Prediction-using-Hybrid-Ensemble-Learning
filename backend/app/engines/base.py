"""The seam between "how risk is computed" and everything else.

The app depends only on this interface. Swapping the LLM engine for validated
clinical models (Framingham, ASCVD, FINDRISC, QRISK3) later means adding one
class here and changing one line in `dependencies.py` — no route, schema or
frontend changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.schemas import PatientProfile, RiskAssessment
from app.parsers.extract import ExtractedReport


class RiskEngineError(RuntimeError):
    """Raised when an engine cannot produce an assessment."""


class RiskEngine(ABC):
    """Produces a `RiskAssessment` from a patient profile and/or a report."""

    #: Stamped onto every assessment so results stay auditable after the fact.
    name: str = "abstract"

    @abstractmethod
    async def assess(
        self,
        profile: PatientProfile | None = None,
        report: ExtractedReport | None = None,
    ) -> RiskAssessment:
        """Estimate future disease risk.

        At least one of `profile` or `report` must carry usable content;
        implementations raise `RiskEngineError` when neither does.
        """
        raise NotImplementedError
