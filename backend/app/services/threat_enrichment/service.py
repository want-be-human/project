import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.schemas.agent import ThreatContext, ThreatTechnique

logger = get_logger(__name__)

_KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
_mitre_mapping: dict | None = None
_port_protocol_rules: dict | None = None


def _load_json(path: Path) -> dict:
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
    def enrich(
        self,
        alert_type: str,
        protocol: str,
        port: int,
        top_features: list[dict[str, Any]] | None = None,
        evidence_keywords: list[str] | None = None,
    ) -> ThreatContext | None:
        """None on enrichment failure (silent degradation)."""
        try:
            return self._do_enrich(
                alert_type=alert_type,
                protocol=protocol.lower() if protocol else "",
                port=port,
                top_features=top_features or [],
                evidence_keywords=evidence_keywords or [],
            )
        except Exception:
            logger.warning("威胁增强失败 - 静默降级", exc_info=True)
            return None

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

        type_entry = mapping.get(alert_type, mapping.get("unknown", {}))
        techniques_raw: list[dict] = list(type_entry.get("techniques", []))

        for rule in rules.get("port_rules", []):
            if port in rule["ports"] and protocol in rule.get("protocols", []):
                techniques_raw.extend(rule["techniques"])

        for rule in rules.get("protocol_rules", []):
            if protocol in rule.get("protocols", []):
                techniques_raw.extend(rule["techniques"])

        if not techniques_raw:
            return None

        seen: dict[str, dict] = {}
        for t in techniques_raw:
            tid = t["technique_id"]
            if tid not in seen or t.get("base_confidence", 0) > seen[tid].get("base_confidence", 0):
                seen[tid] = dict(t)
        unique_techniques = list(seen.values())

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

            if not should_boost:
                continue
            boost = rule.get("confidence_boost", 0)
            boost_ids = set(rule.get("boost_techniques", []))
            for t in unique_techniques:
                if t["technique_id"] in boost_ids:
                    t["base_confidence"] = min(t.get("base_confidence", 0) + boost, 1.0)

        threat_techniques: list[ThreatTechnique] = [
            ThreatTechnique(
                technique_id=t["technique_id"],
                technique_name=t["technique_name"],
                technique_name_zh=t.get("technique_name_zh"),
                tactic_id=t["tactic_id"],
                tactic_name=t["tactic_name"],
                tactic_name_zh=t.get("tactic_name_zh"),
                confidence=round(t.get("base_confidence", 0.5), 2),
                description=t.get("description", ""),
                description_zh=t.get("description_zh"),
                intel_refs=t.get("intel_refs", []),
            )
            for t in unique_techniques
        ]
        threat_techniques.sort(key=lambda x: x.confidence, reverse=True)

        tactics_seen: set[str] = set()
        tactics: list[str] = []
        tactics_zh_seen: set[str] = set()
        tactics_zh: list[str] = []
        for tt in threat_techniques:
            if tt.tactic_name not in tactics_seen:
                tactics_seen.add(tt.tactic_name)
                tactics.append(tt.tactic_name)
            if tt.tactic_name_zh and tt.tactic_name_zh not in tactics_zh_seen:
                tactics_zh_seen.add(tt.tactic_name_zh)
                tactics_zh.append(tt.tactic_name_zh)

        top_scores = [tt.confidence for tt in threat_techniques[:3]]
        enrichment_confidence = round(sum(top_scores) / len(top_scores), 2) if top_scores else 0.0

        return ThreatContext(
            techniques=threat_techniques,
            tactics=tactics,
            tactics_zh=tactics_zh or None,
            enrichment_confidence=enrichment_confidence,
            enrichment_source="local_mitre_v1",
        )
