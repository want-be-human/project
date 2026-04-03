"""
标准化分析 API Schema 定义。
用于 /api/v1/analytics/* 端点的请求与响应数据结构。
"""

from typing import Any

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════
# 评分通用结构
# ══════════════════════════════════════════════════════════════


class ScoreFactorSchema(BaseModel):
    """评分因子"""

    name: str = Field(..., description="因子名称")
    value: float = Field(..., description="因子值")
    weight: float = Field(..., description="因子权重")
    description: str = Field(default="", description="因子说明")


class ScoreResultSchema(BaseModel):
    """标准化评分结果"""

    value: float = Field(..., description="评分值（0-100，-1 表示未实现）")
    factors: list[ScoreFactorSchema] = Field(
        default_factory=list, description="评分因子列表"
    )
    score_version: str = Field(..., description="评分算法版本，如 posture_v1")
    computed_at: str = Field(..., description="计算时间（ISO8601）")
    explain: str | None = Field(default=None, description="可读的评分解释")
    breakdown: dict[str, Any] | None = Field(
        default=None, description="详细分解数据"
    )


# ══════════════════════════════════════════════════════════════
# Overview API
# ══════════════════════════════════════════════════════════════


class AnalyticsOverviewSchema(BaseModel):
    """统一总览（含评分）"""

    # PCAP 相关
    pcap_total: int = Field(..., description="PCAP 文件总数")
    pcap_processing: int = Field(..., description="处理中的 PCAP 数量")
    pcap_24h_count: int = Field(..., description="24 小时内上传数量")

    # Flow 相关
    flow_total: int = Field(..., description="Flow 总数")
    flow_24h_count: int = Field(..., description="24 小时内新增 Flow 数量")

    # Alert 相关
    alert_total: int = Field(..., description="告警总数")
    alert_open_count: int = Field(..., description="开放告警数量")
    alert_by_severity: dict[str, int] = Field(
        ..., description="按严重程度分组的告警计数"
    )

    # Dry-Run 相关
    dryrun_total: int = Field(..., description="Dry-Run 总数")
    dryrun_avg_disruption_risk: float = Field(
        ..., description="平均中断风险值"
    )

    # Scenario 相关
    scenario_total: int = Field(..., description="场景总数")
    scenario_pass_rate: float = Field(..., description="场景通过率（0.0 ~ 1.0）")

    # 内嵌评分
    posture_score: ScoreResultSchema | None = Field(
        default=None, description="安全态势评分"
    )


# ══════════════════════════════════════════════════════════════
# Top Assets API
# ══════════════════════════════════════════════════════════════


class TopAssetItemSchema(BaseModel):
    """高风险资产条目"""

    id: str = Field(..., description="资产 ID")
    label: str = Field(..., description="资产标签")
    risk: float = Field(..., description="风险值")
    category: str = Field(
        default="node", description='资产类别："node" | "edge" | "alert_type"'
    )


class TopAssetsSchema(BaseModel):
    """高风险资产排行"""

    top_risk_nodes: list[TopAssetItemSchema] = Field(
        default_factory=list, description="高风险节点排行"
    )
    top_risk_edges: list[TopAssetItemSchema] = Field(
        default_factory=list, description="高风险边排行"
    )
    top_alert_types: list[dict[str, Any]] = Field(
        default_factory=list, description="高频告警类型排行"
    )
