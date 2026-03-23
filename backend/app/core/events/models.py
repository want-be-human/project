"""
Domain event models for the internal event bus.

Defines event types matching existing WebSocket event names (DOC C C7.2)
and a DomainEvent base model compatible with the current WS JSON envelope.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.core.utils import generate_uuid


# ── 事件类型常量 ───────────────────────────────────────────────
# 必须与现有 WebSocket 事件名完全一致。

PCAP_PROCESS_PROGRESS = "pcap.process.progress"
PCAP_PROCESS_DONE = "pcap.process.done"
ALERT_CREATED = "alert.created"
ALERT_UPDATED = "alert.updated"
TWIN_DRYRUN_CREATED = "twin.dryrun.created"
SCENARIO_RUN_DONE = "scenario.run.done"

# 流水线可观测性事件
PIPELINE_RUN_STARTED = "pipeline.run.started"
PIPELINE_STAGE_COMPLETED = "pipeline.stage.completed"
PIPELINE_STAGE_FAILED = "pipeline.stage.failed"
PIPELINE_RUN_DONE = "pipeline.run.done"

ALL_EVENT_TYPES = [
    PCAP_PROCESS_PROGRESS,
    PCAP_PROCESS_DONE,
    ALERT_CREATED,
    ALERT_UPDATED,
    TWIN_DRYRUN_CREATED,
    SCENARIO_RUN_DONE,
    PIPELINE_RUN_STARTED,
    PIPELINE_STAGE_COMPLETED,
    PIPELINE_STAGE_FAILED,
    PIPELINE_RUN_DONE,
]


class DomainEvent(BaseModel):
    """
    Base domain event.

    The ``event_type`` + ``data`` pair is intentionally compatible with
    the existing WebSocket JSON envelope ``{"event": str, "data": dict}``.
    """

    event_id: str = Field(default_factory=generate_uuid)
    event_type: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"frozen": True}


def make_event(event_type: str, data: dict[str, Any]) -> DomainEvent:
    """Convenience factory for creating a DomainEvent."""
    return DomainEvent(event_type=event_type, data=data)
