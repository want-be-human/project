"""
Unit tests for ThreatEnrichmentService.
Validates MITRE ATT&CK mapping, port/protocol enrichment,
feature-based confidence boosting, and graceful degradation.
"""

from unittest.mock import patch

import pytest

from app.services.threat_enrichment.service import (
    ThreatEnrichmentService,
)


@pytest.fixture
def service():
    return ThreatEnrichmentService()


# ── Alert-type base mapping tests ────────────────────────────────────────


class TestAlertTypeMapping:
    def test_enrich_scan_alert(self, service):
        ctx = service.enrich(alert_type="scan", protocol="tcp", port=80)
        assert ctx is not None
        ids = {t.technique_id for t in ctx.techniques}
        assert "T1595" in ids
        assert "T1046" in ids
        assert "Reconnaissance" in ctx.tactics
        assert ctx.enrichment_confidence > 0

    def test_enrich_bruteforce_alert(self, service):
        ctx = service.enrich(alert_type="bruteforce", protocol="tcp", port=22)
        assert ctx is not None
        ids = {t.technique_id for t in ctx.techniques}
        assert "T1110" in ids
        assert "Credential Access" in ctx.tactics

    def test_enrich_dos_alert(self, service):
        ctx = service.enrich(alert_type="dos", protocol="tcp", port=443)
        assert ctx is not None
        ids = {t.technique_id for t in ctx.techniques}
        assert "T1498" in ids
        assert "Impact" in ctx.tactics

    def test_enrich_exfil_alert(self, service):
        ctx = service.enrich(alert_type="exfil", protocol="tcp", port=443)
        assert ctx is not None
        ids = {t.technique_id for t in ctx.techniques}
        assert "T1041" in ids
        assert "Exfiltration" in ctx.tactics

    def test_enrich_anomaly_alert(self, service):
        ctx = service.enrich(alert_type="anomaly", protocol="tcp", port=12345)
        assert ctx is not None
        assert len(ctx.techniques) > 0
        assert ctx.enrichment_source == "local_mitre_v1"

    def test_enrich_unknown_type_returns_fallback(self, service):
        ctx = service.enrich(alert_type="unknown", protocol="tcp", port=9999)
        # 'unknown' has a fallback entry in the mapping
        assert ctx is not None
        assert len(ctx.techniques) >= 1


# ── Port / protocol supplementary rules ──────────────────────────────────


class TestPortProtocolRules:
    def test_ssh_port_adds_lateral_movement(self, service):
        ctx = service.enrich(alert_type="bruteforce", protocol="tcp", port=22)
        assert ctx is not None
        ids = {t.technique_id for t in ctx.techniques}
        assert "T1021.004" in ids  # SSH remote service
        assert "Lateral Movement" in ctx.tactics

    def test_rdp_port_adds_technique(self, service):
        ctx = service.enrich(alert_type="bruteforce", protocol="tcp", port=3389)
        assert ctx is not None
        ids = {t.technique_id for t in ctx.techniques}
        assert "T1021.001" in ids  # RDP

    def test_dns_port_adds_c2(self, service):
        ctx = service.enrich(alert_type="anomaly", protocol="udp", port=53)
        assert ctx is not None
        ids = {t.technique_id for t in ctx.techniques}
        assert "T1071.004" in ids  # DNS C2

    def test_icmp_protocol_adds_technique(self, service):
        ctx = service.enrich(alert_type="scan", protocol="icmp", port=0)
        assert ctx is not None
        ids = {t.technique_id for t in ctx.techniques}
        assert "T1095" in ids  # Non-Application Layer Protocol


# ── Feature-based confidence boosting ────────────────────────────────────


class TestFeatureBoost:
    def test_high_syn_ratio_boosts_scan_confidence(self, service):
        features = [{"name": "syn_ratio", "value": 0.9, "direction": "high"}]
        ctx_boosted = service.enrich(
            alert_type="scan", protocol="tcp", port=80, top_features=features
        )
        ctx_base = service.enrich(
            alert_type="scan", protocol="tcp", port=80, top_features=[]
        )
        assert ctx_boosted is not None and ctx_base is not None
        # Find T1595 in both
        boosted_t = next(t for t in ctx_boosted.techniques if t.technique_id == "T1595")
        base_t = next(t for t in ctx_base.techniques if t.technique_id == "T1595")
        assert boosted_t.confidence > base_t.confidence

    def test_high_total_bytes_boosts_exfil_confidence(self, service):
        features = [{"name": "total_bytes", "value": 5_000_000, "direction": "high"}]
        ctx = service.enrich(
            alert_type="exfil", protocol="tcp", port=443, top_features=features
        )
        assert ctx is not None
        t1041 = next(t for t in ctx.techniques if t.technique_id == "T1041")
        assert t1041.confidence >= 0.80  # base 0.80 + boost


