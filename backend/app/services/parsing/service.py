"""
Parsing service.
PCAP -> Flow aggregation.
"""

from datetime import datetime
from pathlib import Path
from typing import BinaryIO
import struct

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now

logger = get_logger(__name__)


class ParsingService:
    """
    Service for parsing PCAP files and extracting flows.
    
    Follows DOC B B4.2 specification.
    """

    def __init__(self):
        pass

    def parse_to_flows(
        self,
        pcap_path: Path,
        window_sec: int = 60,
    ) -> list[dict]:
        """
        Parse PCAP file and aggregate packets into flows.
        
        Args:
            pcap_path: Path to the PCAP file
            window_sec: Time window for flow aggregation in seconds
            
        Returns:
            List of flow dictionaries ready for database insertion
            
        Note:
            Flow key: (src_ip, src_port, dst_ip, dst_port, proto, bucket_start)
        """
        logger.info(f"Parsing PCAP: {pcap_path}, window={window_sec}s")
        
        flows = {}
        
        try:
            # Use dpkt for PCAP parsing
            import dpkt
            
            with open(pcap_path, 'rb') as f:
                try:
                    pcap = dpkt.pcap.Reader(f)
                except ValueError:
                    # Try pcapng format
                    f.seek(0)
                    pcap = dpkt.pcapng.Reader(f)
                
                for timestamp, buf in pcap:
                    self._process_packet(timestamp, buf, window_sec, flows)
        
        except ImportError:
            logger.warning("dpkt not installed, using stub data")
            # Return empty if dpkt not available
            return []
        except Exception as e:
            logger.error(f"Error parsing PCAP: {e}")
            raise
        
        # Convert flow dict to list
        flow_list = self._finalize_flows(flows)
        logger.info(f"Extracted {len(flow_list)} flows from PCAP")
        
        return flow_list

    def _process_packet(
        self,
        timestamp: float,
        buf: bytes,
        window_sec: int,
        flows: dict,
    ):
        """Process a single packet and update flow aggregation."""
        try:
            import dpkt
            
            eth = dpkt.ethernet.Ethernet(buf)
            
            # Only process IP packets
            if not isinstance(eth.data, dpkt.ip.IP):
                return
            
            ip = eth.data
            src_ip = self._ip_to_str(ip.src)
            dst_ip = self._ip_to_str(ip.dst)
            
            # Determine protocol and ports
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
            
            # Calculate time bucket
            bucket_start = int(timestamp) // window_sec * window_sec
            
            # Create flow key
            flow_key = (src_ip, src_port, dst_ip, dst_port, proto, bucket_start)
            
            # Determine direction (forward = src < dst lexicographically)
            is_forward = (src_ip, src_port) <= (dst_ip, dst_port)
            
            # Update or create flow
            if flow_key not in flows:
                flows[flow_key] = {
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
            
            flow = flows[flow_key]
            pkt_len = len(buf)
            
            # Update timestamps
            flow["ts_start"] = min(flow["ts_start"], timestamp)
            flow["ts_end"] = max(flow["ts_end"], timestamp)
            flow["packet_timestamps"].append(timestamp)
            
            # Update packet/byte counts
            if is_forward:
                flow["packets_fwd"] += 1
                flow["bytes_fwd"] += pkt_len
            else:
                flow["packets_bwd"] += 1
                flow["bytes_bwd"] += pkt_len
            
            # Update TCP flags
            for flag, count in tcp_flags.items():
                flow["tcp_flags"][flag] = flow["tcp_flags"].get(flag, 0) + count
                
        except Exception as e:
            logger.debug(f"Error processing packet: {e}")

    def _extract_tcp_flags(self, tcp) -> dict:
        """Extract TCP flags from packet."""
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
        """Convert IP bytes to string."""
        if len(ip_bytes) == 4:
            return ".".join(str(b) for b in ip_bytes)
        elif len(ip_bytes) == 16:
            # IPv6
            return ":".join(f"{ip_bytes[i]:02x}{ip_bytes[i+1]:02x}" for i in range(0, 16, 2))
        return "0.0.0.0"

    def _finalize_flows(self, flows: dict) -> list[dict]:
        """Convert flow dictionary to list of flow records."""
        result = []
        now = utc_now()
        
        for flow_key, flow in flows.items():
            # Create flow record
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
                "features": {},  # Will be filled by features service
                "anomaly_score": None,
                "label": None,
                "_tcp_flags": flow["tcp_flags"],
                "_packet_timestamps": flow["packet_timestamps"],
            }
            result.append(record)
        
        return result
