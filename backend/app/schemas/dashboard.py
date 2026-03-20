"""
仪表盘聚合响应 Schema 定义。
用于 GET /api/v1/dashboard/summary 端点的响应数据结构。
"""

from typing import Any

from pydantic import BaseModel, Field


class PipelineSnapshotSchema(BaseModel):
    """最后一次流水线运行快照"""

    id: str = Field(..., description="流水线运行 ID")
    pcap_id: str = Field(..., description="关联的 PCAP 文件 ID")
    status: str = Field(..., description="运行状态")
    stages: list[dict[str, Any]] = Field(
        default_factory=list, description="解析后的 stages_log"
    )
    total_latency_ms: float | None = Field(
        default=None, description="总耗时（毫秒）"
    )
    failed_stages: list[str] = Field(
        default_factory=list, description="失败的阶段列表"
    )


class OverviewSchema(BaseModel):
    """总览指标"""

    # PCAP 相关
    pcap_total: int = Field(..., description="PCAP 文件总数")
    pcap_processing: int = Field(..., description="处理中的 PCAP 数量")
    pcap_last_done_at: str | None = Field(
        default=None, description="最后完成时间（ISO8601）"
    )
    pcap_24h_count: int = Field(..., description="24 小时内上传数量")

    # Flow 相关
    flow_total: int = Field(..., description="Flow 总数")
    flow_24h_count: int = Field(..., description="24 小时内新增 Flow 数量")

    # Alert 相关
    alert_total: int = Field(..., description="告警总数")
    alert_open_count: int = Field(
        ..., description="开放告警数量（new + triaged + investigating）"
    )
    alert_by_severity: dict[str, int] = Field(
        ..., description='按严重程度分组的告警计数，如 {"low":0, "medium":0, "high":0, "critical":0}'
    )
    alert_by_type: dict[str, int] = Field(
        ..., description='按类型分组的告警计数，如 {"scan":0, "bruteforce":0, ...}'
    )
    alert_last_analysis_at: str | None = Field(
        default=None, description="最后分析时间（ISO8601）"
    )

    # Dry-Run 相关
    dryrun_total: int = Field(..., description="Dry-Run 总数")
    dryrun_avg_disruption_risk: float = Field(
        ..., description="平均中断风险值"
    )
    dryrun_last_result: dict[str, Any] | None = Field(
        default=None, description="最后一次 dry-run 的 impact 摘要"
    )

    # Scenario 相关
    scenario_total: int = Field(..., description="场景总数")
    scenario_last_status: str | None = Field(
        default=None, description='最后运行状态："pass" | "fail" | None'
    )
    scenario_pass_rate: float = Field(
        ..., description="场景通过率（0.0 ~ 1.0）"
    )

    # Pipeline 相关
    pipeline_last_run: PipelineSnapshotSchema | None = Field(
        default=None, description="最后一次流水线运行快照"
    )

    # 新增：Sparkline 趋势数据（最近 7 天每日计数）
    pcap_trend: list[int] = Field(
        default_factory=list,
        description="最近 7 天每日 PCAP 上传数量数组",
    )
    flow_trend: list[int] = Field(
        default_factory=list,
        description="最近 7 天每日 Flow 新增数量数组",
    )
    alert_open_trend: list[int] = Field(
        default_factory=list,
        description="最近 7 天每日开放告警数量数组",
    )


class TrendDaySchema(BaseModel):
    """单日趋势数据"""

    date: str = Field(..., description='日期，如 "2024-01-15"')
    low: int = Field(..., description="低危告警数量")
    medium: int = Field(..., description="中危告警数量")
    high: int = Field(..., description="高危告警数量")
    critical: int = Field(..., description="严重告警数量")


class TrendsSchema(BaseModel):
    """告警趋势"""

    days: list[TrendDaySchema] = Field(
        default_factory=list, description="按天分组的趋势数据"
    )


class DistributionItemSchema(BaseModel):
    """分布项"""

    type: str = Field(..., description="告警类型")
    count: int = Field(..., description="该类型的告警数量")


class DistributionsSchema(BaseModel):
    """告警类型分布"""

    items: list[DistributionItemSchema] = Field(
        default_factory=list, description="按类型分组的分布数据"
    )


class TopologySnapshotSchema(BaseModel):
    """迷你拓扑快照"""

    node_count: int = Field(..., description="节点数量")
    edge_count: int = Field(..., description="边数量")
    top_risk_nodes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="前 10 个高风险节点，格式 [{id, label, risk}, ...]",
    )
    top_risk_edges: list[dict[str, Any]] = Field(
        default_factory=list,
        description="前 10 条高风险边，格式 [{id, source, target, risk}, ...]",
    )


class ActivityEventSchema(BaseModel):
    """活动事件"""

    id: str = Field(..., description="事件 ID")
    type: str = Field(
        ..., description='事件类型："pcap" | "pipeline" | "alert" | "dryrun" | "scenario"'
    )
    summary: str = Field(..., description="事件摘要")
    detail: dict[str, Any] = Field(
        default_factory=dict, description="类型特定的额外信息"
    )
    created_at: str = Field(..., description="创建时间（ISO8601）")


class DashboardSummarySchema(BaseModel):
    """仪表盘聚合响应"""

    overview: OverviewSchema = Field(..., description="总览指标")
    trends: TrendsSchema = Field(..., description="告警趋势")
    distributions: DistributionsSchema = Field(..., description="告警类型分布")
    topology_snapshot: TopologySnapshotSchema = Field(
        ..., description="迷你拓扑快照"
    )
    recent_activity: list[ActivityEventSchema] = Field(
        default_factory=list, description="最近活动事件列表"
    )
