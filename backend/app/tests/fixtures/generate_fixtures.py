"""
Generate PCAP fixtures for regression testing.

Creates three deterministic PCAPs with known traffic patterns:

1. ssh_bruteforce.pcap  — many SYN packets from one IP to port 22
2. port_scan.pcap       — one IP scanning many ports
3. normal_traffic.pcap  — balanced traffic, low anomaly baseline
"""

import struct
import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def _write_pcap(path: str, packets: list[tuple[int, bytes]]) -> None:
    """Write a minimal PCAP file from a list of (timestamp, raw_packet) tuples."""
    PCAP_MAGIC = 0xA1B2C3D4
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHIIII", PCAP_MAGIC, 2, 4, 0, 0, 65535, 1))
        for ts_sec, pkt in packets:
            f.write(struct.pack("<IIII", ts_sec, 0, len(pkt), len(pkt)))
            f.write(pkt)


def _build_tcp_packet(
    src_ip: tuple[int, ...], dst_ip: tuple[int, ...],
    src_port: int, dst_port: int, seq: int, flags: int,
    payload_size: int = 20,
) -> bytes:
    """Build Ethernet + IPv4 + TCP + dummy payload."""
    tcp_hdr = struct.pack(
        "!HHIIBBHHH",
        src_port, dst_port, seq, 0,
        (5 << 4), flags, 65535, 0, 0,
    )
    payload = b"\x00" * payload_size
    ip_total = 20 + len(tcp_hdr) + payload_size
    ip_hdr = struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, ip_total, seq & 0xFFFF, 0, 64, 6, 0,
        bytes(src_ip), bytes(dst_ip),
    )
    eth_hdr = b"\x00" * 12 + struct.pack("!H", 0x0800)
    return eth_hdr + ip_hdr + tcp_hdr + payload


def generate_ssh_bruteforce(path: str, n_packets: int = 80) -> None:
    """SSH brute-force: many SYN from 192.0.2.10 → 198.51.100.20:22."""
    base_ts = 1_700_000_000
    packets = []
    for i in range(n_packets):
        flags = 0x02 if i % 3 != 2 else 0x10   # ~67 % SYN
        pkt = _build_tcp_packet(
            (192, 0, 2, 10), (198, 51, 100, 20),
            40000 + (i % 200), 22, i, flags,
        )
        packets.append((base_ts + i, pkt))
    _write_pcap(path, packets)


def generate_port_scan(path: str, n_packets: int = 60) -> None:
    """Port scan: 192.0.2.50 sends SYN to 198.51.100.30 on ports 20-79."""
    base_ts = 1_700_000_000
    packets = []
    for i in range(n_packets):
        dst_port = 20 + (i % 60)
        pkt = _build_tcp_packet(
            (192, 0, 2, 50), (198, 51, 100, 30),
            50000, dst_port, i, 0x02,
        )
        packets.append((base_ts + i, pkt))
    _write_pcap(path, packets)


def generate_normal_traffic(path: str, n_packets: int = 40) -> None:
    """Normal balanced traffic: bidirectional HTTP-like flow."""
    base_ts = 1_700_000_000
    packets = []
    for i in range(n_packets):
        if i % 2 == 0:
            pkt = _build_tcp_packet(
                (10, 0, 0, 5), (10, 0, 0, 6),
                12345, 80, i, 0x10, payload_size=100,
            )
        else:
            pkt = _build_tcp_packet(
                (10, 0, 0, 6), (10, 0, 0, 5),
                80, 12345, i, 0x10, payload_size=200,
            )
        packets.append((base_ts + i, pkt))
    _write_pcap(path, packets)


if __name__ == "__main__":
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    generate_ssh_bruteforce(str(FIXTURES_DIR / "regression_ssh_bruteforce.pcap"))
    generate_port_scan(str(FIXTURES_DIR / "regression_port_scan.pcap"))
    generate_normal_traffic(str(FIXTURES_DIR / "regression_normal_traffic.pcap"))
    print("Fixtures generated.")
