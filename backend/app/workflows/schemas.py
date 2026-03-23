"""
工作流执行轨迹的 Pydantic 模式。
用于 WorkflowExecution.stages_log JSON 中的阶段级日志记录。
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


class StageExecutionLog(BaseModel):
    """单个阶段执行记录，可序列化到 stages_log JSON。"""

    stage_name: str = Field(..., description="阶段标识符")
    status: Literal["pending", "running", "completed", "failed", "skipped"] = Field(
        ..., description="阶段执行状态"
    )
    started_at: str | None = Field(default=None, description="ISO8601 开始时间")
    completed_at: str | None = Field(default=None, description="ISO8601 结束时间")
    latency_ms: float | None = Field(default=None, description="执行耗时（毫秒）")
    input_snapshot: dict[str, Any] = Field(default_factory=dict, description="精简输入摘要")
    output_snapshot: dict[str, Any] = Field(default_factory=dict, description="精简输出摘要")
    error: str | None = Field(default=None, description="失败时的错误信息")


class WorkflowExecutionSchema(BaseModel):
    """面向 API 的工作流执行记录模式。"""

    version: str = Field(default="1.1")
    id: str
    alert_id: str
    workflow_type: str
    status: str
    created_at: str
    completed_at: str | None = None
    stages_log: list[StageExecutionLog] = Field(default_factory=list)

    class Config:
        from_attributes = True
