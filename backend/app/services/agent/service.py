import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.scoring_policy import SEVERITY_BASE, CONFIDENCE_CAP
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
    CompileHint,
)
from app.services.threat_enrichment.service import ThreatEnrichmentService

logger = get_logger(__name__)

_TYPE_ZH = {
    "anomaly": "异常",
    "scan": "扫描",
    "dos": "拒绝服务",
    "bruteforce": "暴力破解",
    "exfil": "数据外泄",
    "unknown": "未知",
}

_HYPOTHESIS_ZH = {
    "scan": "来自 {src} 的疑似端口扫描或网络侦察行为",
    "bruteforce": "针对 {proto}/{port} 的疑似暴力破解攻击",
    "dos": "针对 {dst} 的疑似拒绝服务攻击",
    "exfil": "来自 {src} 的疑似数据外泄行为",
    "anomaly": "检测到来自 {src} 的异常网络行为",
}

_HYPOTHESIS_EN = {
    "scan": "Possible port scanning or network reconnaissance from {src}",
    "bruteforce": "Possible brute-force attack targeting {proto}/{port}",
    "dos": "Possible denial-of-service attack against {dst}",
    "exfil": "Possible data exfiltration from {src}",
    "anomaly": "Anomalous network behavior detected from {src}",
}


def _load_json_field(value) -> dict:
    return json.loads(value) if isinstance(value, str) else value


