"""
Agent schemas: Investigation and Recommendation.
Strictly follows DOC C C1.4 and C1.5 schemas.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


# ---------- Threat enrichment schemas (Module E) ----------

class ThreatTechnique(BaseModel):
    """Single MITRE ATT&CK technique matched by enrichment."""
    technique_id: str = Field(..., description="MITRE technique ID, e.g. T1595")
    technique_name: str = Field(..., description="Technique name")
    tactic_id: str = Field(..., description="MITRE tactic ID, e.g. TA0043")
    tactic_name: str = Field(..., description="Tactic name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Match confidence")
    description: str = Field(default="", description="Brief description")
    intel_refs: list[str] = Field(default_factory=list, description="Reference URLs")


class ThreatContext(BaseModel):
    """Threat intelligence enrichment result."""
    techniques: list[ThreatTechnique] = Field(default_factory=list, description="Matched MITRE techniques")
    tactics: list[str] = Field(default_factory=list, description="De-duplicated tactic names")
    enrichment_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall enrichment confidence")
    enrichment_source: str = Field(default="local_mitre_v1", description="Enrichment data source identifier")


# ---------- Investigation schemas - DOC C C1.4 ----------

class InvestigationImpact(BaseModel):
    """Impact assessment in Investigation."""
    scope: list[str] = Field(default_factory=list, description="Affected scope")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")


class InvestigationSchema(BaseModel):
    """
    Investigation output schema - DOC C C1.4.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the investigation")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    alert_id: str = Field(..., description="Related alert ID")
    hypothesis: str = Field(..., description="Investigation hypothesis")
    why: list[str] = Field(default_factory=list, description="Reasons supporting hypothesis")
    impact: InvestigationImpact = Field(..., description="Impact assessment")
    next_steps: list[str] = Field(default_factory=list, description="Recommended next steps")
    safety_note: str = Field(
        default="Advisory only; no actions executed.",
        description="Safety disclaimer"
    )
    threat_context: ThreatContext | None = Field(
        default=None,
        description="Optional MITRE ATT&CK threat enrichment context",
    )

    class Config:
        from_attributes = True


# Recommendation schemas - DOC C C1.5
class RecommendedAction(BaseModel):
    """Single action in Recommendation - DOC C C1.5."""
    title: str = Field(..., description="Action title")
    priority: Literal["high", "medium", "low"] = Field(..., description="Action priority")
    steps: list[str] = Field(default_factory=list, description="Action steps")
    rollback: list[str] = Field(default_factory=list, description="Rollback steps")
    risk: str = Field(default="", description="Risk description")


class RecommendationSchema(BaseModel):
    """
    Recommendation output schema - DOC C C1.5.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the recommendation")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    alert_id: str = Field(..., description="Related alert ID")
    actions: list[RecommendedAction] = Field(default_factory=list, description="Recommended actions")
    threat_context: ThreatContext | None = Field(
        default=None,
        description="Optional MITRE ATT&CK threat enrichment context",
    )

    class Config:
        from_attributes = True


# Triage request/response - DOC C C6.5
class TriageRequest(BaseModel):
    """Request for POST /alerts/{id}/triage - DOC C C6.5."""
    language: Literal["zh", "en"] = Field(default="en", description="Output language")


class TriageResponse(BaseModel):
    """Response for POST /alerts/{id}/triage - DOC C C6.5."""
    triage_summary: str = Field(..., description="Triage summary text")


class LanguageRequest(BaseModel):
    """Optional language request body for investigate/recommend."""
    language: Literal["zh", "en"] = Field(default="en", description="Output language")
