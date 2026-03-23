"""
Scenario 相关 Schema：Scenario 与 ScenarioRunResult。
严格遵循 DOC C C4.1 与 C4.2。
"""

from typing import Literal
from pydantic import BaseModel, Field


# Scenario Schema（DOC C C4.1）
class ScenarioPcapRef(BaseModel):
    """场景中的 PCAP 引用。"""
    pcap_id: str = Field(..., description="PCAP 文件 ID")


class MustHaveExpectation(BaseModel):
    """场景中的必选期望项 - DOC C C4.1。"""
    type: str = Field(..., description="告警类型")
    severity_at_least: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="最低严重等级"
    )


class ScenarioExpectations(BaseModel):
    """场景期望配置 - DOC C C4.1。"""
    min_alerts: int = Field(default=0, ge=0, description="期望的最少告警数")
    must_have: list[MustHaveExpectation] = Field(
        default_factory=list, description="必需告警模式"
    )
    evidence_chain_contains: list[str] = Field(
        default_factory=list, description="必需证据链节点"
    )
    dry_run_required: bool = Field(default=False, description="是否要求 dry run")


class ScenarioSchema(BaseModel):
    """
    场景输出 Schema - DOC C C4.1。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="场景 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    name: str = Field(..., description="场景名称")
    description: str = Field(default="", description="场景描述")
    pcap_ref: ScenarioPcapRef = Field(..., description="PCAP 引用")
    expectations: ScenarioExpectations = Field(..., description="场景期望")
    tags: list[str] = Field(default_factory=list, description="标签")

    class Config:
        from_attributes = True


# ScenarioRunResult Schema（DOC C C4.2）
class ScenarioCheck(BaseModel):
    """场景运行中的单项检查结果 - DOC C C4.2。"""
    name: str = Field(..., description="检查项名称")
    pass_: bool = Field(alias="pass", description="是否通过")
    details: dict = Field(default_factory=dict, description="检查详情")

    class Config:
        populate_by_name = True


class ScenarioMetrics(BaseModel):
    """场景运行指标 - DOC C C4.2。"""
    alert_count: int = Field(default=0, description="告警总数")
    high_severity_count: int = Field(default=0, description="高严重等级告警数")
    avg_dry_run_risk: float = Field(default=0.0, description="平均 dry run 风险")


class ScenarioRunResultSchema(BaseModel):
    """
    场景运行结果输出 Schema - DOC C C4.2。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="运行结果 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    scenario_id: str = Field(..., description="关联场景 ID")
    status: Literal["pass", "fail"] = Field(..., description="整体状态")
    checks: list[ScenarioCheck] = Field(default_factory=list, description="检查结果")
    metrics: ScenarioMetrics = Field(default_factory=ScenarioMetrics, description="运行指标")

    class Config:
        from_attributes = True


# 创建 scenario 请求 - DOC C C6.9
class CreateScenarioRequest(BaseModel):
    """POST /scenarios 请求体 - DOC C C6.9。"""
    name: str = Field(..., description="场景名称")
    description: str = Field(default="", description="描述")
    pcap_ref: ScenarioPcapRef = Field(..., description="PCAP 引用")
    expectations: ScenarioExpectations = Field(..., description="期望配置")
    tags: list[str] = Field(default_factory=list, description="标签")


# Scenario 查询参数
class ScenarioQueryParams(BaseModel):
    """GET /scenarios 查询参数。"""
    limit: int = Field(default=50, ge=1, le=1000, description="最大结果数")
    offset: int = Field(default=0, ge=0, description="分页偏移量")
