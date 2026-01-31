"""
Features service.
Flow -> Features extraction.
"""

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class FeaturesService:
    """
    Service for extracting features from flows.
    
    Follows DOC B B4.3 specification.
    Minimum feature set (20-40 features).
    """

    def __init__(self):
        pass

    def extract_features(self, flow: dict) -> dict[str, Any]:
        """
        Extract features from a flow record.
        
        Args:
            flow: Flow dictionary with packet/byte counts and metadata
            
        Returns:
            Dictionary of extracted features
        """
        features = {}
        
        # Basic counts
        features["total_packets"] = flow.get("packets_fwd", 0) + flow.get("packets_bwd", 0)
        features["total_bytes"] = flow.get("bytes_fwd", 0) + flow.get("bytes_bwd", 0)
        
        # Bytes per packet
        if features["total_packets"] > 0:
            features["bytes_per_packet"] = features["total_bytes"] / features["total_packets"]
        else:
            features["bytes_per_packet"] = 0
        
        # Flow duration
        ts_start = flow.get("ts_start")
        ts_end = flow.get("ts_end")
        if ts_start and ts_end:
            duration = (ts_end - ts_start).total_seconds() * 1000 if hasattr(ts_start, 'total_seconds') else 0
            features["flow_duration_ms"] = max(0, duration)
        else:
            features["flow_duration_ms"] = 0
        
        # Forward/backward ratios
        total_packets = features["total_packets"]
        total_bytes = features["total_bytes"]
        
        if total_packets > 0:
            features["fwd_ratio_packets"] = flow.get("packets_fwd", 0) / total_packets
        else:
            features["fwd_ratio_packets"] = 0.5
            
        if total_bytes > 0:
            features["fwd_ratio_bytes"] = flow.get("bytes_fwd", 0) / total_bytes
        else:
            features["fwd_ratio_bytes"] = 0.5
        
        # Inter-arrival time statistics
        timestamps = flow.get("_packet_timestamps", [])
        if len(timestamps) > 1:
            iats = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            features["iat_mean_ms"] = sum(iats) / len(iats) * 1000
            
            # Standard deviation
            if len(iats) > 1:
                mean = features["iat_mean_ms"] / 1000
                variance = sum((x - mean) ** 2 for x in iats) / len(iats)
                features["iat_std_ms"] = (variance ** 0.5) * 1000
            else:
                features["iat_std_ms"] = 0
        else:
            features["iat_mean_ms"] = 0
            features["iat_std_ms"] = 0
        
        # TCP flags (if available)
        tcp_flags = flow.get("_tcp_flags", {})
        features["syn_count"] = tcp_flags.get("syn", 0)
        features["ack_count"] = tcp_flags.get("ack", 0)
        features["fin_count"] = tcp_flags.get("fin", 0)
        features["rst_count"] = tcp_flags.get("rst", 0)
        features["psh_count"] = tcp_flags.get("psh", 0)
        
        # Port bucket
        dst_port = flow.get("dst_port", 0)
        if dst_port < 1024:
            features["dst_port_bucket"] = "well_known"  # 0-1023
        elif dst_port < 49152:
            features["dst_port_bucket"] = "registered"  # 1024-49151
        else:
            features["dst_port_bucket"] = "dynamic"  # 49152+
        
        # Protocol-based features
        proto = flow.get("proto", "OTHER")
        features["is_tcp"] = 1 if proto == "TCP" else 0
        features["is_udp"] = 1 if proto == "UDP" else 0
        features["is_icmp"] = 1 if proto == "ICMP" else 0
        
        # Packet size statistics (forward)
        packets_fwd = flow.get("packets_fwd", 0)
        bytes_fwd = flow.get("bytes_fwd", 0)
        if packets_fwd > 0:
            features["avg_pkt_size_fwd"] = bytes_fwd / packets_fwd
        else:
            features["avg_pkt_size_fwd"] = 0
        
        # Packet size statistics (backward)
        packets_bwd = flow.get("packets_bwd", 0)
        bytes_bwd = flow.get("bytes_bwd", 0)
        if packets_bwd > 0:
            features["avg_pkt_size_bwd"] = bytes_bwd / packets_bwd
        else:
            features["avg_pkt_size_bwd"] = 0
        
        # SYN to packet ratio (potential scan indicator)
        if total_packets > 0:
            features["syn_ratio"] = features["syn_count"] / total_packets
        else:
            features["syn_ratio"] = 0
        
        # RST ratio (potential rejection indicator)
        if total_packets > 0:
            features["rst_ratio"] = features["rst_count"] / total_packets
        else:
            features["rst_ratio"] = 0
        
        return features

    def extract_features_batch(self, flows: list[dict]) -> list[dict]:
        """
        Extract features for a batch of flows.
        
        Args:
            flows: List of flow dictionaries
            
        Returns:
            List of flows with features populated
        """
        for flow in flows:
            flow["features"] = self.extract_features(flow)
        return flows
