from datetime import datetime
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class FeaturesService:
    FEATURE_NAMES: list[str] = [
        "total_packets", "total_bytes", "bytes_per_packet", "flow_duration_ms",
        "fwd_ratio_packets", "fwd_ratio_bytes",
        "iat_mean_ms", "iat_std_ms",
        "syn_count", "ack_count", "fin_count", "rst_count", "psh_count",
        "dst_port_bucket", "is_tcp", "is_udp", "is_icmp",
        "avg_pkt_size_fwd", "avg_pkt_size_bwd",
        "syn_ratio", "rst_ratio",
        "bwd_to_fwd_packets_ratio", "bwd_to_fwd_bytes_ratio", "has_bwd_traffic",
        "has_syn", "has_ack", "has_fin_or_rst", "handshake_completeness",
        "syn_ack_ratio", "fin_rst_ratio", "termination_type",
        "is_short_flow", "packets_per_second", "bytes_per_second", "single_packet_flow",
        "bytes_asymmetry", "packets_asymmetry", "payload_size_ratio_fwd_bwd",
    ]

    @staticmethod
    def _safe_div(numerator, denominator, default: float = 0.0) -> float:
        try:
            if numerator is None or denominator is None:
                return default
            if denominator == 0:
                return default
            return float(numerator) / float(denominator)
        except (TypeError, ValueError):
            return default

    def extract_features(self, flow: dict) -> dict[str, Any]:
        features: dict[str, Any] = {}
        sd = self._safe_div

        packets_fwd: int = flow.get("packets_fwd", 0) or 0
        packets_bwd: int = flow.get("packets_bwd", 0) or 0
        bytes_fwd: int = flow.get("bytes_fwd", 0) or 0
        bytes_bwd: int = flow.get("bytes_bwd", 0) or 0
        tcp_flags: dict = flow.get("_tcp_flags", {}) or {}
        dst_port: int = flow.get("dst_port", 0) or 0
        proto: str = flow.get("proto", "OTHER") or "OTHER"

        total_packets = packets_fwd + packets_bwd
        total_bytes = bytes_fwd + bytes_bwd
        features["total_packets"] = total_packets
        features["total_bytes"] = total_bytes
        features["bytes_per_packet"] = sd(total_bytes, total_packets)

        ts_start = flow.get("ts_start")
        ts_end = flow.get("ts_end")
        duration_ms = 0.0
        if ts_start and ts_end:
            if isinstance(ts_start, datetime) and isinstance(ts_end, datetime):
                duration_ms = (ts_end - ts_start).total_seconds() * 1000
            elif isinstance(ts_start, (int, float)) and isinstance(ts_end, (int, float)):
                duration_ms = (ts_end - ts_start) * 1000
        features["flow_duration_ms"] = max(0.0, round(duration_ms, 3))
        duration_s = features["flow_duration_ms"] / 1000.0

        features["fwd_ratio_packets"] = sd(packets_fwd, total_packets, 0.5)
        features["fwd_ratio_bytes"] = sd(bytes_fwd, total_bytes, 0.5)

        iat_stats = flow.get("_iat_stats")
        if iat_stats:
            features["iat_mean_ms"] = iat_stats.get("mean_ms", 0.0)
            features["iat_std_ms"] = iat_stats.get("std_ms", 0.0)
        else:
            timestamps = flow.get("_packet_timestamps", []) or []
            if len(timestamps) > 1:
                iats = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
                iat_mean_s = sum(iats) / len(iats)
                features["iat_mean_ms"] = iat_mean_s * 1000
                if len(iats) > 1:
                    variance = sum((x - iat_mean_s) ** 2 for x in iats) / len(iats)
                    features["iat_std_ms"] = (variance ** 0.5) * 1000
                else:
                    features["iat_std_ms"] = 0.0
            else:
                features["iat_mean_ms"] = 0.0
                features["iat_std_ms"] = 0.0

        syn_count = tcp_flags.get("syn", 0) or 0
        ack_count = tcp_flags.get("ack", 0) or 0
        fin_count = tcp_flags.get("fin", 0) or 0
        rst_count = tcp_flags.get("rst", 0) or 0
        psh_count = tcp_flags.get("psh", 0) or 0
        features["syn_count"] = syn_count
        features["ack_count"] = ack_count
        features["fin_count"] = fin_count
        features["rst_count"] = rst_count
        features["psh_count"] = psh_count

        if dst_port < 1024:
            features["dst_port_bucket"] = "well_known"
        elif dst_port < 49152:
            features["dst_port_bucket"] = "registered"
        else:
            features["dst_port_bucket"] = "dynamic"

        features["is_tcp"] = 1 if proto == "TCP" else 0
        features["is_udp"] = 1 if proto == "UDP" else 0
        features["is_icmp"] = 1 if proto == "ICMP" else 0

        avg_fwd = sd(bytes_fwd, packets_fwd)
        avg_bwd = sd(bytes_bwd, packets_bwd)
        features["avg_pkt_size_fwd"] = avg_fwd
        features["avg_pkt_size_bwd"] = avg_bwd

        features["syn_ratio"] = sd(syn_count, total_packets)
        features["rst_ratio"] = sd(rst_count, total_packets)

        features["bwd_to_fwd_packets_ratio"] = sd(packets_bwd, packets_fwd)
        features["bwd_to_fwd_bytes_ratio"] = sd(bytes_bwd, bytes_fwd)
        features["has_bwd_traffic"] = 1 if packets_bwd > 0 else 0

        has_syn = 1 if syn_count > 0 else 0
        has_ack = 1 if ack_count > 0 else 0
        has_fin_or_rst = 1 if (fin_count > 0 or rst_count > 0) else 0
        features["has_syn"] = has_syn
        features["has_ack"] = has_ack
        features["has_fin_or_rst"] = has_fin_or_rst
        features["handshake_completeness"] = round((has_syn + has_ack + has_fin_or_rst) / 3.0, 4)

        features["syn_ack_ratio"] = sd(syn_count, ack_count)
        features["fin_rst_ratio"] = sd(fin_count, fin_count + rst_count, 0.5)
        has_fin = 1 if fin_count > 0 else 0
        has_rst = 1 if rst_count > 0 else 0
        features["termination_type"] = has_fin + has_rst * 2

        features["is_short_flow"] = 1 if total_packets <= 3 else 0
        features["packets_per_second"] = sd(total_packets, duration_s)
        features["bytes_per_second"] = sd(total_bytes, duration_s)
        features["single_packet_flow"] = 1 if total_packets == 1 else 0

        features["bytes_asymmetry"] = sd(abs(bytes_fwd - bytes_bwd), bytes_fwd + bytes_bwd)
        features["packets_asymmetry"] = sd(abs(packets_fwd - packets_bwd), packets_fwd + packets_bwd)
        features["payload_size_ratio_fwd_bwd"] = sd(avg_fwd, max(avg_bwd, 1.0))

        return features

    def extract_features_batch(self, flows: list[dict]) -> list[dict]:
        for flow in flows:
            flow["features"] = self.extract_features(flow)
        return flows
