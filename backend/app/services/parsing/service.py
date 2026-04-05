"""
解析服务。
将 PCAP 聚合为 Flow。
"""

from datetime import datetime
from pathlib import Path

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now

logger = get_logger(__name__)


class ParsingService:
    """
用于解析 PCAP 文件并提取流记录的服务。

遵循 DOC B B4.2 规范。
"""

    def __init__(self):
        pass

    def parse_to_flows(
        self,
        pcap_path: Path,
        window_sec: int = 60,
    ) -> list[dict]:
        """
解析 PCAP 并将报文聚合为双向会话。

        参数：
            pcap_path: PCAP 文件路径
            window_sec: 会话聚合时间窗（秒）

        返回：
            可直接入库的 flow 字典列表

        说明：
            会话键为 (canon_ip1, canon_port1, canon_ip2, canon_port2, proto, bucket_start)
            其中 canon 为排序后的端点；输出中的 src/dst 对应发起方/响应方。
        """
        logger.info(f"正在解析 PCAP: {pcap_path}, 窗口={window_sec}s")
        
        flows = {}
        
        try:
            # 使用 dpkt 解析 PCAP
            import dpkt
            
            with open(pcap_path, 'rb') as f:
                try:
                    pcap = dpkt.pcap.Reader(f)
                except ValueError:
                    # 尝试 pcapng 格式
                    f.seek(0)
                    pcap = dpkt.pcapng.Reader(f)
                
                for timestamp, buf in pcap:
                    self._process_packet(timestamp, buf, window_sec, flows)
        
        except ImportError:
            logger.warning("dpkt not installed, using stub data")
            # 若未安装 dpkt，则返回空结果
            return []
        except Exception as e:
            logger.error(f"解析 PCAP 出错: {e}")
            raise
        
        # 将 flow 字典转换为列表
        flow_list = self._finalize_flows(flows)
        logger.info(f"从 PCAP 中提取了 {len(flow_list)} 条流")
        
        return flow_list

    def _process_packet(
        self,
        timestamp: float,
        buf: bytes,
        window_sec: int,
        flows: dict,
    ):
        """处理单个报文并更新流聚合状态。"""
        try:
            import dpkt
            
            eth = dpkt.ethernet.Ethernet(buf)
            
            # 仅处理 IP 报文
            if not isinstance(eth.data, dpkt.ip.IP):
                return
            
            ip = eth.data
            src_ip = self._ip_to_str(ip.src)  # type: ignore[attr-defined]
            dst_ip = self._ip_to_str(ip.dst)  # type: ignore[attr-defined]
            
            # 识别协议与端口
            proto = "OTHER"
            src_port = 0
            dst_port = 0
            tcp_flags = {}
            
            if isinstance(ip.data, dpkt.tcp.TCP):
                proto = "TCP"
                tcp = ip.data
                src_port = tcp.sport  # type: ignore[attr-defined]
                dst_port = tcp.dport  # type: ignore[attr-defined]
                tcp_flags = self._extract_tcp_flags(tcp)
            elif isinstance(ip.data, dpkt.udp.UDP):
                proto = "UDP"
                udp = ip.data
                src_port = udp.sport  # type: ignore[attr-defined]
                dst_port = udp.dport  # type: ignore[attr-defined]
            elif isinstance(ip.data, dpkt.icmp.ICMP):
                proto = "ICMP"
            
            # 规范化会话键：对端点排序，使 A->B 与 B->A 共享同一键
            endpoint_a = (src_ip, src_port)
            endpoint_b = (dst_ip, dst_port)
            if endpoint_a <= endpoint_b:
                canon = (src_ip, src_port, dst_ip, dst_port)
            else:
                canon = (dst_ip, dst_port, src_ip, src_port)

            bucket_start = int(timestamp) // window_sec * window_sec
            session_key = (*canon, proto, bucket_start)

            # 创建或更新双向会话
            if session_key not in flows:
                # 首包定义发起方（正向方向）
                flows[session_key] = {
                    "_initiator": (src_ip, src_port),
                    "src_ip": src_ip,
                    "src_port": src_port,
                    "dst_ip": dst_ip,
                    "dst_port": dst_port,
                    "proto": proto,
                    "bucket_start": bucket_start,
                    "ts_start": timestamp,
                    "ts_end": timestamp,
                    "packets_fwd": 0,
                    "packets_bwd": 0,
                    "bytes_fwd": 0,
                    "bytes_bwd": 0,
                    "tcp_flags": {"syn": 0, "ack": 0, "fin": 0, "rst": 0, "psh": 0},
                    "packet_timestamps": [],
                }

            flow = flows[session_key]
            pkt_len = len(buf)

            # 更新时间戳
            flow["ts_start"] = min(flow["ts_start"], timestamp)
            flow["ts_end"] = max(flow["ts_end"], timestamp)
            flow["packet_timestamps"].append(timestamp)

            # 方向判定：与发起方（首包发送者）一致即为正向
            is_forward = (src_ip, src_port) == flow["_initiator"]

            if is_forward:
                flow["packets_fwd"] += 1
                flow["bytes_fwd"] += pkt_len
            else:
                flow["packets_bwd"] += 1
                flow["bytes_bwd"] += pkt_len

            # 更新 TCP 标志统计
            for flag, count in tcp_flags.items():
                flow["tcp_flags"][flag] = flow["tcp_flags"].get(flag, 0) + count
                
        except Exception as e:
            logger.debug(f"处理数据包出错: {e}")

    def _extract_tcp_flags(self, tcp) -> dict:
        """从报文中提取 TCP 标志位。"""
        flags = {}
        if tcp.flags & 0x02:  # SYN
            flags["syn"] = 1
        if tcp.flags & 0x10:  # ACK
            flags["ack"] = 1
        if tcp.flags & 0x01:  # FIN
            flags["fin"] = 1
        if tcp.flags & 0x04:  # RST
            flags["rst"] = 1
        if tcp.flags & 0x08:  # PSH
            flags["psh"] = 1
        return flags

    def _ip_to_str(self, ip_bytes: bytes) -> str:
        """将 IP 字节转换为字符串。"""
        if len(ip_bytes) == 4:
            return ".".join(str(b) for b in ip_bytes)
        elif len(ip_bytes) == 16:
            # IPv6 地址
            return ":".join(f"{ip_bytes[i]:02x}{ip_bytes[i+1]:02x}" for i in range(0, 16, 2))
        return "0.0.0.0"

    def _finalize_flows(self, flows: dict) -> list[dict]:
        """将流字典转换为流记录列表。"""
        result = []
        now = utc_now()
        
        for flow_key, flow in flows.items():
            # 生成 flow 记录
            record = {
                "id": generate_uuid(),
                "version": "1.1",
                "created_at": now,
                "ts_start": datetime.utcfromtimestamp(flow["ts_start"]),
                "ts_end": datetime.utcfromtimestamp(flow["ts_end"]),
                "src_ip": flow["src_ip"],
                "src_port": flow["src_port"],
                "dst_ip": flow["dst_ip"],
                "dst_port": flow["dst_port"],
                "proto": flow["proto"],
                "packets_fwd": flow["packets_fwd"],
                "packets_bwd": flow["packets_bwd"],
                "bytes_fwd": flow["bytes_fwd"],
                "bytes_bwd": flow["bytes_bwd"],
                "features": {},  # 由 features 服务后续填充
                "anomaly_score": None,
                "label": None,
                "_tcp_flags": flow["tcp_flags"],
                "_packet_timestamps": flow["packet_timestamps"],
            }
            result.append(record)
        
        return result
