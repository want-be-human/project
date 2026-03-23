"""
内部事件总线的领域事件模型。

定义与现有 WebSocket 事件名（DOC C C7.2）一致的事件类型，
以及与当前 WS JSON 包装格式兼容的 DomainEvent 基础模型。
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
    领域事件基类。

    其中 ``event_type`` + ``data`` 组合与现有
    WebSocket JSON 包装格式 ``{"event": str, "data": dict}`` 保持兼容。
    """

    event_id: str = Field(default_factory=generate_uuid)
    event_type: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"frozen": True}


def make_event(event_type: str, data: dict[str, Any]) -> DomainEvent:
    """用于创建 DomainEvent 的便捷工厂函数。"""
    return DomainEvent(event_type=event_type, data=data)
