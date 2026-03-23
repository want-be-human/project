"""
威胁增强服务。
基于本地静态知识文件提供轻量级 MITRE ATT&CK 映射与威胁上下文增强。
无需外部依赖。
"""

import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.schemas.agent import ThreatContext, ThreatTechnique

logger = get_logger(__name__)

# ── 模块级缓存：每个进程仅加载一次 ─────────────────────────────────────────

_KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
_mitre_mapping: dict | None = None
_port_protocol_rules: dict | None = None


def _load_json(path: Path) -> dict:
    """使用 UTF-8 编码加载 JSON 文件。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_mitre_mapping() -> dict:
    global _mitre_mapping
    if _mitre_mapping is None:
        _mitre_mapping = _load_json(_KNOWLEDGE_DIR / "mitre_mapping.json")
    return _mitre_mapping


def _get_port_protocol_rules() -> dict:
    global _port_protocol_rules
    if _port_protocol_rules is None:
        _port_protocol_rules = _load_json(_KNOWLEDGE_DIR / "port_protocol_rules.json")
    return _port_protocol_rules


class ThreatEnrichmentService:
    """
    基于本地 MITRE ATT&CK 映射与端口/协议启发规则的轻量威胁情报增强服务。

    该服务无状态，不依赖数据库会话、外部 API 或重型基础设施。
    """

    def enrich(
        self,
        alert_type: str,
        protocol: str,
        port: int,
        top_features: list[dict[str, Any]] | None = None,
        evidence_keywords: list[str] | None = None,
    ) -> ThreatContext | None:
        """
        基于给定告警参数生成 ThreatContext。

        当无法执行增强或出现意外错误时返回 ``None``（静默降级）。
        """
        try:
            return self._do_enrich(
                alert_type=alert_type,
                protocol=protocol.lower() if protocol else "",
                port=port,
                top_features=top_features or [],
                evidence_keywords=evidence_keywords or [],
            )
        except Exception:
            logger.warning("Threat enrichment failed – degrading gracefully", exc_info=True)
            return None

    # ── 内部实现 ───────────────────────────────────────────────────────

    def _do_enrich(
        self,
        alert_type: str,
        protocol: str,
        port: int,
        top_features: list[dict[str, Any]],
        evidence_keywords: list[str],
    ) -> ThreatContext | None:
        mapping = _get_mitre_mapping()
        rules = _get_port_protocol_rules()

        # 1. 基于 alert_type 的基础技术匹配
        type_entry = mapping.get(alert_type, mapping.get("unknown", {}))
        techniques_raw: list[dict] = list(type_entry.get("techniques", []))

        # 2. 基于端口的补充技术匹配
        for rule in rules.get("port_rules", []):
            if port in rule["ports"] and protocol in rule.get("protocols", []):
                techniques_raw.extend(rule["techniques"])

        # 3. 仅基于协议的规则（如 ICMP）
        for rule in rules.get("protocol_rules", []):
            if protocol in rule.get("protocols", []):
                techniques_raw.extend(rule["techniques"])

        if not techniques_raw:
            return None

        # 4. 按 technique_id 去重，保留最高 base_confidence
        seen: dict[str, dict] = {}
        for t in techniques_raw:
            tid = t["technique_id"]
            if tid not in seen or t.get("base_confidence", 0) > seen[tid].get("base_confidence", 0):
                seen[tid] = dict(t)  # shallow copy
        unique_techniques = list(seen.values())

        # 5. 基于特征的置信度提升
        feature_boost = rules.get("feature_boost_rules", {})
        feature_map = {f.get("name", ""): f for f in top_features}

        for fname, rule in feature_boost.items():
            feature = feature_map.get(fname)
            if feature is None:
                continue
            try:
                val = float(feature.get("value", 0))
            except (TypeError, ValueError):
                continue

            should_boost = False
            if "threshold_high" in rule and val >= rule["threshold_high"]:
                should_boost = True
            if "threshold_low" in rule and val <= rule["threshold_low"]:
                should_boost = True

            if should_boost:
                boost = rule.get("confidence_boost", 0)
                boost_ids = set(rule.get("boost_techniques", []))
                for t in unique_techniques:
                    if t["technique_id"] in boost_ids:
                        t["base_confidence"] = min(t.get("base_confidence", 0) + boost, 1.0)

        # 6. 构建 ThreatTechnique 列表
        threat_techniques: list[ThreatTechnique] = []
        for t in unique_techniques:
            threat_techniques.append(ThreatTechnique(
                technique_id=t["technique_id"],
                technique_name=t["technique_name"],
                tactic_id=t["tactic_id"],
                tactic_name=t["tactic_name"],
                confidence=round(t.get("base_confidence", 0.5), 2),
                description=t.get("description", ""),
                intel_refs=t.get("intel_refs", []),
            ))

        # 排序：按置信度从高到低
        threat_techniques.sort(key=lambda x: x.confidence, reverse=True)

        # 7. 去重 tactics 列表（保留首次出现顺序）
        tactics_seen: set[str] = set()
        tactics: list[str] = []
        for tt in threat_techniques:
            if tt.tactic_name not in tactics_seen:
                tactics_seen.add(tt.tactic_name)
                tactics.append(tt.tactic_name)

        # 8. 总体增强置信度 = 前 3 项加权平均
        top_scores = [tt.confidence for tt in threat_techniques[:3]]
        enrichment_confidence = round(sum(top_scores) / len(top_scores), 2) if top_scores else 0.0

        return ThreatContext(
            techniques=threat_techniques,
            tactics=tactics,
            enrichment_confidence=enrichment_confidence,
            enrichment_source="local_mitre_v1",
        )
