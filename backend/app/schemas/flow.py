"""
FlowRecord Schema。
严格遵循 DOC C C1.2 FlowRecord 规范。
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


class FlowRecordSchema(BaseModel):
    """
    FlowRecord 输出 Schema - DOC C C1.2。

    所有字段名必须与 DOC C 完全一致。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="流 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    pcap_id: str = Field(..., description="所属 pcap 引用")
    ts_start: str = Field(..., description="流开始时间（ISO8601 UTC）")
    ts_end: str = Field(..., description="流结束时间（ISO8601 UTC）")
    src_ip: str = Field(..., description="源 IP 地址")
    src_port: int = Field(..., ge=0, le=65535, description="源端口")
    dst_ip: str = Field(..., description="目的 IP 地址")
    dst_port: int = Field(..., ge=0, le=65535, description="目的端口")
    proto: Literal["TCP", "UDP", "ICMP", "OTHER"] = Field(..., description="协议")
    packets_fwd: int = Field(default=0, ge=0, description="正向报文数")
    packets_bwd: int = Field(default=0, ge=0, description="反向报文数")
    bytes_fwd: int = Field(default=0, ge=0, description="正向字节数")
    bytes_bwd: int = Field(default=0, ge=0, description="反向字节数")
    features: dict[str, Any] = Field(default_factory=dict, description="提取特征")
    anomaly_score: float | None = Field(default=None, ge=0.0, le=1.0, description="异常分数")
    label: str | None = Field(default=None, description="可选标签")

    class Config:
        from_attributes = True


class FlowQueryParams(BaseModel):
    """GET /flows 查询参数 - DOC C C6.3。"""

    pcap_id: str | None = Field(default=None, description="按 pcap ID 过滤")
    src_ip: str | None = Field(default=None, description="按源 IP 过滤")
    dst_ip: str | None = Field(default=None, description="按目的 IP 过滤")
    proto: str | None = Field(default=None, description="按协议过滤")
    min_score: float | None = Field(default=None, ge=0.0, le=1.0, description="最小异常分数")
    start: str | None = Field(default=None, description="开始时间过滤（ISO8601）")
    end: str | None = Field(default=None, description="结束时间过滤（ISO8601）")
    limit: int = Field(default=100, ge=1, le=1000, description="最大结果数")
    offset: int = Field(default=0, ge=0, description="分页偏移量")
