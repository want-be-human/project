"""
Unit tests for FeaturesService.
DOC B B6: features — input flow → features dict (fixed assertions).
"""

import pytest
from datetime import datetime, timezone

from app.services.features.service import FeaturesService


@pytest.fixture
def svc():
    return FeaturesService()


# --------------- helper to build a flow dict ---------------

def _make_flow(
    *,
    packets_fwd: int = 10,
    packets_bwd: int = 5,
    bytes_fwd: int = 1000,
    bytes_bwd: int = 300,
    ts_start: datetime | None = None,
    ts_end: datetime | None = None,
    dst_port: int = 22,
    proto: str = "TCP",
    tcp_flags: dict | None = None,
    timestamps: list[float] | None = None,
) -> dict:
    ts_start = ts_start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ts_end = ts_end or datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
    return {
        "packets_fwd": packets_fwd,
        "packets_bwd": packets_bwd,
        "bytes_fwd": bytes_fwd,
        "bytes_bwd": bytes_bwd,
        "ts_start": ts_start,
        "ts_end": ts_end,
        "dst_port": dst_port,
        "proto": proto,
        "_tcp_flags": tcp_flags or {"syn": 2, "ack": 8, "fin": 1, "rst": 0, "psh": 3},
        "_packet_timestamps": timestamps or [],
    }


# --------------- tests ---------------

class TestExtractFeatures:
    """Test that extract_features returns correct feature dict."""

    def test_total_packets(self, svc: FeaturesService):
        flow = _make_flow(packets_fwd=10, packets_bwd=5)
        feats = svc.extract_features(flow)
        assert feats["total_packets"] == 15

    def test_total_bytes(self, svc: FeaturesService):
        flow = _make_flow(bytes_fwd=1000, bytes_bwd=300)
        feats = svc.extract_features(flow)
        assert feats["total_bytes"] == 1300

    def test_bytes_per_packet(self, svc: FeaturesService):
        flow = _make_flow(packets_fwd=10, packets_bwd=0, bytes_fwd=500, bytes_bwd=0)
        feats = svc.extract_features(flow)
        assert feats["bytes_per_packet"] == pytest.approx(50.0)

    def test_bytes_per_packet_zero_packets(self, svc: FeaturesService):
        flow = _make_flow(packets_fwd=0, packets_bwd=0, bytes_fwd=0, bytes_bwd=0)
        feats = svc.extract_features(flow)
        assert feats["bytes_per_packet"] == 0

    def test_flow_duration_ms_datetime(self, svc: FeaturesService):
        flow = _make_flow(
            ts_start=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            ts_end=datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc),
        )
        feats = svc.extract_features(flow)
        assert feats["flow_duration_ms"] == pytest.approx(30_000.0)

    def test_flow_duration_ms_zero_when_same(self, svc: FeaturesService):
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        feats = svc.extract_features(_make_flow(ts_start=ts, ts_end=ts))
        assert feats["flow_duration_ms"] == 0

    def test_fwd_ratio_packets(self, svc: FeaturesService):
        feats = svc.extract_features(_make_flow(packets_fwd=8, packets_bwd=2))
        assert feats["fwd_ratio_packets"] == pytest.approx(0.8)

    def test_fwd_ratio_bytes(self, svc: FeaturesService):
        feats = svc.extract_features(_make_flow(bytes_fwd=750, bytes_bwd=250))
        assert feats["fwd_ratio_bytes"] == pytest.approx(0.75)

    def test_tcp_flags(self, svc: FeaturesService):
        flags = {"syn": 5, "ack": 10, "fin": 0, "rst": 1, "psh": 2}
        feats = svc.extract_features(_make_flow(tcp_flags=flags))
        assert feats["syn_count"] == 5
        assert feats["ack_count"] == 10
        assert feats["rst_count"] == 1

    def test_syn_ratio(self, svc: FeaturesService):
        flags = {"syn": 6, "ack": 0, "fin": 0, "rst": 0, "psh": 0}
        feats = svc.extract_features(_make_flow(packets_fwd=6, packets_bwd=0, tcp_flags=flags))
        assert feats["syn_ratio"] == pytest.approx(1.0)

    def test_dst_port_bucket_well_known(self, svc: FeaturesService):
        feats = svc.extract_features(_make_flow(dst_port=80))
        assert feats["dst_port_bucket"] == "well_known"

    def test_dst_port_bucket_registered(self, svc: FeaturesService):
        feats = svc.extract_features(_make_flow(dst_port=8080))
        assert feats["dst_port_bucket"] == "registered"

    def test_dst_port_bucket_dynamic(self, svc: FeaturesService):
        feats = svc.extract_features(_make_flow(dst_port=50000))
        assert feats["dst_port_bucket"] == "dynamic"

    def test_proto_flags(self, svc: FeaturesService):
        feats_tcp = svc.extract_features(_make_flow(proto="TCP"))
        assert feats_tcp["is_tcp"] == 1
        assert feats_tcp["is_udp"] == 0
        feats_udp = svc.extract_features(_make_flow(proto="UDP"))
        assert feats_udp["is_udp"] == 1
        assert feats_udp["is_tcp"] == 0

    def test_iat_with_timestamps(self, svc: FeaturesService):
        ts = [0.0, 0.1, 0.3, 0.6]  # iats: 0.1, 0.2, 0.3 → mean 0.2s = 200ms
        feats = svc.extract_features(_make_flow(timestamps=ts))
        assert feats["iat_mean_ms"] == pytest.approx(200.0)
        assert feats["iat_std_ms"] > 0

    def test_minimum_feature_count(self, svc: FeaturesService):
        """DOC B B4.3: at least 5 features (Week3 DoD)."""
        feats = svc.extract_features(_make_flow())
        assert len(feats) >= 5


class TestExtractFeaturesBatch:
    def test_batch_populates_features_key(self, svc: FeaturesService):
        flows = [_make_flow(), _make_flow(packets_fwd=20)]
        result = svc.extract_features_batch(flows)
        for f in result:
            assert "features" in f
            assert isinstance(f["features"], dict)
            assert f["features"]["total_packets"] > 0
