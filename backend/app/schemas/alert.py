"""
Alert schemas.
Strictly follows DOC C C1.3 Alert schema.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


# Alert schema 的嵌套对象
class TimeWindow(BaseModel):
    """Time window for alert - DOC C C1.3."""
    start: str = Field(..., description="Start time ISO8601 UTC")
    end: str = Field(..., description="End time ISO8601 UTC")


class PrimaryService(BaseModel):
    """Primary service info - DOC C C1.3."""
    proto: str = Field(..., description="Protocol")
    dst_port: int = Field(..., description="Destination port")


class AlertEntities(BaseModel):
    """Alert entities - DOC C C1.3."""
    primary_src_ip: str = Field(..., description="Primary source IP")
    primary_dst_ip: str = Field(..., description="Primary destination IP")
    primary_service: PrimaryService = Field(..., description="Primary service")


class TopFlowSummary(BaseModel):
    """Top flow summary in evidence - DOC C C1.3."""
    flow_id: str = Field(..., description="Flow ID")
    anomaly_score: float = Field(..., description="Anomaly score")
    summary: str = Field(..., description="Brief description")


class TopFeature(BaseModel):
    """Top feature in evidence - DOC C C1.3."""
    name: str = Field(..., description="Feature name")
    value: Any = Field(..., description="Feature value")
    direction: Literal["high", "low"] = Field(..., description="Anomaly direction")


class PcapRef(BaseModel):
    """PCAP reference in evidence - DOC C C1.3."""
    pcap_id: str = Field(..., description="PCAP ID")
    offset_hint: int | None = Field(default=None, description="Byte offset hint")


class AlertEvidence(BaseModel):
    """Alert evidence - DOC C C1.3."""
    flow_ids: list[str] = Field(default_factory=list, description="Related flow IDs")
    top_flows: list[TopFlowSummary] = Field(default_factory=list, description="Top anomalous flows")
    top_features: list[TopFeature] = Field(default_factory=list, description="Top contributing features")
    pcap_ref: PcapRef | None = Field(default=None, description="PCAP reference")


class AlertAggregation(BaseModel):
    """Alert aggregation info - DOC C C1.3."""
    rule: str = Field(..., description="Aggregation rule")
    group_key: str = Field(..., description="Group key")
    count_flows: int = Field(..., description="Number of flows in group")


class AlertAgent(BaseModel):
    """Alert agent info - DOC C C1.3."""
    triage_summary: str | None = Field(default=None, description="Triage summary")
    investigation_id: str | None = Field(default=None, description="Investigation ID")
    recommendation_id: str | None = Field(default=None, description="Recommendation ID")


class AlertTwin(BaseModel):
    """Alert twin info - DOC C C1.3."""
    plan_id: str | None = Field(default=None, description="Action plan ID")
    dry_run_id: str | None = Field(default=None, description="Latest dry run ID")


class AlertSchema(BaseModel):
    """
    Alert output schema - DOC C C1.3.
    
    All field names MUST match DOC C exactly.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the alert")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    severity: Literal["low", "medium", "high", "critical"] = Field(..., description="Alert severity")
    status: Literal["new", "triaged", "investigating", "resolved", "false_positive"] = Field(
        default="new", description="Alert status"
    )
    type: Literal["anomaly", "scan", "dos", "bruteforce", "exfil", "unknown"] = Field(
        default="anomaly", description="Alert type"
    )
    time_window: TimeWindow = Field(..., description="Time window")
    entities: AlertEntities = Field(..., description="Primary entities")
    evidence: AlertEvidence = Field(..., description="Evidence")
    aggregation: AlertAggregation = Field(..., description="Aggregation info")
    agent: AlertAgent = Field(default_factory=AlertAgent, description="Agent info")
    twin: AlertTwin = Field(default_factory=AlertTwin, description="Twin info")
    tags: list[str] = Field(default_factory=list, description="Tags")
    notes: str = Field(default="", description="Notes")

    class Config:
        from_attributes = True


class AlertUpdateRequest(BaseModel):
    """Request for PATCH /alerts/{id} - DOC C C6.4."""
    status: Literal["new", "triaged", "investigating", "resolved", "false_positive"] | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    tags: list[str] | None = None
    notes: str | None = None


class AlertQueryParams(BaseModel):
    """Query parameters for GET /alerts - DOC C C6.4."""
    status: str | None = Field(default=None, description="Filter by status")
    severity: str | None = Field(default=None, description="Filter by severity")
    type: str | None = Field(default=None, description="Filter by type")
    start: str | None = Field(default=None, description="Start time filter ISO8601")
    end: str | None = Field(default=None, description="End time filter ISO8601")
    limit: int = Field(default=50, ge=1, le=1000, description="Max results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
