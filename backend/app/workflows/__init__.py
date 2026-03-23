"""
用于智能体操作的工作流引擎。
提供可编排、可扩展且兼容回退策略的工作流阶段。

为避免循环依赖，请在需要处直接导入引擎与阶段：
    from app.workflows.engine import WorkflowEngine
    from app.workflows.stages.triage import TriageStage
"""

from app.workflows.models import WorkflowExecution
from app.workflows.schemas import StageExecutionLog, WorkflowExecutionSchema

__all__ = [
    "WorkflowExecution",
    "StageExecutionLog",
    "WorkflowExecutionSchema",
]
