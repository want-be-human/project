"""
FlowRecord schemas.
Strictly follows DOC C C1.2 FlowRecord schema.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


class FlowRecordSchema(BaseModel):
    """
    FlowRecord output schema - DOC C C1.2.
    
    All field names MUST match DOC C exactly.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the flow")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    pcap_id: str = Field(..., description="Reference to parent pcap")
    ts_start: str = Field(..., description="Flow start time ISO8601 UTC")
    ts_end: str = Field(..., description="Flow end time ISO8601 UTC")
    src_ip: str = Field(..., description="Source IP address")
    src_port: int = Field(..., ge=0, le=65535, description="Source port")
    dst_ip: str = Field(..., description="Destination IP address")
    dst_port: int = Field(..., ge=0, le=65535, description="Destination port")
    proto: Literal["TCP", "UDP", "ICMP", "OTHER"] = Field(..., description="Protocol")
    packets_fwd: int = Field(default=0, ge=0, description="Forward packets count")
    packets_bwd: int = Field(default=0, ge=0, description="Backward packets count")
    bytes_fwd: int = Field(default=0, ge=0, description="Forward bytes count")
    bytes_bwd: int = Field(default=0, ge=0, description="Backward bytes count")
    features: dict[str, Any] = Field(default_factory=dict, description="Extracted features")
    anomaly_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Anomaly score")
    label: str | None = Field(default=None, description="Optional label")

    class Config:
        from_attributes = True


class FlowQueryParams(BaseModel):
    """Query parameters for GET /flows - DOC C C6.3."""

    pcap_id: str | None = Field(default=None, description="Filter by pcap ID")
    src_ip: str | None = Field(default=None, description="Filter by source IP")
    dst_ip: str | None = Field(default=None, description="Filter by destination IP")
    proto: str | None = Field(default=None, description="Filter by protocol")
    min_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Minimum anomaly score")
    start: str | None = Field(default=None, description="Start time filter ISO8601")
    end: str | None = Field(default=None, description="End time filter ISO8601")
    limit: int = Field(default=100, ge=1, le=1000, description="Max results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