class AgentService:
    """Generates structured triage/investigation/recommendation output; no actions executed."""

    def __init__(self, db: Session):
        self.db = db

    def triage(self, alert: Alert, language: str = "en") -> str:
        aggregation = _load_json_field(alert.aggregation)
        flow_count = aggregation.get("count_flows", 0)

        if language == "zh":
            summary = (
                f"检测到{alert.severity}级{_TYPE_ZH.get(alert.type, alert.type)}异常。"
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

        agent_data = _load_json_field(alert.agent)
        agent_data["triage_summary"] = summary
        alert.agent = json.dumps(agent_data)
        self.db.commit()

        logger.info(f"已为告警 {alert.id} 生成分诊摘要")
        return summary

    def investigate(self, alert: Alert, language: str = "en") -> InvestigationSchema:
        evidence = _load_json_field(alert.evidence)
        aggregation = _load_json_field(alert.aggregation)

        threat_context = self._run_enrichment(alert, evidence)

        hypothesis = self._build_hypothesis(alert, language, threat_context)
        why = self._build_why(alert, evidence, aggregation, language, threat_context)
        impact = self._assess_impact(alert, evidence)
        next_steps = self._suggest_next_steps(alert, language)

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

        inv_model = Investigation(
            id=inv_id,
            created_at=now,
            alert_id=alert.id,
            payload=investigation.model_dump_json(),
        )
        self.db.add(inv_model)

        agent_data = _load_json_field(alert.agent)
        agent_data["investigation_id"] = inv_id
        alert.agent = json.dumps(agent_data)

        self.db.commit()

        logger.info(f"已为告警 {alert.id} 生成调查报告 {inv_id}")
        return investigation

    def recommend(self, alert: Alert, language: str = "en") -> RecommendationSchema:
        evidence = _load_json_field(alert.evidence)

        threat_context = self._run_enrichment(alert, evidence)
        actions = self._build_actions(alert, language, threat_context)

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

        rec_model = Recommendation(
            id=rec_id,
            created_at=now,
            alert_id=alert.id,
            payload=recommendation.model_dump_json(),
        )
        self.db.add(rec_model)

        agent_data = _load_json_field(alert.agent)
        agent_data["recommendation_id"] = rec_id
        alert.agent = json.dumps(agent_data)

        self.db.commit()

        logger.info(f"已为告警 {alert.id} 生成建议 {rec_id}")
        return recommendation

    def _run_enrichment(self, alert: Alert, evidence: dict) -> ThreatContext | None:
        if not settings.THREAT_ENRICHMENT_ENABLED:
            return None
        return ThreatEnrichmentService().enrich(
            alert_type=alert.type,
            protocol=alert.primary_proto,
            port=alert.primary_dst_port,
            top_features=evidence.get("top_features", []),
        )

    def _build_hypothesis(
        self,
        alert: Alert,
        language: str = "en",
        threat_context: ThreatContext | None = None,
    ) -> str:
        templates = _HYPOTHESIS_ZH if language == "zh" else _HYPOTHESIS_EN
        base = templates.get(alert.type, templates["anomaly"]).format(
            src=alert.primary_src_ip,
            dst=alert.primary_dst_ip,
            proto=alert.primary_proto,
            port=alert.primary_dst_port,
        )

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
        reasons = []
        flow_count = aggregation.get("count_flows", 0)

        if language == "zh":
            reasons.append(f"在聚合窗口内检测到 {flow_count} 条异常流量")
        else:
            reasons.append(f"Detected {flow_count} anomalous flows in aggregation window")

        for feature in evidence.get("top_features", [])[:3]:
            if language == "zh":
                direction_zh = {"high": "偏高", "low": "偏低"}.get(
                    feature.get("direction", ""), feature.get("direction", ""),
                )
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
        scope = [
            f"dst_ip:{alert.primary_dst_ip}",
            f"service:{alert.primary_proto}/{alert.primary_dst_port}",
        ]

        flow_count = len(evidence.get("flow_ids", []))
        base_confidence = SEVERITY_BASE.get(alert.severity, 0.5)
        confidence = min(base_confidence + (flow_count * 0.01), CONFIDENCE_CAP)

        return {"scope": scope, "confidence": round(confidence, 2)}

    def _suggest_next_steps(self, alert: Alert, language: str = "en") -> list[str]:
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
        actions = []
        is_zh = language == "zh"
        high_priority = "high" if alert.severity in ["critical", "high"] else "medium"

        if alert.type in ["scan", "bruteforce"]:
            if is_zh:
                actions.append(RecommendedAction(
                    title=f"临时封禁源 IP {alert.primary_src_ip}",
                    priority=high_priority,
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
                    action_intent="executable",
                    compile_hint=CompileHint(
                        preferred_action_type="block_ip",
                        reason="封禁扫描/暴力破解来源 IP",
                    ),
                ))
            else:
                actions.append(RecommendedAction(
                    title=f"Temporary block source IP {alert.primary_src_ip}",
                    priority=high_priority,
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
                    action_intent="executable",
                    compile_hint=CompileHint(
                        preferred_action_type="block_ip",
                        reason="Block scanning/brute-force source",
                    ),
                ))

        if alert.type == "dos":
            if is_zh:
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
                    action_intent="executable",
                    compile_hint=CompileHint(
                        preferred_action_type="rate_limit_service",
                        reason="限制 DoS 攻击流量",
                    ),
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
                    action_intent="executable",
                    compile_hint=CompileHint(
                        preferred_action_type="rate_limit_service",
                        reason="Rate limit DoS traffic",
                    ),
                ))

        if alert.type == "exfil":
            if is_zh:
                actions.append(RecommendedAction(
                    title=f"封禁数据外泄源 IP {alert.primary_src_ip}",
                    priority=high_priority,
                    steps=[
                        f"添加防火墙规则封禁 {alert.primary_src_ip} 的出站流量",
                        "检查是否有已泄露数据需要处置",
                        "通知安全团队进行进一步调查",
                    ],
                    rollback=[
                        f"移除封禁 {alert.primary_src_ip} 的防火墙规则",
                        "验证合法出站流量已恢复",
                    ],
                    risk="如果 IP 为内部共享地址，可能影响其他用户的正常出站流量",
                    action_intent="executable",
                    compile_hint=CompileHint(
                        preferred_action_type="block_ip",
                        reason="封禁数据外泄来源以阻止泄露",
                    ),
                ))
            else:
                actions.append(RecommendedAction(
                    title=f"Block exfiltration source IP {alert.primary_src_ip}",
                    priority=high_priority,
                    steps=[
                        f"Add firewall rule to block outbound traffic from {alert.primary_src_ip}",
                        "Check if any exfiltrated data requires remediation",
                        "Notify security team for further investigation",
                    ],
                    rollback=[
                        f"Remove firewall rule blocking {alert.primary_src_ip}",
                        "Verify legitimate outbound traffic is restored",
                    ],
                    risk="May block legitimate outbound traffic if IP is shared internally",
                    action_intent="executable",
                    compile_hint=CompileHint(
                        preferred_action_type="block_ip",
                        reason="Block exfiltration source to stop data leakage",
                    ),
                ))

        if alert.type == "anomaly":
            if is_zh:
                actions.append(RecommendedAction(
                    title=f"隔离异常行为源主机 {alert.primary_src_ip}",
                    priority=high_priority,
                    steps=[
                        f"将 {alert.primary_src_ip} 从网络中隔离",
                        "检查主机上的可疑进程和连接",
                        "保留取证日志以供后续分析",
                    ],
                    rollback=[
                        f"恢复 {alert.primary_src_ip} 的网络连接",
                        "验证主机服务正常运行",
                    ],
                    risk="隔离可能导致该主机上的合法服务中断",
                    action_intent="executable",
                    compile_hint=CompileHint(
                        preferred_action_type="isolate_host",
                        reason="隔离异常主机以遏制潜在威胁",
                    ),
                ))
            else:
                actions.append(RecommendedAction(
                    title=f"Isolate anomalous source host {alert.primary_src_ip}",
                    priority=high_priority,
                    steps=[
                        f"Isolate {alert.primary_src_ip} from the network",
                        "Inspect suspicious processes and connections on the host",
                        "Preserve forensic logs for further analysis",
                    ],
                    rollback=[
                        f"Restore network connectivity for {alert.primary_src_ip}",
                        "Verify host services are operating normally",
                    ],
                    risk="Isolation may disrupt legitimate services running on this host",
                    action_intent="executable",
                    compile_hint=CompileHint(
                        preferred_action_type="isolate_host",
                        reason="Isolate anomalous host to contain potential threat",
                    ),
                ))

        mitre_risk_suffix = ""
        if threat_context and threat_context.techniques:
            top = threat_context.techniques[0]
            if is_zh:
                mitre_risk_suffix = f"。关联威胁技术: {top.technique_id} ({top.technique_name})"
            else:
                mitre_risk_suffix = f". Related threat technique: {top.technique_id} ({top.technique_name})"

        if is_zh:
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
                action_intent="monitoring",
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
                action_intent="monitoring",
            ))

        return actions
