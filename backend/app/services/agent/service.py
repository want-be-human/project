"""
智能体服务。
为分诊、调查与建议生成结构化输出。
"""

import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now, datetime_to_iso
from app.models.alert import Alert
from app.models.investigation import Investigation
from app.models.recommendation import Recommendation
from app.schemas.agent import (
    InvestigationSchema,
    InvestigationImpact,
    RecommendationSchema,
    RecommendedAction,
    ThreatContext,
)
from app.services.threat_enrichment.service import ThreatEnrichmentService

logger = get_logger(__name__)


class AgentService:
    """
用于智能体分析的服务。

遵循 DOC B B4.7 规范。
仅生成结构化输出，不执行动作。
"""

    def __init__(self, db: Session):
        self.db = db

    def triage(self, alert: Alert, language: str = "en") -> str:
        """
        Generate short triage summary for alert.
        
        Args:
            alert: Alert model instance
            language: 'zh' for Chinese, 'en' for English
            
        Returns:
            Triage summary string
        """
        aggregation = json.loads(alert.aggregation) if isinstance(alert.aggregation, str) else alert.aggregation
        
        flow_count = aggregation.get("count_flows", 0)
        
        if language == "zh":
            summary = (
                f"检测到{alert.severity}级{self._type_to_zh(alert.type)}异常。"
                f"来源IP {alert.primary_src_ip} 在时间窗口内产生了 {flow_count} 条异常流量，"
                f"目标服务为 {alert.primary_proto}/{alert.primary_dst_port}。"
                f"建议进一步调查并考虑临时封禁措施。"
            )
        else:
            summary = (
                f"Detected {alert.severity} severity {alert.type} anomaly. "
                f"Source IP {alert.primary_src_ip} generated {flow_count} anomalous flows "
                f"targeting {alert.primary_proto}/{alert.primary_dst_port}. "
                f"Recommend investigation and consider temporary blocking."
            )
        
        # 更新 alert 的 triage 摘要
        agent_data = json.loads(alert.agent) if isinstance(alert.agent, str) else alert.agent
        agent_data["triage_summary"] = summary
        alert.agent = json.dumps(agent_data)
        self.db.commit()
        
        logger.info(f"Generated triage for alert {alert.id}")
        return summary

    def investigate(self, alert: Alert, language: str = "en") -> InvestigationSchema:
        """
        Generate structured investigation for alert.
        
        Args:
            alert: Alert model instance
            language: 'zh' for Chinese, 'en' for English
            
        Returns:
            Investigation schema
        """
        evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
        aggregation = json.loads(alert.aggregation) if isinstance(alert.aggregation, str) else alert.aggregation
        
        # 威胁增强（模块 E）
        threat_context = self._run_enrichment(alert, evidence)

        # 基于告警类型构建假设
        hypothesis = self._build_hypothesis(alert, language, threat_context)
        
        # 构建推理依据
        why = self._build_why(alert, evidence, aggregation, language, threat_context)
        
        # 评估影响
        impact = self._assess_impact(alert, evidence)
        
        # 给出后续步骤
        next_steps = self._suggest_next_steps(alert, language)
        
        # 创建 investigation 记录
        inv_id = generate_uuid()
        now = utc_now()
        
        investigation = InvestigationSchema(
            version="1.1",
            id=inv_id,
            created_at=datetime_to_iso(now),
            alert_id=alert.id,
            hypothesis=hypothesis,
            why=why,
            impact=InvestigationImpact(
                scope=impact["scope"],
                confidence=impact["confidence"],
            ),
            next_steps=next_steps,
            safety_note="仅供参考，未执行任何操作。" if language == "zh" else "Advisory only; no actions executed.",
            threat_context=threat_context,
        )
        
        # 写入数据库
        inv_model = Investigation(
            id=inv_id,
            created_at=now,
            alert_id=alert.id,
            payload=investigation.model_dump_json(),
        )
        self.db.add(inv_model)
        
        # 更新 alert 的 agent 字段
        agent_data = json.loads(alert.agent) if isinstance(alert.agent, str) else alert.agent
        agent_data["investigation_id"] = inv_id
        alert.agent = json.dumps(agent_data)
        
        self.db.commit()
        
        logger.info(f"Generated investigation {inv_id} for alert {alert.id}")
        return investigation

    def recommend(self, alert: Alert, language: str = "en") -> RecommendationSchema:
        """
        Generate action recommendations for alert.
        
        Args:
            alert: Alert model instance
            language: 'zh' for Chinese, 'en' for English
            
        Returns:
            Recommendation schema
        """
        evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence

        # 威胁增强（模块 E）
        threat_context = self._run_enrichment(alert, evidence)

        # 基于告警类型与严重级别构建建议动作
        actions = self._build_actions(alert, language, threat_context)
        
        # 创建 recommendation 记录
        rec_id = generate_uuid()
        now = utc_now()
        
        recommendation = RecommendationSchema(
            version="1.1",
            id=rec_id,
            created_at=datetime_to_iso(now),
            alert_id=alert.id,
            actions=actions,
            threat_context=threat_context,
        )
        
        # 写入数据库
        rec_model = Recommendation(
            id=rec_id,
            created_at=now,
            alert_id=alert.id,
            payload=recommendation.model_dump_json(),
        )
        self.db.add(rec_model)
        
        # 更新 alert 的 agent 字段
        agent_data = json.loads(alert.agent) if isinstance(alert.agent, str) else alert.agent
        agent_data["recommendation_id"] = rec_id
        alert.agent = json.dumps(agent_data)
        
        self.db.commit()
        
        logger.info(f"Generated recommendation {rec_id} for alert {alert.id}")
        return recommendation

    def _type_to_zh(self, alert_type: str) -> str:
        """将告警类型翻译为中文。"""
        mapping = {
            "anomaly": "异常",
            "scan": "扫描",
            "dos": "拒绝服务",
            "bruteforce": "暴力破解",
            "exfil": "数据外泄",
            "unknown": "未知",
        }
        return mapping.get(alert_type, alert_type)

    def _run_enrichment(self, alert: Alert, evidence: dict) -> ThreatContext | None:
        """在启用时执行威胁增强；失败或关闭时返回 None。"""
        if not settings.THREAT_ENRICHMENT_ENABLED:
            return None
        top_features = evidence.get("top_features", [])
        return ThreatEnrichmentService().enrich(
            alert_type=alert.type,
            protocol=alert.primary_proto,
            port=alert.primary_dst_port,
            top_features=top_features,
        )

    def _build_hypothesis(self, alert: Alert, language: str = "en", threat_context: ThreatContext | None = None) -> str:
        """构建调查假设。"""
        if language == "zh":
            self._type_to_zh(alert.type)
            hypotheses = {
                "scan": f"来自 {alert.primary_src_ip} 的疑似端口扫描或网络侦察行为",
                "bruteforce": f"针对 {alert.primary_proto}/{alert.primary_dst_port} 的疑似暴力破解攻击",
                "dos": f"针对 {alert.primary_dst_ip} 的疑似拒绝服务攻击",
                "exfil": f"来自 {alert.primary_src_ip} 的疑似数据外泄行为",
                "anomaly": f"检测到来自 {alert.primary_src_ip} 的异常网络行为",
            }
        else:
            hypotheses = {
                "scan": f"Possible port scanning or network reconnaissance from {alert.primary_src_ip}",
                "bruteforce": f"Possible brute-force attack targeting {alert.primary_proto}/{alert.primary_dst_port}",
                "dos": f"Possible denial-of-service attack against {alert.primary_dst_ip}",
                "exfil": f"Possible data exfiltration from {alert.primary_src_ip}",
                "anomaly": f"Anomalous network behavior detected from {alert.primary_src_ip}",
            }
        base = hypotheses.get(alert.type, hypotheses["anomaly"])

        # 补充 MITRE 技术引用
        if threat_context and threat_context.techniques:
            top = threat_context.techniques[0]
            if language == "zh":
                base += f"（关联 MITRE ATT&CK: {top.technique_id} {top.technique_name}）"
            else:
                base += f" (maps to MITRE ATT&CK: {top.technique_id} {top.technique_name})"

        return base

    def _build_why(
        self,
        alert: Alert,
        evidence: dict,
        aggregation: dict,
        language: str = "en",
        threat_context: ThreatContext | None = None,
    ) -> list[str]:
        """构建支撑假设的推理依据。"""
        reasons = []
        
        flow_count = aggregation.get("count_flows", 0)
        if language == "zh":
            reasons.append(f"在聚合窗口内检测到 {flow_count} 条异常流量")
        else:
            reasons.append(f"Detected {flow_count} anomalous flows in aggregation window")
        
        top_features = evidence.get("top_features", [])
        for feature in top_features[:3]:
            if language == "zh":
                direction_zh = {"high": "偏高", "low": "偏低"}.get(feature.get('direction', ''), feature.get('direction', ''))
                reasons.append(
                    f"特征 '{feature['name']}' 数值{direction_zh}：{feature['value']}"
                )
            else:
                reasons.append(
                    f"Feature '{feature['name']}' shows {feature['direction']} value: {feature['value']}"
                )
        
        if language == "zh":
            reasons.append(f"基于异常评分，告警严重等级评估为 {alert.severity}")
        else:
            reasons.append(f"Alert severity assessed as {alert.severity} based on anomaly scores")

        # 追加基于 MITRE 的推理说明
        if threat_context and threat_context.techniques:
            tactics_str = ", ".join(threat_context.tactics)
            if language == "zh":
                reasons.append(
                    f"威胁情报关联：匹配 {len(threat_context.techniques)} 项 MITRE ATT&CK 技术，"
                    f"涉及战术阶段 {tactics_str}（置信度 {threat_context.enrichment_confidence:.0%}）"
                )
            else:
                reasons.append(
                    f"Threat intel: matched {len(threat_context.techniques)} MITRE ATT&CK technique(s) "
                    f"across tactics [{tactics_str}] (confidence {threat_context.enrichment_confidence:.0%})"
                )

        return reasons

    def _assess_impact(self, alert: Alert, evidence: dict) -> dict:
        """评估影响范围与置信度。"""
        scope = [
            f"dst_ip:{alert.primary_dst_ip}",
            f"service:{alert.primary_proto}/{alert.primary_dst_port}",
        ]
        
        # 基于 flow 数量与严重级别计算置信度
        flow_count = len(evidence.get("flow_ids", []))
        
        if alert.severity == "critical":
            base_confidence = 0.9
        elif alert.severity == "high":
            base_confidence = 0.8
        elif alert.severity == "medium":
            base_confidence = 0.65
        else:
            base_confidence = 0.5
        
        # 按 flow 数量调整
        confidence = min(base_confidence + (flow_count * 0.01), 0.95)
        
        return {"scope": scope, "confidence": round(confidence, 2)}

    def _suggest_next_steps(self, alert: Alert, language: str = "en") -> list[str]:
        """给出调查下一步建议。"""
        if language == "zh":
            steps = [
                f"查看 {alert.primary_src_ip} 的详细流量记录",
                "检查源 IP 是已知/内部地址还是外部地址",
                "验证目标服务是否需要此流量模式",
            ]
            if alert.type in ["scan", "bruteforce"]:
                steps.append("考虑临时封禁源 IP")
                steps.append("查看防火墙日志中的类似模式")
            if alert.type == "dos":
                steps.append("检查目标服务可用性")
                steps.append("考虑启用速率限制")
        else:
            steps = [
                f"Review detailed flow records for {alert.primary_src_ip}",
                "Check if source IP is known/internal or external",
                "Verify if target service requires this traffic pattern",
            ]
            if alert.type in ["scan", "bruteforce"]:
                steps.append("Consider temporary blocking of source IP")
                steps.append("Review firewall logs for similar patterns")
            if alert.type == "dos":
                steps.append("Check target service availability")
                steps.append("Consider rate limiting")
        
        return steps

    def _build_actions(
        self,
        alert: Alert,
        language: str = "en",
        threat_context: ThreatContext | None = None,
    ) -> list[RecommendedAction]:
        """基于告警构建推荐动作。"""
        actions = []
        
        if alert.type in ["scan", "bruteforce"]:
            if language == "zh":
                actions.append(RecommendedAction(
                    title=f"临时封禁源 IP {alert.primary_src_ip}",
                    priority="high" if alert.severity in ["critical", "high"] else "medium",
                    steps=[
                        f"添加防火墙规则封禁 {alert.primary_src_ip}",
                        "设置过期时间（建议：24 小时）",
                        "监控来自相关 IP 的持续尝试",
                    ],
                    rollback=[
                        f"移除封禁 {alert.primary_src_ip} 的防火墙规则",
                        "验证合法流量已恢复",
                    ],
                    risk="如果 IP 为共享/NAT 地址，可能会阻断合法流量",
                ))
            else:
                actions.append(RecommendedAction(
                    title=f"Temporary block source IP {alert.primary_src_ip}",
                    priority="high" if alert.severity in ["critical", "high"] else "medium",
                    steps=[
                        f"Add firewall rule to block {alert.primary_src_ip}",
                        "Set expiration time (recommended: 24 hours)",
                        "Monitor for continued attempts from related IPs",
                    ],
                    rollback=[
                        f"Remove firewall rule blocking {alert.primary_src_ip}",
                        "Verify legitimate traffic is restored",
                    ],
                    risk="May block legitimate traffic if IP is shared/NAT",
                ))
        
        if alert.type == "dos":
            if language == "zh":
                actions.append(RecommendedAction(
                    title=f"对 {alert.primary_proto}/{alert.primary_dst_port} 的流量进行速率限制",
                    priority="high",
                    steps=[
                        "为目标服务配置速率限制",
                        "根据正常流量模式设置阈值",
                        "启用阈值突破告警",
                    ],
                    rollback=[
                        "移除速率限制规则",
                        "恢复正常服务限制",
                    ],
                    risk="可能影响合法的高流量用户",
                ))
            else:
                actions.append(RecommendedAction(
                    title=f"Rate limit traffic to {alert.primary_proto}/{alert.primary_dst_port}",
                    priority="high",
                    steps=[
                        "Configure rate limiting for the target service",
                        "Set threshold based on normal traffic patterns",
                        "Enable alerting for threshold breaches",
                    ],
                    rollback=[
                        "Remove rate limiting rules",
                        "Restore normal service limits",
                    ],
                    risk="May impact legitimate high-volume users",
                ))
        
        # 构建 MITRE 风险后缀，增强上下文引用
        mitre_risk_suffix = ""
        if threat_context and threat_context.techniques:
            top = threat_context.techniques[0]
            if language == "zh":
                mitre_risk_suffix = f"。关联威胁技术: {top.technique_id} ({top.technique_name})"
            else:
                mitre_risk_suffix = f". Related threat technique: {top.technique_id} ({top.technique_name})"

        if language == "zh":
            actions.append(RecommendedAction(
                title="加强对相关实体的监控",
                priority="medium",
                steps=[
                    f"将 {alert.primary_src_ip} 加入监控列表",
                    "对受影响服务启用详细日志记录",
                    "设置类似模式的告警",
                ],
                rollback=[
                    "调查完成后从监控列表中移除",
                    "将日志级别恢复为正常",
                ],
                risk="日志存储和处理开销增加" + mitre_risk_suffix,
            ))
        else:
            actions.append(RecommendedAction(
                title="Enhance monitoring for related entities",
                priority="medium",
                steps=[
                    f"Add {alert.primary_src_ip} to watchlist",
                    "Enable detailed logging for affected services",
                    "Set up alerts for similar patterns",
                ],
                rollback=[
                    "Remove from watchlist after investigation",
                    "Reset logging to normal levels",
                ],
                risk="Increased log storage and processing" + mitre_risk_suffix,
            ))
        
        return actions
