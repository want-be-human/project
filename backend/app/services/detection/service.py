"""
Detection service.
Baseline anomaly detection using IsolationForest.
"""

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


class DetectionService:
    """
    Service for anomaly detection.
    
    Follows DOC B B4.4 specification.
    Uses IsolationForest for baseline detection.
    """

    def __init__(self, model_params: dict | None = None):
        self.model_params = model_params or {}
        self.model = None
        
        # Features to use for detection
        self.feature_names = [
            "total_packets",
            "total_bytes",
            "bytes_per_packet",
            "flow_duration_ms",
            "fwd_ratio_packets",
            "fwd_ratio_bytes",
            "iat_mean_ms",
            "iat_std_ms",
            "syn_count",
            "ack_count",
            "fin_count",
            "rst_count",
            "syn_ratio",
            "rst_ratio",
            "avg_pkt_size_fwd",
            "avg_pkt_size_bwd",
            "is_tcp",
            "is_udp",
        ]

    def score_flows(self, flows: list[dict]) -> list[dict]:
        """
        Calculate anomaly scores for flows.
        
        Args:
            flows: List of flow dictionaries with features
            
        Returns:
            Same flows with anomaly_score populated
        """
        if not flows:
            return flows
        
        try:
            from sklearn.ensemble import IsolationForest
            
            # Extract feature matrix
            X = self._flows_to_matrix(flows)
            
            if X.shape[0] < 2:
                # Not enough samples for meaningful detection
                for flow in flows:
                    flow["anomaly_score"] = 0.5
                return flows
            
            # Fit IsolationForest
            contamination = self.model_params.get("contamination", 0.1)
            n_estimators = self.model_params.get("n_estimators", 100)
            
            self.model = IsolationForest(
                contamination=contamination,
                n_estimators=n_estimators,
                random_state=42,
            )
            
            self.model.fit(X)
            
            # 获取原始分数（sklearn 中越负 = 越异常）
            raw_scores = self.model.score_samples(X)

            # 取反，使"越大 = 越异常"
            neg_scores = -raw_scores

            # 使用 5/95 分位数裁剪，防止单个极端离群点压缩整体分布
            p5, p95 = np.percentile(neg_scores, [5, 95])
            clipped = np.clip(neg_scores, p5, p95)

            if p95 > p5:
                normalized = (clipped - p5) / (p95 - p5)
            else:
                # 所有分数相同时给默认值
                normalized = np.full_like(raw_scores, 0.5)

            # TODO: 后续接入持久化模型时，使用全局分位数/分数映射表替代批次内分位数归一化
            # 届时可在此处加载预训练的 scaler 或查分位数表，实现跨批次可比的分数

            # 将归一化分数赋值给每条流
            for i, flow in enumerate(flows):
                flow["anomaly_score"] = float(normalized[i])

            logger.info(
                f"异常检测完成: {len(flows)} 条流, "
                f"p5={p5:.4f}, p95={p95:.4f}, max={normalized.max():.3f}"
            )
            
        except ImportError:
            logger.warning("sklearn not installed, using random scores")
            for flow in flows:
                flow["anomaly_score"] = np.random.random() * 0.5  # Random 0-0.5
        except Exception as e:
            logger.error(f"Error in anomaly detection: {e}")
            for flow in flows:
                flow["anomaly_score"] = 0.5
        
        return flows

    def _flows_to_matrix(self, flows: list[dict]) -> np.ndarray:
        """Convert flows to feature matrix."""
        rows = []
        
        for flow in flows:
            features = flow.get("features", {})
            row = []
            
            for name in self.feature_names:
                value = features.get(name, 0)
                # Handle non-numeric values
                if isinstance(value, str):
                    value = hash(value) % 10  # Simple encoding
                row.append(float(value))
            
            rows.append(row)
        
        return np.array(rows)

    def get_top_anomalous_flows(
        self,
        flows: list[dict],
        threshold: float = 0.7,
        limit: int = 10,
    ) -> list[dict]:
        """
        Get top anomalous flows above threshold.
        
        Args:
            flows: List of scored flows
            threshold: Minimum anomaly score
            limit: Maximum number of flows to return
            
        Returns:
            List of anomalous flows sorted by score descending
        """
        anomalous = [f for f in flows if (f.get("anomaly_score") or 0) >= threshold]
        anomalous.sort(key=lambda x: x.get("anomaly_score", 0), reverse=True)
        return anomalous[:limit]
