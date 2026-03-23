"""
特征服务。
将 Flow 提取为特征。
"""

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class FeaturesService:
    """
    从流记录中提取特征的服务。

    遵循 DOC B B4.3 规范。
    最小特征集约 20-40 个特征。
    """

    # ── 集中管理的特征名列表，便于 DetectionService 直接引用 ──
    FEATURE_NAMES: list[str] = [
        # 基础统计
        "total_packets", "total_bytes", "bytes_per_packet", "flow_duration_ms",
        # 正反向比例
        "fwd_ratio_packets", "fwd_ratio_bytes",
        # 包间隔统计
        "iat_mean_ms", "iat_std_ms",
        # TCP 标志位计数
        "syn_count", "ack_count", "fin_count", "rst_count", "psh_count",
        # 端口与协议
        "dst_port_bucket", "is_tcp", "is_udp", "is_icmp",
        # 包大小统计
        "avg_pkt_size_fwd", "avg_pkt_size_bwd",
        # 标志位比例
        "syn_ratio", "rst_ratio",
        # 【新增】双向响应性
        "bwd_to_fwd_packets_ratio", "bwd_to_fwd_bytes_ratio", "has_bwd_traffic",
        # 【新增】会话完成度
        "has_syn", "has_ack", "has_fin_or_rst", "handshake_completeness",
        # 【新增】TCP 握手/结束特征
        "syn_ack_ratio", "fin_rst_ratio", "termination_type",
        # 【新增】短会话与突发特征
        "is_short_flow", "packets_per_second", "bytes_per_second", "single_packet_flow",
        # 【新增】上下行不对称特征
        "bytes_asymmetry", "packets_asymmetry", "payload_size_ratio_fwd_bwd",
    ]
    def __init__(self):
        pass

    # ── 安全除法，处理 None / 零除 / 类型异常 ──
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
        """
        从单条流记录中提取全部特征。

        Args:
            flow: 包含包/字节计数和元数据的流字典
        Returns:
            提取的特征字典
        """
        features: dict[str, Any] = {}
        sd = self._safe_div

        # ── 原始数据统一提取（防 None）──
        packets_fwd: int = flow.get("packets_fwd", 0) or 0
        packets_bwd: int = flow.get("packets_bwd", 0) or 0
        bytes_fwd: int = flow.get("bytes_fwd", 0) or 0
        bytes_bwd: int = flow.get("bytes_bwd", 0) or 0
        tcp_flags: dict = flow.get("_tcp_flags", {}) or {}
        dst_port: int = flow.get("dst_port", 0) or 0
        proto: str = flow.get("proto", "OTHER") or "OTHER"
        # ── 基础计数特征 ──
        total_packets = packets_fwd + packets_bwd
        total_bytes = bytes_fwd + bytes_bwd
        features["total_packets"] = total_packets
        features["total_bytes"] = total_bytes
        features["bytes_per_packet"] = sd(total_bytes, total_packets)

        # ── 流持续时长（兼容 datetime 与 float/epoch）──
        ts_start = flow.get("ts_start")
        ts_end = flow.get("ts_end")
        duration_ms = 0.0
        if ts_start and ts_end:
            from datetime import datetime
            if isinstance(ts_start, datetime) and isinstance(ts_end, datetime):
                duration_ms = (ts_end - ts_start).total_seconds() * 1000
            elif isinstance(ts_start, (int, float)) and isinstance(ts_end, (int, float)):
                duration_ms = (ts_end - ts_start) * 1000
        features["flow_duration_ms"] = max(0.0, round(duration_ms, 3))
        duration_s = features["flow_duration_ms"] / 1000.0  # 复用于速率计算

        # ── 正反向比例 ──
        features["fwd_ratio_packets"] = sd(packets_fwd, total_packets, 0.5)
        features["fwd_ratio_bytes"] = sd(bytes_fwd, total_bytes, 0.5)

        # ── 包间隔时间统计 ──
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

        # ── TCP 标志位计数 ──
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
        # ── 端口分桶 ──
        if dst_port < 1024:
            features["dst_port_bucket"] = "well_known"
        elif dst_port < 49152:
            features["dst_port_bucket"] = "registered"
        else:
            features["dst_port_bucket"] = "dynamic"

        # ── 协议标志 ──
        features["is_tcp"] = 1 if proto == "TCP" else 0
        features["is_udp"] = 1 if proto == "UDP" else 0
        features["is_icmp"] = 1 if proto == "ICMP" else 0

        # ── 正/反向平均包大小 ──
        avg_fwd = sd(bytes_fwd, packets_fwd)
        avg_bwd = sd(bytes_bwd, packets_bwd)
        features["avg_pkt_size_fwd"] = avg_fwd
        features["avg_pkt_size_bwd"] = avg_bwd

        # ── 标志位比例 ──
        features["syn_ratio"] = sd(syn_count, total_packets)
        features["rst_ratio"] = sd(rst_count, total_packets)

        # ================================================================
        #                    【新增特征 — 5 组】
        # ================================================================

        # ── A. 双向响应性 ──
        # 反向/正向包比：扫描流几乎无反向包，该值趋近 0
        features["bwd_to_fwd_packets_ratio"] = sd(packets_bwd, packets_fwd)
        # 反向/正向字节比：C2 信标呈异常字节比
        features["bwd_to_fwd_bytes_ratio"] = sd(bytes_bwd, bytes_fwd)
        # 是否存在反向流量（二值）：无应答流高度可疑
        features["has_bwd_traffic"] = 1 if packets_bwd > 0 else 0

        # ── B. 会话完成度 ──
        has_syn = 1 if syn_count > 0 else 0
        has_ack = 1 if ack_count > 0 else 0
        has_fin_or_rst = 1 if (fin_count > 0 or rst_count > 0) else 0
        features["has_syn"] = has_syn
        features["has_ack"] = has_ack
        features["has_fin_or_rst"] = has_fin_or_rst
        # 握手完成度 0-1：低值 = 扫描/探测特征
        features["handshake_completeness"] = round((has_syn + has_ack + has_fin_or_rst) / 3.0, 4)

        # ── C. TCP 握手/结束特征 ──
        # SYN/ACK 比：SYN Flood 时远大于 1
        features["syn_ack_ratio"] = sd(syn_count, ack_count)
        # FIN/(FIN+RST) 比：0=RST 终止(拒绝) 1=FIN 终止(正常) 0.5=默认
        features["fin_rst_ratio"] = sd(fin_count, fin_count + rst_count, 0.5)
        # 终止类型：0=无终止 1=仅FIN 2=仅RST 3=两者都有
        has_fin = 1 if fin_count > 0 else 0
        has_rst = 1 if rst_count > 0 else 0
        features["termination_type"] = has_fin + has_rst * 2

        # ── D. 短会话与突发特征 ──
        # 短流标记：端口扫描/探测通常 1-3 包
        features["is_short_flow"] = 1 if total_packets <= 3 else 0
        # 每秒包数：突发/DDoS 有极高 PPS
        features["packets_per_second"] = sd(total_packets, duration_s)
        # 每秒字节数：带宽洪泛检测
        features["bytes_per_second"] = sd(total_bytes, duration_s)
        # 单包流：大概率扫描或探测
        features["single_packet_flow"] = 1 if total_packets == 1 else 0

        # ── E. 上下行不对称特征 ──
        # 字节不对称度 [0,1]：1 = 完全单向（数据外泄/C2）
        features["bytes_asymmetry"] = sd(abs(bytes_fwd - bytes_bwd), bytes_fwd + bytes_bwd)
        # 包数不对称度 [0,1]
        features["packets_asymmetry"] = sd(abs(packets_fwd - packets_bwd), packets_fwd + packets_bwd)
        # 正/反向平均包大小比：隧道流量呈异常大小比
        features["payload_size_ratio_fwd_bwd"] = sd(avg_fwd, max(avg_bwd, 1.0))

        return features

    def extract_features_batch(self, flows: list[dict]) -> list[dict]:
        """
        批量提取特征。

        Args:
            flows: 流字典列表
        Returns:
            已填充 features 字段的流列表
        """
        for flow in flows:
            flow["features"] = self.extract_features(flow)
        return flows
