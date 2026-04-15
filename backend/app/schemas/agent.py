"""
智能体 Schema：Investigation 与 Recommendation。
严格遵循 DOC C C1.4 与 C1.5 规范。
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


# 威胁增强 Schema（模块 E）

class ThreatTechnique(BaseModel):
    """增强流程匹配到的单个 MITRE ATT&CK 技术。"""
    technique_id: str = Field(..., description="MITRE 技术 ID，例如 T1595")
    technique_name: str = Field(..., description="技术名称")
    technique_name_zh: str | None = Field(default=None, description="技术名称（中文）")
    tactic_id: str = Field(..., description="MITRE 战术 ID，例如 TA0043")
    tactic_name: str = Field(..., description="战术名称")
    tactic_name_zh: str | None = Field(default=None, description="战术名称（中文）")
    confidence: float = Field(..., ge=0.0, le=1.0, description="匹配置信度")
    description: str = Field(default="", description="简要描述")
    description_zh: str | None = Field(default=None, description="简要描述（中文）")
    intel_refs: list[str] = Field(default_factory=list, description="参考链接")


class ThreatContext(BaseModel):
    """威胁情报增强结果。"""
    techniques: list[ThreatTechnique] = Field(default_factory=list, description="匹配到的 MITRE 技术")
    tactics: list[str] = Field(default_factory=list, description="去重后的战术名称")
    tactics_zh: list[str] | None = Field(default=None, description="去重后的战术名称（中文）")
    enrichment_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="整体增强置信度")
    enrichment_source: str = Field(default="local_mitre_v1", description="增强数据来源标识")


class InvestigationImpact(BaseModel):
    """调查中的影响评估。"""
    scope: list[str] = Field(default_factory=list, description="受影响范围")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信分数")


class InvestigationSchema(BaseModel):
    """
    Investigation 输出 Schema - DOC C C1.4。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="调查 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    alert_id: str = Field(..., description="关联告警 ID")
    hypothesis: str = Field(..., description="调查假设")
    why: list[str] = Field(default_factory=list, description="支撑假设的理由")
    impact: InvestigationImpact = Field(..., description="影响评估")
    next_steps: list[str] = Field(default_factory=list, description="推荐下一步")
    safety_note: str = Field(
        default="Advisory only; no actions executed.",
        description="安全免责声明"
    )
    threat_context: ThreatContext | None = Field(
        default=None,
        description="可选的 MITRE ATT&CK 威胁增强上下文",
    )

    class Config:
        from_attributes = True


class CompileHint(BaseModel):
    """编译器提示，提供首选 action_type 映射。"""
    preferred_action_type: str = Field(..., description="建议的 action_type，例如 'block_ip'")
    reason: str = Field(default="", description="映射建议的原因")


class RecommendedAction(BaseModel):
    """Recommendation 中的单个动作 - DOC C C1.5。"""
    title: str = Field(..., description="动作标题")
    priority: Literal["high", "medium", "low"] = Field(..., description="动作优先级")
    steps: list[str] = Field(default_factory=list, description="执行步骤")
    rollback: list[str] = Field(default_factory=list, description="回滚步骤")
    risk: str = Field(default="", description="风险描述")
    action_intent: Literal["executable", "monitoring", "advisory"] = Field(
        default="executable",
        description="动作意图分类：executable 可编译, monitoring 监控类, advisory 建议类",
    )
    compile_hint: CompileHint | None = Field(
        default=None,
        description="编译器提示，提供首选 action_type 映射",
    )


class RecommendationSchema(BaseModel):
    """
    Recommendation 输出 Schema - DOC C C1.5。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="建议 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    alert_id: str = Field(..., description="关联告警 ID")
    actions: list[RecommendedAction] = Field(default_factory=list, description="推荐动作列表")
    threat_context: ThreatContext | None = Field(
        default=None,
        description="可选的 MITRE ATT&CK 威胁增强上下文",
    )

    class Config:
        from_attributes = True


# Triage 请求/响应 - DOC C C6.5
class TriageRequest(BaseModel):
    """POST /alerts/{id}/triage 的请求体 - DOC C C6.5。"""
    language: Literal["zh", "en"] = Field(default="en", description="输出语言")


class TriageResponse(BaseModel):
    """POST /alerts/{id}/triage 的响应体 - DOC C C6.5。"""
    triage_summary: str = Field(..., description="分诊摘要文本")


class LanguageRequest(BaseModel):
    """investigate/recommend 的可选语言请求体。"""
    language: Literal["zh", "en"] = Field(default="en", description="输出语言")
