"""
内部事件总线的领域事件模型（v2）。

定义与现有 WebSocket 事件名（DOC C C7.2）一致的事件类型，
以及与当前 WS JSON 包装格式兼容的 DomainEvent 基础模型。

v2 新增 trace_id / source / version 字段，为后续分布式追踪和
Redis/Kafka 替换预留接口，同时保持与现有信封格式的向后兼容。
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.core.utils import generate_uuid


# ── 事件类型常量 ───────────────────────────────────────────────
# 必须与 contract/events/registry.json 和前端 events.ts 保持一致。

# PCAP 处理事件
PCAP_PROCESS_PROGRESS = "pcap.process.progress"
PCAP_PROCESS_DONE = "pcap.process.done"
PCAP_PROCESS_FAILED = "pcap.process.failed"

# 告警事件
ALERT_CREATED = "alert.created"
ALERT_UPDATED = "alert.updated"

# 数字孪生事件
TWIN_DRYRUN_CREATED = "twin.dryrun.created"

# 场景运行事件
SCENARIO_RUN_DONE = "scenario.run.done"
SCENARIO_RUN_STARTED     = "scenario.run.started"
SCENARIO_STAGE_STARTED   = "scenario.stage.started"
SCENARIO_STAGE_COMPLETED = "scenario.stage.completed"
SCENARIO_STAGE_FAILED    = "scenario.stage.failed"
SCENARIO_RUN_PROGRESS    = "scenario.run.progress"

# 流水线可观测性事件
PIPELINE_RUN_STARTED = "pipeline.run.started"
PIPELINE_STAGE_COMPLETED = "pipeline.stage.completed"
PIPELINE_STAGE_FAILED = "pipeline.stage.failed"
PIPELINE_RUN_DONE = "pipeline.run.done"

# 预留事件常量（暂不加入 ALL_EVENT_TYPES，仅供后续扩展使用）
PCAP_BATCH_STARTED = "pcap.batch.started"
FLOW_FEATURES_DONE = "flow.features.done"
TWIN_DRYRUN_EVALUATED = "twin.dryrun.evaluated"
DASHBOARD_METRICS_UPDATED = "dashboard.metrics.updated"

ALL_EVENT_TYPES = [
    PCAP_PROCESS_PROGRESS,
    PCAP_PROCESS_DONE,
    PCAP_PROCESS_FAILED,
    ALERT_CREATED,
    ALERT_UPDATED,
    TWIN_DRYRUN_CREATED,
    SCENARIO_RUN_DONE,
    SCENARIO_RUN_STARTED,
    SCENARIO_STAGE_STARTED,
    SCENARIO_STAGE_COMPLETED,
    SCENARIO_STAGE_FAILED,
    SCENARIO_RUN_PROGRESS,
    PIPELINE_RUN_STARTED,
    PIPELINE_STAGE_COMPLETED,
    PIPELINE_STAGE_FAILED,
    PIPELINE_RUN_DONE,
]


class DomainEvent(BaseModel):
    """
    领域事件信封 v2。

    其中 ``event_type`` + ``data`` 组合与现有
    WebSocket JSON 包装格式 ``{"event": str, "data": dict}`` 保持兼容。

    v2 新增字段（均有默认值，向后兼容）：
    - trace_id: 请求级追踪 ID，便于日后分布式追踪
    - source: 事件来源标识
    - version: 信封版本号
    """

    event_id: str = Field(default_factory=generate_uuid)
    event_type: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # ── v2 新增字段 ──
    trace_id: str = Field(default_factory=generate_uuid)
    source: str = Field(default="nettwin-soc")
    version: str = Field(default="2")

    model_config = {"frozen": True}


def make_event(
    event_type: str,
    data: dict[str, Any],
    *,
    trace_id: str | None = None,
    source: str = "nettwin-soc",
) -> DomainEvent:
    """用于创建 DomainEvent 的便捷工厂函数。"""
    return DomainEvent(
        event_type=event_type,
        data=data,
        trace_id=trace_id or generate_uuid(),
        source=source,
    )
