"""
Unit tests for DetectionService (IsolationForest).
DOC B B6: detection — fixed input → score output range correct.
"""

import pytest

from app.services.detection.service import DetectionService
from app.services.features.service import FeaturesService


def _make_scored_flows(n: int = 30) -> list[dict]:
    """Generate n synthetic flows with features already populated."""
    feat_svc = FeaturesService()
    flows = []
    for i in range(n):
        flow = {
            "packets_fwd": 1 + i,
            "packets_bwd": max(0, i - 5),
            "bytes_fwd": 74 * (1 + i),
            "bytes_bwd": 40 * max(0, i - 5),
            "ts_start": None,
            "ts_end": None,
            "dst_port": 22 if i < 20 else 443,
            "proto": "TCP",
            "_tcp_flags": {
                "syn": 1 if i % 3 == 0 else 0,
                "ack": 1,
                "fin": 0,
                "rst": 0,
                "psh": 0,
            },
            "_packet_timestamps": [],
        }
        flow["features"] = feat_svc.extract_features(flow)
        flows.append(flow)
    return flows


class TestScoreFlows:
    """IsolationForest scoring tests."""

    def test_returns_same_length(self):
        svc = DetectionService()
        flows = _make_scored_flows(30)
        result = svc.score_flows(flows)
        assert len(result) == 30

    def test_scores_in_0_1(self):
        svc = DetectionService()
        flows = _make_scored_flows(50)
        result = svc.score_flows(flows)
        for f in result:
            assert 0.0 <= f["anomaly_score"] <= 1.0, f"score out of range: {f['anomaly_score']}"

    def test_two_samples_fallback(self):
        """With only 1 sample IsolationForest can't fit — fallback to 0.5."""
        svc = DetectionService()
        flows = _make_scored_flows(1)
        result = svc.score_flows(flows)
        assert result[0]["anomaly_score"] == pytest.approx(0.5)

    def test_empty_flows(self):
        svc = DetectionService()
        assert svc.score_flows([]) == []

    def test_custom_contamination(self):
        svc = DetectionService(model_params={"contamination": 0.2, "n_estimators": 50})
        flows = _make_scored_flows(40)
        result = svc.score_flows(flows)
        scores = [f["anomaly_score"] for f in result]
        assert max(scores) <= 1.0
        assert min(scores) >= 0.0

    def test_outlier_gets_higher_score(self):
        """An extreme outlier should generally score higher than a normal flow."""
        svc = DetectionService()
        flows = _make_scored_flows(30)
        # Inject one clear outlier
        feat_svc = FeaturesService()
        outlier = {
            "packets_fwd": 5000,
            "packets_bwd": 0,
            "bytes_fwd": 999_999,
            "bytes_bwd": 0,
            "ts_start": None,
            "ts_end": None,
            "dst_port": 31337,
            "proto": "TCP",
            "_tcp_flags": {"syn": 5000, "ack": 0, "fin": 0, "rst": 0, "psh": 0},
            "_packet_timestamps": [],
        }
        outlier["features"] = feat_svc.extract_features(outlier)
        flows.append(outlier)

        result = svc.score_flows(flows)
        outlier_score = result[-1]["anomaly_score"]
        normal_scores = [f["anomaly_score"] for f in result[:-1]]
        median_normal = sorted(normal_scores)[len(normal_scores) // 2]
        # Outlier should be above median of normals
        assert outlier_score > median_normal, (
            f"outlier={outlier_score:.3f} should > median_normal={median_normal:.3f}"
        )


class TestGetTopAnomalous:
    def test_filters_by_threshold(self):
        svc = DetectionService()
        flows = [
            {"anomaly_score": 0.9, "id": "a"},
            {"anomaly_score": 0.5, "id": "b"},
            {"anomaly_score": 0.8, "id": "c"},
            {"anomaly_score": 0.3, "id": "d"},
        ]
        top = svc.get_top_anomalous_flows(flows, threshold=0.7, limit=10)
        assert len(top) == 2
        assert top[0]["id"] == "a"
        assert top[1]["id"] == "c"

    def test_respects_limit(self):
        svc = DetectionService()
        flows = [{"anomaly_score": 0.9 - i * 0.01, "id": str(i)} for i in range(20)]
        top = svc.get_top_anomalous_flows(flows, threshold=0.0, limit=5)
        assert len(top) == 5
