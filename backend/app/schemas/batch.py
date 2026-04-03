"""
批量接入 Pydantic Schema。

定义 Batch / BatchFile / Job 的请求与响应模型。
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ── 请求模型 ──────────────────────────────────────────────────

class CreateBatchRequest(BaseModel):
    """创建批次请求。"""
    name: str | None = Field(default=None, description="批次名称，为空时自动生成")
    source: str | None = Field(default=None, description="数据来源标识")
    tags: list[str] | None = Field(default=None, description="用户自定义标签")


class CancelBatchRequest(BaseModel):
    """取消批次请求。"""
    reason: str | None = Field(default=None, description="取消原因")


# ── 响应模型 ──────────────────────────────────────────────────

class BatchSchema(BaseModel):
    """批次摘要。"""
    version: str
    id: str
    created_at: str
    name: str
    status: str
    source: str | None = None
    tags: list[str] | None = None
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    total_flow_count: int = 0
    total_alert_count: int = 0
    total_size_bytes: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    total_latency_ms: float | None = None
    error_message: str | None = None


class BatchFileSchema(BaseModel):
    """批次文件记录。"""
    version: str
    id: str
    created_at: str
    batch_id: str
    pcap_id: str | None = None
    original_filename: str
    size_bytes: int = 0
    sha256: str | None = None
    status: str
    sequence: int = 0
    flow_count: int = 0
    alert_count: int = 0
    error_message: str | None = None
    reject_reason: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    latency_ms: float | None = None
    retry_count: int = 0


class BatchDetailSchema(BatchSchema):
    """批次详情，含文件列表。"""
    files: list[BatchFileSchema] = []


class JobSchema(BaseModel):
    """作业记录。"""
    version: str
    id: str
    created_at: str
    batch_id: str
    batch_file_id: str
    pcap_id: str | None = None
    status: str
    current_stage: str | None = None
    stages_log: list[dict[str, Any]] | None = None
    retry_count: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    latency_ms: float | None = None
    error_message: str | None = None


class BatchStartResponse(BaseModel):
    """启动批次处理响应。"""
    batch_id: str
    jobs_created: int
    skipped_files: int


class BatchRetryResponse(BaseModel):
    """重试批次响应。"""
    batch_id: str
    jobs_created: int
    files_retried: int
