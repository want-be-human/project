"""
Alerting service.
Flow -> Alert generation and aggregation.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now, datetime_to_iso

logger = get_logger(__name__)


class AlertingService:
    """
    Service for generating and aggregating alerts.
    
    Follows DOC B B4.5 specification.
    """

    def __init__(
        self,
        score_threshold: float = 0.7,
        window_sec: int = 60,
    ):
        self.score_threshold = score_threshold
        self.window_sec = window_sec
        
        # Severity mapping based on score
        self.severity_thresholds = {
            "critical": 0.95,
            "high": 0.85,
            "medium": 0.70,
            "low": 0.0,
        }

    def generate_alerts(
        self,
        flows: list[dict],
        pcap_id: str,
    ) -> list[dict]:
        """
        Generate alerts from scored flows.
        
        Args:
            flows: List of flows with anomaly_score
            pcap_id: ID of the source PCAP
            
        Returns:
            List of alert dictionaries
        """
        # Filter anomalous flows
        anomalous = [
            f for f in flows
            if (f.get("anomaly_score") or 0) >= self.score_threshold
        ]
        
        if not anomalous:
            logger.info("No anomalous flows found above threshold")
            return []
        
        logger.info(f"Found {len(anomalous)} anomalous flows")
        
        # Group by aggregation rule: same_src_ip + window
        groups = self._aggregate_flows(anomalous)
        
        # Generate alerts from groups
        alerts = []
        for group_key, group_flows in groups.items():
            alert = self._create_alert(group_key, group_flows, pcap_id)
            alerts.append(alert)
        
        logger.info(f"Generated {len(alerts)} alerts")
        return alerts

    def _aggregate_flows(self, flows: list[dict]) -> dict[str, list[dict]]:
        """
        Aggregate flows by src_ip + time window.
        
        Returns dict mapping group_key to list of flows.
        """
        groups = {}
        
        for flow in flows:
            src_ip = flow.get("src_ip", "unknown")
            ts_start = flow.get("ts_start")
            
            # Calculate time bucket
            if isinstance(ts_start, datetime):
                bucket = int(ts_start.timestamp()) // self.window_sec * self.window_sec
            else:
                bucket = 0
            
            group_key = f"{src_ip}@{bucket}"
            
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(flow)
        
        return groups

    def _create_alert(
        self,
        group_key: str,
        flows: list[dict],
        pcap_id: str,
    ) -> dict:
        """Create an alert from a group of flows."""
        now = utc_now()
        
        # Calculate time window
        ts_starts = [f.get("ts_start") for f in flows if f.get("ts_start")]
        ts_ends = [f.get("ts_end") for f in flows if f.get("ts_end")]
        
        window_start = min(ts_starts) if ts_starts else now
        window_end = max(ts_ends) if ts_ends else now
        
        # Get primary entities from most anomalous flow
        flows_sorted = sorted(flows, key=lambda x: x.get("anomaly_score", 0), reverse=True)
        primary_flow = flows_sorted[0]
        
        # Calculate severity from max score
        max_score = max(f.get("anomaly_score", 0) for f in flows)
        severity = self._score_to_severity(max_score)
        
        # Determine alert type based on patterns
        alert_type = self._determine_type(flows)
        
        # Build evidence
        flow_ids = [f.get("id") for f in flows if f.get("id")]
        top_flows = self._get_top_flows(flows_sorted[:5])
        top_features = self._get_top_features(flows)
        
        evidence = {
            "flow_ids": flow_ids,
            "top_flows": top_flows,
            "top_features": top_features,
            "pcap_ref": {"pcap_id": pcap_id, "offset_hint": None},
        }
        
        # Build aggregation
        aggregation = {
            "rule": f"same_src_ip + {self.window_sec}s_window",
            "group_key": group_key,
            "count_flows": len(flows),
        }
        
        alert = {
            "id": generate_uuid(),
            "version": "1.1",
            "created_at": now,
            "severity": severity,
            "status": "new",
            "type": alert_type,
            "time_window_start": window_start,
            "time_window_end": window_end,
            "primary_src_ip": primary_flow.get("src_ip", "0.0.0.0"),
            "primary_dst_ip": primary_flow.get("dst_ip", "0.0.0.0"),
            "primary_proto": primary_flow.get("proto", "TCP"),
            "primary_dst_port": primary_flow.get("dst_port", 0),
            "evidence": json.dumps(evidence),
            "aggregation": json.dumps(aggregation),
            "agent": json.dumps({
                "triage_summary": None,
                "investigation_id": None,
                "recommendation_id": None,
            }),
            "twin": json.dumps({
                "plan_id": None,
                "dry_run_id": None,
            }),
            "tags": json.dumps(["auto"]),
            "notes": "",
            "_flow_ids": flow_ids,  # For creating alert_flows associations
        }
        
        return alert

    def _score_to_severity(self, score: float) -> str:
        """Map anomaly score to severity level."""
        for severity, threshold in self.severity_thresholds.items():
            if score >= threshold:
                return severity
        return "low"

    def _determine_type(self, flows: list[dict]) -> str:
        """Determine alert type based on flow patterns."""
        # Count unique destinations
        dst_ips = set(f.get("dst_ip") for f in flows)
        dst_ports = set(f.get("dst_port") for f in flows)
        
        # High SYN count and many destinations -> scan
        total_syn = sum(f.get("features", {}).get("syn_count", 0) for f in flows)
        total_packets = sum(f.get("features", {}).get("total_packets", 0) for f in flows)
        
        if len(dst_ips) > 5 or len(dst_ports) > 10:
            return "scan"
        
        if total_packets > 100 and total_syn / max(total_packets, 1) > 0.5:
            return "scan"
        
        # Single destination, many connections -> bruteforce
        if len(dst_ips) == 1 and len(flows) > 5:
            dst_port = flows[0].get("dst_port", 0)
            if dst_port in [22, 23, 3389, 21]:  # SSH, Telnet, RDP, FTP
                return "bruteforce"
        
        # High volume to single target -> dos
        total_bytes = sum(f.get("features", {}).get("total_bytes", 0) for f in flows)
        if total_bytes > 1000000 and len(dst_ips) == 1:  # >1MB
            return "dos"
        
        # Default to anomaly
        return "anomaly"

    def _get_top_flows(self, flows: list[dict]) -> list[dict]:
        """Get top flow summaries for evidence."""
        result = []
        for flow in flows:
            summary = f"{flow.get('proto', 'TCP')}/{flow.get('dst_port', 0)}"
            if flow.get("features", {}).get("syn_count", 0) > 5:
                summary += " SYN burst"
            
            result.append({
                "flow_id": flow.get("id", ""),
                "anomaly_score": flow.get("anomaly_score", 0),
                "summary": summary,
            })
        return result

    def _get_top_features(self, flows: list[dict]) -> list[dict]:
        """Get top contributing features across flows."""
        # Aggregate features
        feature_values = {}
        
        for flow in flows:
            features = flow.get("features", {})
            for name, value in features.items():
                if isinstance(value, (int, float)):
                    if name not in feature_values:
                        feature_values[name] = []
                    feature_values[name].append(value)
        
        # Find features with highest variance or extreme values
        top_features = []
        
        # Check for high SYN count
        syn_counts = feature_values.get("syn_count", [])
        if syn_counts and max(syn_counts) > 10:
            top_features.append({
                "name": "syn_count",
                "value": int(max(syn_counts)),
                "direction": "high",
            })
        
        # Check for high packet rate
        total_packets = feature_values.get("total_packets", [])
        if total_packets and max(total_packets) > 100:
            top_features.append({
                "name": "total_packets",
                "value": int(max(total_packets)),
                "direction": "high",
            })
        
        # Check for RST ratio
        rst_ratios = feature_values.get("rst_ratio", [])
        if rst_ratios and max(rst_ratios) > 0.3:
            top_features.append({
                "name": "rst_ratio",
                "value": round(max(rst_ratios), 2),
                "direction": "high",
            })
        
        return top_features[:5]  # Limit to 5
