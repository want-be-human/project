"""内部事件总线的领域事件模型 (v2)。

与 DOC C C7.2 WebSocket 事件名一致；保持与 {"event", "data"} 兼容。
v2 新增 trace_id / source / version（均有默认值，向后兼容）。
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.core.utils import generate_uuid


# 事件类型常量
# 必须与 contract/events/registry.json 和前端 events.ts 保持一致

# PCAP 处理
PCAP_PROCESS_PROGRESS = "pcap.process.progress"
PCAP_PROCESS_DONE = "pcap.process.done"
PCAP_PROCESS_FAILED = "pcap.process.failed"

# 告警
ALERT_CREATED = "alert.created"
ALERT_UPDATED = "alert.updated"

# 数字孪生
TWIN_DRYRUN_CREATED = "twin.dryrun.created"

# 场景运行
SCENARIO_RUN_DONE = "scenario.run.done"
SCENARIO_RUN_STARTED     = "scenario.run.started"
SCENARIO_STAGE_STARTED   = "scenario.stage.started"
SCENARIO_STAGE_COMPLETED = "scenario.stage.completed"
SCENARIO_STAGE_FAILED    = "scenario.stage.failed"
SCENARIO_RUN_PROGRESS    = "scenario.run.progress"

# 流水线可观测性
PIPELINE_RUN_STARTED = "pipeline.run.started"
PIPELINE_STAGE_COMPLETED = "pipeline.stage.completed"
PIPELINE_STAGE_FAILED = "pipeline.stage.failed"
PIPELINE_RUN_DONE = "pipeline.run.done"

# 批次生命周期
BATCH_CREATED            = "batch.created"
BATCH_UPLOAD_PROGRESS    = "batch.upload.progress"
BATCH_PROCESSING_STARTED = "batch.processing.started"
BATCH_COMPLETED          = "batch.completed"
BATCH_FAILED             = "batch.failed"
BATCH_CANCELLED          = "batch.cancelled"

# 批次文件状态
BATCH_FILE_STATUS        = "batch.file.status"

# 批次作业生命周期
BATCH_JOB_STARTED        = "batch.job.started"
BATCH_JOB_STAGE_STARTED  = "batch.job.stage.started"
BATCH_JOB_STAGE_COMPLETED = "batch.job.stage.completed"
BATCH_JOB_STAGE_FAILED   = "batch.job.stage.failed"
BATCH_JOB_COMPLETED      = "batch.job.completed"
BATCH_JOB_FAILED         = "batch.job.failed"

# 预留常量（未加入 ALL_EVENT_TYPES）
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
    BATCH_CREATED,
    BATCH_UPLOAD_PROGRESS,
    BATCH_PROCESSING_STARTED,
    BATCH_COMPLETED,
    BATCH_FAILED,
    BATCH_CANCELLED,
    BATCH_FILE_STATUS,
    BATCH_JOB_STARTED,
    BATCH_JOB_STAGE_STARTED,
    BATCH_JOB_STAGE_COMPLETED,
    BATCH_JOB_STAGE_FAILED,
    BATCH_JOB_COMPLETED,
    BATCH_JOB_FAILED,
]


class DomainEvent(BaseModel):
    """领域事件信封 v2；event_type + data 与 WS {"event", "data"} 兼容。"""

    event_id: str = Field(default_factory=generate_uuid)
    event_type: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
    return DomainEvent(
        event_type=event_type,
        data=data,
        trace_id=trace_id or generate_uuid(),
        source=source,
    )
