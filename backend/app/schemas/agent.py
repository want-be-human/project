"""
Agent schemas: Investigation and Recommendation.
Strictly follows DOC C C1.4 and C1.5 schemas.
"""

from typing import Literal
from pydantic import BaseModel, Field


# Investigation schemas - DOC C C1.4
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

    class Config:
        from_attributes = True


# Triage request/response - DOC C C6.5
class TriageRequest(BaseModel):
    """Request for POST /alerts/{id}/triage - DOC C C6.5."""
    language: Literal["zh", "en"] = Field(default="en", description="Output language")


class TriageResponse(BaseModel):
    """Response for POST /alerts/{id}/triage - DOC C C6.5."""
    triage_summary: str = Field(..., description="Triage summary text")