# ── Graceful degradation ─────────────────────────────────────────────────


class TestDegradation:
    def test_corrupted_mapping_returns_none(self, service):
        """Simulates a broken knowledge file → enrich should return None."""
        with patch(
            "app.services.threat_enrichment.service._get_mitre_mapping",
            side_effect=Exception("corrupted"),
        ):
            result = service.enrich(alert_type="scan", protocol="tcp", port=80)
            assert result is None

    def test_missing_features_does_not_crash(self, service):
        """top_features=None should work fine."""
        ctx = service.enrich(
            alert_type="scan", protocol="tcp", port=80,
            top_features=None, evidence_keywords=None,
        )
        assert ctx is not None

    def test_empty_string_protocol(self, service):
        ctx = service.enrich(alert_type="anomaly", protocol="", port=0)
        assert ctx is not None


# ── Enrichment output structure ──────────────────────────────────────────


class TestOutputStructure:
    def test_techniques_sorted_by_confidence(self, service):
        ctx = service.enrich(alert_type="scan", protocol="tcp", port=80)
        assert ctx is not None
        for i in range(len(ctx.techniques) - 1):
            assert ctx.techniques[i].confidence >= ctx.techniques[i + 1].confidence

    def test_tactics_deduplicated(self, service):
        ctx = service.enrich(alert_type="scan", protocol="icmp", port=0)
        assert ctx is not None
        assert len(ctx.tactics) == len(set(ctx.tactics))

    def test_intel_refs_are_urls(self, service):
        ctx = service.enrich(alert_type="bruteforce", protocol="tcp", port=22)
        assert ctx is not None
        for t in ctx.techniques:
            for ref in t.intel_refs:
                assert ref.startswith("https://attack.mitre.org/")

    def test_enrichment_confidence_range(self, service):
        ctx = service.enrich(alert_type="dos", protocol="tcp", port=80)
        assert ctx is not None
        assert 0.0 <= ctx.enrichment_confidence <= 1.0


# ── Bilingual fields ──────────────────────────────────────────────────────


class TestBilingualFields:
    def test_scan_techniques_have_zh_fields(self, service):
        ctx = service.enrich(alert_type="scan", protocol="tcp", port=80)
        assert ctx is not None
        for t in ctx.techniques:
            assert t.technique_name_zh is not None, f"{t.technique_id} missing technique_name_zh"
            assert t.tactic_name_zh is not None, f"{t.technique_id} missing tactic_name_zh"
            assert t.description_zh is not None, f"{t.technique_id} missing description_zh"

    def test_bruteforce_techniques_have_zh_fields(self, service):
        ctx = service.enrich(alert_type="bruteforce", protocol="tcp", port=22)
        assert ctx is not None
        for t in ctx.techniques:
            assert t.technique_name_zh is not None, f"{t.technique_id} missing technique_name_zh"

    def test_dos_techniques_have_zh_fields(self, service):
        ctx = service.enrich(alert_type="dos", protocol="tcp", port=443)
        assert ctx is not None
        for t in ctx.techniques:
            assert t.technique_name_zh is not None, f"{t.technique_id} missing technique_name_zh"

    def test_tactics_zh_populated(self, service):
        ctx = service.enrich(alert_type="bruteforce", protocol="tcp", port=22)
        assert ctx is not None
        assert ctx.tactics_zh is not None
        assert len(ctx.tactics_zh) == len(ctx.tactics)

    def test_tactics_zh_deduplicated(self, service):
        ctx = service.enrich(alert_type="scan", protocol="icmp", port=0)
        assert ctx is not None
        if ctx.tactics_zh:
            assert len(ctx.tactics_zh) == len(set(ctx.tactics_zh))

    def test_zh_fields_optional_backward_compat(self, service):
        """If a technique entry lacks _zh fields, they should be None, not crash."""
        from app.schemas.agent import ThreatTechnique
        t = ThreatTechnique(
            technique_id="T9999", technique_name="Test",
            tactic_id="TA0000", tactic_name="Test Tactic",
            confidence=0.5,
        )
        assert t.technique_name_zh is None
        assert t.tactic_name_zh is None
        assert t.description_zh is None
