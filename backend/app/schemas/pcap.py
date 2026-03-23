"""
PcapFile Schema。
严格遵循 DOC C C1.1 PcapFile 规范。
"""

from typing import Literal
from pydantic import BaseModel, Field


class PcapFileSchema(BaseModel):
    """
    PcapFile 输出 Schema - DOC C C1.1。

    所有字段名必须与 DOC C 完全一致。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="pcap 文件 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    filename: str = Field(..., description="原始文件名")
    size_bytes: int = Field(..., description="文件大小（字节）")
    status: Literal["uploaded", "processing", "done", "failed"] = Field(
        ..., description="处理状态"
    )
    progress: int = Field(default=0, ge=0, le=100, description="处理进度 0-100")
    flow_count: int = Field(default=0, ge=0, description="提取到的流数量")
    alert_count: int = Field(default=0, ge=0, description="生成的告警数量")
    error_message: str | None = Field(default=None, description="失败时的错误信息")

    class Config:
        from_attributes = True  # 为 SQLAlchemy 启用 ORM 模式


class PcapProcessRequest(BaseModel):
    """POST /pcaps/{id}/process 请求体 - DOC C C6.2。"""

    mode: Literal["flows_only", "flows_and_detect"] = Field(
        default="flows_and_detect",
        description="处理模式",
    )
    window_sec: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="流聚合时间窗（秒）",
    )


class PcapProcessResponse(BaseModel):
    """POST /pcaps/{id}/process 响应体 - DOC C C6.2。"""

    accepted: bool = Field(default=True, description="是否已受理处理请求")
