"""
PcapFile schemas.
Strictly follows DOC C C1.1 PcapFile schema.
"""

from typing import Literal
from pydantic import BaseModel, Field


class PcapFileSchema(BaseModel):
    """
    PcapFile output schema - DOC C C1.1.
    
    All field names MUST match DOC C exactly.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the pcap file")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")
    status: Literal["uploaded", "processing", "done", "failed"] = Field(
        ..., description="Processing status"
    )
    progress: int = Field(default=0, ge=0, le=100, description="Processing progress 0-100")
    flow_count: int = Field(default=0, ge=0, description="Number of flows extracted")
    alert_count: int = Field(default=0, ge=0, description="Number of alerts generated")
    error_message: str | None = Field(default=None, description="Error message if failed")

    class Config:
        from_attributes = True  # Enable ORM mode for SQLAlchemy


class PcapProcessRequest(BaseModel):
    """Request body for POST /pcaps/{id}/process - DOC C C6.2."""

    mode: Literal["flows_only", "flows_and_detect"] = Field(
        default="flows_and_detect",
        description="Processing mode",
    )
    window_sec: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="Time window for flow aggregation in seconds",
    )


class PcapProcessResponse(BaseModel):
    """Response for POST /pcaps/{id}/process - DOC C C6.2."""

    accepted: bool = Field(default=True, description="Whether processing was accepted")
