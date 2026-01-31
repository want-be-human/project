"""
Scenario schemas: Scenario and ScenarioRunResult.
Strictly follows DOC C C4.1 and C4.2 schemas.
"""

from typing import Literal
from pydantic import BaseModel, Field


# Scenario schemas - DOC C C4.1
class ScenarioPcapRef(BaseModel):
    """PCAP reference in scenario."""
    pcap_id: str = Field(..., description="PCAP file ID")


class MustHaveExpectation(BaseModel):
    """Must-have expectation in scenario - DOC C C4.1."""
    type: str = Field(..., description="Alert type")
    severity_at_least: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Minimum severity"
    )


class ScenarioExpectations(BaseModel):
    """Expectations for scenario - DOC C C4.1."""
    min_alerts: int = Field(default=0, ge=0, description="Minimum alerts expected")
    must_have: list[MustHaveExpectation] = Field(
        default_factory=list, description="Required alert patterns"
    )
    evidence_chain_contains: list[str] = Field(
        default_factory=list, description="Required evidence chain nodes"
    )
    dry_run_required: bool = Field(default=False, description="Whether dry run is required")


class ScenarioSchema(BaseModel):
    """
    Scenario output schema - DOC C C4.1.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the scenario")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    name: str = Field(..., description="Scenario name")
    description: str = Field(default="", description="Scenario description")
    pcap_ref: ScenarioPcapRef = Field(..., description="PCAP reference")
    expectations: ScenarioExpectations = Field(..., description="Scenario expectations")
    tags: list[str] = Field(default_factory=list, description="Tags")

    class Config:
        from_attributes = True


# ScenarioRunResult schemas - DOC C C4.2
class ScenarioCheck(BaseModel):
    """Single check result in scenario run - DOC C C4.2."""
    name: str = Field(..., description="Check name")
    pass_: bool = Field(alias="pass", description="Whether check passed")
    details: dict = Field(default_factory=dict, description="Check details")

    class Config:
        populate_by_name = True


class ScenarioMetrics(BaseModel):
    """Metrics from scenario run - DOC C C4.2."""
    alert_count: int = Field(default=0, description="Total alerts")
    high_severity_count: int = Field(default=0, description="High severity alerts")
    avg_dry_run_risk: float = Field(default=0.0, description="Average dry run risk")


class ScenarioRunResultSchema(BaseModel):
    """
    ScenarioRunResult output schema - DOC C C4.2.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the run result")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    scenario_id: str = Field(..., description="Related scenario ID")
    status: Literal["pass", "fail"] = Field(..., description="Overall status")
    checks: list[ScenarioCheck] = Field(default_factory=list, description="Check results")
    metrics: ScenarioMetrics = Field(default_factory=ScenarioMetrics, description="Run metrics")

    class Config:
        from_attributes = True


# Create scenario request - DOC C C6.9
class CreateScenarioRequest(BaseModel):
    """Request for POST /scenarios - DOC C C6.9."""
    name: str = Field(..., description="Scenario name")
    description: str = Field(default="", description="Description")
    pcap_ref: ScenarioPcapRef = Field(..., description="PCAP reference")
    expectations: ScenarioExpectations = Field(..., description="Expectations")
    tags: list[str] = Field(default_factory=list, description="Tags")


# Scenario query params
class ScenarioQueryParams(BaseModel):
    """Query parameters for GET /scenarios."""
    limit: int = Field(default=50, ge=1, le=1000, description="Max results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
