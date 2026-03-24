"""
告警 Schema。
严格遵循 DOC C C1.3 告警规范。
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


# Alert schema 的嵌套对象
class TimeWindow(BaseModel):
    """告警时间窗口 - DOC C C1.3。"""
    start: str = Field(..., description="开始时间（ISO8601 UTC）")
    end: str = Field(..., description="结束时间（ISO8601 UTC）")


class PrimaryService(BaseModel):
    """主要服务信息 - DOC C C1.3。"""
    proto: str = Field(..., description="协议")
    dst_port: int = Field(..., description="目标端口")


class AlertEntities(BaseModel):
    """告警实体 - DOC C C1.3。"""
    primary_src_ip: str = Field(..., description="主要源 IP")
    primary_dst_ip: str = Field(..., description="主要目的 IP")
    primary_service: PrimaryService = Field(..., description="主要服务")


class TopFlowSummary(BaseModel):
    """证据中的高优先级流摘要 - DOC C C1.3。"""
    flow_id: str = Field(..., description="流 ID")
    anomaly_score: float = Field(..., description="异常分数")
    summary: str = Field(..., description="简要描述")


class TopFeature(BaseModel):
    """证据中的高贡献特征 - DOC C C1.3。"""
    name: str = Field(..., description="特征名")
    value: Any = Field(..., description="特征值")
    direction: Literal["high", "low"] = Field(..., description="异常方向")


class PcapRef(BaseModel):
    """证据中的 PCAP 引用 - DOC C C1.3。"""
    pcap_id: str = Field(..., description="PCAP ID")
    offset_hint: int | None = Field(default=None, description="字节偏移提示")


class AlertEvidence(BaseModel):
    """告警证据 - DOC C C1.3。"""
    flow_ids: list[str] = Field(default_factory=list, description="关联流 ID 列表")
    top_flows: list[TopFlowSummary] = Field(default_factory=list, description="高异常流列表")
    top_features: list[TopFeature] = Field(default_factory=list, description="主要贡献特征")
    pcap_ref: PcapRef | None = Field(default=None, description="PCAP 引用")


class AlertAggregation(BaseModel):
    """告警聚合信息 - DOC C C1.3。"""
    rule: str = Field(..., description="聚合规则")
    group_key: str = Field(..., description="分组键")
    count_flows: int = Field(..., description="组内流数量")
    # 新增可选字段（向后兼容旧数据）
    dimensions: list[str] | None = Field(default=None, description="聚合维度列表")
    composite_score: float | None = Field(default=None, description="复合严重度分数")
    score_breakdown: dict | None = Field(default=None, description="分数分项明细")


class AlertAgent(BaseModel):
    """告警智能体信息 - DOC C C1.3。"""
    triage_summary: str | None = Field(default=None, description="分诊摘要")
    investigation_id: str | None = Field(default=None, description="调查 ID")
    recommendation_id: str | None = Field(default=None, description="建议 ID")


class AlertTwin(BaseModel):
    """告警数字孪生信息 - DOC C C1.3。"""
    plan_id: str | None = Field(default=None, description="动作计划 ID")
    dry_run_id: str | None = Field(default=None, description="最新 dry run ID")


class AlertSchema(BaseModel):
    """
    告警输出 Schema - DOC C C1.3。

    所有字段名必须与 DOC C 完全一致。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="告警 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    severity: Literal["low", "medium", "high", "critical"] = Field(..., description="告警严重等级")
    status: Literal["new", "triaged", "investigating", "resolved", "false_positive"] = Field(
        default="new", description="告警状态"
    )
    type: Literal["anomaly", "scan", "dos", "bruteforce", "exfil", "unknown"] = Field(
        default="anomaly", description="告警类型"
    )
    time_window: TimeWindow = Field(..., description="时间窗口")
    entities: AlertEntities = Field(..., description="主要实体")
    evidence: AlertEvidence = Field(..., description="证据")
    aggregation: AlertAggregation = Field(..., description="聚合信息")
    agent: AlertAgent = Field(default_factory=AlertAgent, description="智能体信息")
    twin: AlertTwin = Field(default_factory=AlertTwin, description="数字孪生信息")
    tags: list[str] = Field(default_factory=list, description="标签")
    notes: str = Field(default="", description="备注")

    class Config:
        from_attributes = True


class AlertUpdateRequest(BaseModel):
    """PATCH /alerts/{id} 请求体 - DOC C C6.4。"""
    status: Literal["new", "triaged", "investigating", "resolved", "false_positive"] | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    tags: list[str] | None = None
    notes: str | None = None


class AlertQueryParams(BaseModel):
    """GET /alerts 查询参数 - DOC C C6.4。"""
    status: str | None = Field(default=None, description="按状态过滤")
    severity: str | None = Field(default=None, description="按严重等级过滤")
    type: str | None = Field(default=None, description="按类型过滤")
    start: str | None = Field(default=None, description="开始时间过滤（ISO8601）")
    end: str | None = Field(default=None, description="结束时间过滤（ISO8601）")
    limit: int = Field(default=50, ge=1, le=1000, description="最大结果数")
    offset: int = Field(default=0, ge=0, description="分页偏移量")
