from datetime import datetime, timezone
from pathlib import Path

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now

logger = get_logger(__name__)

_PROTO_MAP = {6: "TCP", 17: "UDP", 1: "ICMP"}


def _nfstream_available() -> bool:
    try:
        from nfstream import NFStreamer  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


_USE_NFSTREAM = _nfstream_available()


class ParsingService:
    def parse_to_flows(
        self,
        pcap_path: Path,
        *,
        idle_timeout: int = 120,
        active_timeout: int = 1800,
        window_sec: int | None = None,  # dpkt-fallback only
    ) -> list[dict]:
        if _USE_NFSTREAM:
            return self._parse_with_nfstream(pcap_path, idle_timeout, active_timeout)

        ws = window_sec if window_sec is not None else 60
        logger.info("NFStream 不可用，使用 dpkt fallback (window_sec=%d)", ws)
        return self._parse_with_dpkt(pcap_path, ws)

    def _parse_with_nfstream(
        self, pcap_path: Path, idle_timeout: int, active_timeout: int,
    ) -> list[dict]:
        from nfstream import NFStreamer

        logger.info(
            "NFStream 解析: %s (idle=%ds, active=%ds)",
            pcap_path, idle_timeout, active_timeout,
        )

        streamer = NFStreamer(
            source=str(pcap_path),
            idle_timeout=idle_timeout,
            active_timeout=active_timeout,
            statistical_analysis=True,
        )

        now = utc_now()
        flow_list = [self._nfstream_to_flow_dict(nf, now) for nf in streamer]
        logger.info("NFStream 提取了 %d 条流", len(flow_list))
        return flow_list

    def _nfstream_to_flow_dict(self, nf, now: datetime) -> dict:
        proto_str = _PROTO_MAP.get(nf.protocol, "OTHER")

        ts_start_epoch = nf.bidirectional_first_seen_ms / 1000.0
        ts_end_epoch = nf.bidirectional_last_seen_ms / 1000.0

        tcp_flags = {"syn": 0, "ack": 0, "fin": 0, "rst": 0, "psh": 0}
        if proto_str == "TCP":
            tcp_flags = {
                "syn": getattr(nf, "src2dst_syn_packets", 0) + getattr(nf, "dst2src_syn_packets", 0),
                "ack": getattr(nf, "src2dst_ack_packets", 0) + getattr(nf, "dst2src_ack_packets", 0),
                "fin": getattr(nf, "src2dst_fin_packets", 0) + getattr(nf, "dst2src_fin_packets", 0),
                "rst": getattr(nf, "src2dst_rst_packets", 0) + getattr(nf, "dst2src_rst_packets", 0),
                "psh": getattr(nf, "src2dst_psh_packets", 0) + getattr(nf, "dst2src_psh_packets", 0),
            }

        iat_stats = {
            "mean_ms": getattr(nf, "bidirectional_mean_piat_ms", 0.0) or 0.0,
            "std_ms": getattr(nf, "bidirectional_stddev_piat_ms", 0.0) or 0.0,
        }

        return {
            "id": generate_uuid(),
            "version": "1.1",
            "created_at": now,
            "ts_start": datetime.fromtimestamp(ts_start_epoch, tz=timezone.utc),
            "ts_end": datetime.fromtimestamp(ts_end_epoch, tz=timezone.utc),
            "src_ip": nf.src_ip,
            "src_port": nf.src_port,
            "dst_ip": nf.dst_ip,
            "dst_port": nf.dst_port,
            "proto": proto_str,
            "packets_fwd": nf.src2dst_packets,
            "packets_bwd": nf.dst2src_packets,
            "bytes_fwd": nf.src2dst_bytes,
            "bytes_bwd": nf.dst2src_bytes,
            "features": {},
            "anomaly_score": None,
            "label": None,
            "_tcp_flags": tcp_flags,
            "_packet_timestamps": [],
            "_iat_stats": iat_stats,
        }

    def _parse_with_dpkt(self, pcap_path: Path, window_sec: int) -> list[dict]:
        logger.info("dpkt 解析: %s, 窗口=%ds", pcap_path, window_sec)

        flows: dict = {}

        try:
            import dpkt

            with open(pcap_path, "rb") as f:
                try:
                    pcap = dpkt.pcap.Reader(f)
                except ValueError:
                    f.seek(0)
                    pcap = dpkt.pcapng.Reader(f)

                for timestamp, buf in pcap:
                    self._process_packet(timestamp, buf, window_sec, flows)

        except ImportError:
            logger.warning("dpkt not installed, returning empty result")
            return []
        except Exception as e:
            logger.error("解析 PCAP 出错: %s", e)
            raise

        flow_list = self._finalize_flows(flows)
        logger.info("dpkt 提取了 %d 条流", len(flow_list))
        return flow_list

    def _process_packet(
        self,
        timestamp: float,
        buf: bytes,
        window_sec: int,
        flows: dict,
    ):
        try:
            import dpkt

            eth = dpkt.ethernet.Ethernet(buf)

            if not isinstance(eth.data, dpkt.ip.IP):
                return

            ip = eth.data
            src_ip = self._ip_to_str(ip.src)
            dst_ip = self._ip_to_str(ip.dst)

            proto = "OTHER"
            src_port = 0
            dst_port = 0
            tcp_flags = {}

            if isinstance(ip.data, dpkt.tcp.TCP):
                proto = "TCP"
                tcp = ip.data
                src_port = tcp.sport
                dst_port = tcp.dport
                tcp_flags = self._extract_tcp_flags(tcp)
            elif isinstance(ip.data, dpkt.udp.UDP):
                proto = "UDP"
                udp = ip.data
                src_port = udp.sport
                dst_port = udp.dport
            elif isinstance(ip.data, dpkt.icmp.ICMP):
                proto = "ICMP"

            endpoint_a = (src_ip, src_port)
            endpoint_b = (dst_ip, dst_port)
            if endpoint_a <= endpoint_b:
                canon = (src_ip, src_port, dst_ip, dst_port)
            else:
                canon = (dst_ip, dst_port, src_ip, src_port)

            bucket_start = int(timestamp) // window_sec * window_sec
            session_key = (*canon, proto, bucket_start)

            if session_key not in flows:
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

            flow["ts_start"] = min(flow["ts_start"], timestamp)
            flow["ts_end"] = max(flow["ts_end"], timestamp)
            flow["packet_timestamps"].append(timestamp)

            is_forward = (src_ip, src_port) == flow["_initiator"]

            if is_forward:
                flow["packets_fwd"] += 1
                flow["bytes_fwd"] += pkt_len
            else:
                flow["packets_bwd"] += 1
                flow["bytes_bwd"] += pkt_len

            for flag, count in tcp_flags.items():
                flow["tcp_flags"][flag] = flow["tcp_flags"].get(flag, 0) + count

        except Exception as e:
            logger.debug("处理数据包出错: %s", e)

    def _extract_tcp_flags(self, tcp) -> dict:
        flags = {}
        if tcp.flags & 0x02:
            flags["syn"] = 1
        if tcp.flags & 0x10:
            flags["ack"] = 1
        if tcp.flags & 0x01:
            flags["fin"] = 1
        if tcp.flags & 0x04:
            flags["rst"] = 1
        if tcp.flags & 0x08:
            flags["psh"] = 1
        return flags

    def _ip_to_str(self, ip_bytes: bytes) -> str:
        if len(ip_bytes) == 4:
            return ".".join(str(b) for b in ip_bytes)
        if len(ip_bytes) == 16:
            return ":".join(f"{ip_bytes[i]:02x}{ip_bytes[i+1]:02x}" for i in range(0, 16, 2))
        return "0.0.0.0"

    def _finalize_flows(self, flows: dict) -> list[dict]:
        result = []
        now = utc_now()

        for flow in flows.values():
            result.append({
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
                "features": {},
                "anomaly_score": None,
                "label": None,
                "_tcp_flags": flow["tcp_flags"],
                "_packet_timestamps": flow["packet_timestamps"],
            })

        return result
