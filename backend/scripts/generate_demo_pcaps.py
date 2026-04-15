#!/usr/bin/env python3
"""Generate synthetic PCAP files (port scan, brute-force, DoS, benign mixes) for demos/tests."""

import struct
import socket
import random
import time
from pathlib import Path

PCAP_MAGIC = 0xA1B2C3D4
PCAP_VERSION_MAJOR = 2
PCAP_VERSION_MINOR = 4
PCAP_THISZONE = 0
PCAP_SIGFIGS = 0
PCAP_SNAPLEN = 65535
PCAP_LINKTYPE_ETHERNET = 1

_SERVER_PORTS = [22, 25, 53, 80, 110, 143, 443, 993, 995,
                 3306, 5432, 6379, 8080, 8443, 27017]


def write_pcap_header(f):
    f.write(struct.pack(
        '<IHHIIII',
        PCAP_MAGIC,
        PCAP_VERSION_MAJOR,
        PCAP_VERSION_MINOR,
        PCAP_THISZONE,
        PCAP_SIGFIGS,
        PCAP_SNAPLEN,
        PCAP_LINKTYPE_ETHERNET,
    ))


def write_packet(f, timestamp: float, data: bytes):
    ts_sec = int(timestamp)
    ts_usec = int((timestamp - ts_sec) * 1000000)
    caplen = len(data)
    f.write(struct.pack('<IIII', ts_sec, ts_usec, caplen, caplen))
    f.write(data)


def build_ethernet_header(src_mac: bytes, dst_mac: bytes, ethertype: int = 0x0800) -> bytes:
    return dst_mac + src_mac + struct.pack('>H', ethertype)


def build_ip_header(src_ip: str, dst_ip: str, proto: int, payload_len: int) -> bytes:
    version_ihl = (4 << 4) | 5
    total_len = 20 + payload_len
    ident = random.randint(0, 65535)
    flags_frag = 0x4000  # 不分片
    ttl = 64
    src = socket.inet_aton(src_ip)
    dst = socket.inet_aton(dst_ip)

    def pack(checksum: int) -> bytes:
        return struct.pack(
            '>BBHHHBBH4s4s',
            version_ihl, 0, total_len,
            ident, flags_frag,
            ttl, proto, checksum,
            src, dst,
        )

    return pack(ip_checksum(pack(0)))


def ip_checksum(header: bytes) -> int:
    if len(header) % 2 == 1:
        header += b'\x00'
    total = 0
    for i in range(0, len(header), 2):
        total += (header[i] << 8) + header[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def build_tcp_header(src_port: int, dst_port: int, flags: int, seq: int = 0, ack: int = 0) -> bytes:
    data_offset = (5 << 4)  # 5 * 4 = 20 字节，无选项
    return struct.pack(
        '>HHIIBBHHH',
        src_port, dst_port,
        seq, ack,
        data_offset, flags,
        65535, 0, 0,
    )


def _tcp_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port,
                flags, seq=0, ack=0, payload: bytes = b'') -> bytes:
    tcp = build_tcp_header(src_port, dst_port, flags, seq, ack) + payload
    ip = build_ip_header(src_ip, dst_ip, 6, len(tcp))
    return build_ethernet_header(src_mac, dst_mac) + ip + tcp


def build_tcp_syn_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port):
    return _tcp_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, 0x02)


def build_tcp_syn_ack_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port):
    return _tcp_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, 0x12)


def build_tcp_rst_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port):
    return _tcp_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, 0x04)


def build_tcp_ack_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, seq=0, ack=0):
    return _tcp_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, 0x10, seq, ack)


def build_tcp_data_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port,
                          payload_size: int, seq=0, ack=0):
    return _tcp_packet(
        src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port,
        0x18, seq, ack, b'\x00' * payload_size,
    )


def build_tcp_fin_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, seq=0, ack=0):
    return _tcp_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, 0x11, seq, ack)


def build_udp_packet(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, payload_size: int) -> bytes:
    payload = b'\x00' * payload_size
    udp = struct.pack('>HHHH', src_port, dst_port, 8 + payload_size, 0) + payload
    ip = build_ip_header(src_ip, dst_ip, 17, len(udp))
    return build_ethernet_header(src_mac, dst_mac) + ip + udp


def random_private_ip() -> str:
    pool = random.choice(["10", "172", "192"])
    if pool == "10":
        return f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
    if pool == "172":
        return f"172.{random.randint(16,31)}.{random.randint(0,255)}.{random.randint(1,254)}"
    return f"192.168.{random.randint(0,255)}.{random.randint(1,254)}"


def random_mac() -> bytes:
    return bytes(random.randint(0, 255) for _ in range(6))


def random_ephemeral_port() -> int:
    return random.randint(32768, 60999)


def random_server_port() -> int:
    return random.choice(_SERVER_PORTS)


def generate_tcp_session(
    client_ip: str, server_ip: str,
    client_mac: bytes, server_mac: bytes,
    client_port: int, server_port: int,
    base_time: float,
    num_rounds: int,
    request_size_range: tuple[int, int],
    response_size_range: tuple[int, int],
    iat_range: tuple[float, float],
    termination: str = "fin",
) -> list[tuple[float, bytes]]:
    """Build one full bidirectional TCP session. termination: 'fin' | 'rst' | 'none'."""
    pkts: list[tuple[float, bytes]] = []
    t = base_time
    seq_c = random.randint(1000, 99999)
    seq_s = random.randint(1000, 99999)

    # 三次握手
    pkts.append((t, build_tcp_syn_packet(
        client_mac, server_mac, client_ip, server_ip, client_port, server_port)))
    t += random.uniform(0.001, 0.01)
    pkts.append((t, build_tcp_syn_ack_packet(
        server_mac, client_mac, server_ip, client_ip, server_port, client_port)))
    t += random.uniform(0.001, 0.01)
    pkts.append((t, build_tcp_ack_packet(
        client_mac, server_mac, client_ip, server_ip, client_port, server_port,
        seq=seq_c, ack=seq_s + 1)))
    t += random.uniform(0.001, 0.005)

    for _ in range(num_rounds):
        req = random.randint(*request_size_range)
        resp = random.randint(*response_size_range)

        pkts.append((t, build_tcp_data_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port, req, seq=seq_c, ack=seq_s)))
        seq_c += req
        t += random.uniform(0.0005, 0.005)

        pkts.append((t, build_tcp_ack_packet(
            server_mac, client_mac, server_ip, client_ip,
            server_port, client_port, seq=seq_s, ack=seq_c)))
        t += random.uniform(0.005, 0.05)

        pkts.append((t, build_tcp_data_packet(
            server_mac, client_mac, server_ip, client_ip,
            server_port, client_port, resp, seq=seq_s, ack=seq_c)))
        seq_s += resp
        t += random.uniform(0.0005, 0.005)

        pkts.append((t, build_tcp_ack_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port, seq=seq_c, ack=seq_s)))

        t += random.uniform(*iat_range)

    if termination == "fin":
        pkts.append((t, build_tcp_fin_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port, seq=seq_c, ack=seq_s)))
        t += random.uniform(0.001, 0.01)
        pkts.append((t, build_tcp_fin_packet(
            server_mac, client_mac, server_ip, client_ip,
            server_port, client_port, seq=seq_s, ack=seq_c + 1)))
        t += random.uniform(0.001, 0.01)
        pkts.append((t, build_tcp_ack_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port, seq=seq_c + 1, ack=seq_s + 1)))
    elif termination == "rst":
        pkts.append((t, build_tcp_rst_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port)))

    return pkts


def _random_tcp_sessions(
    count_range: tuple[int, int],
    base_time: float,
    server_ports: list[int],
    num_rounds_range: tuple[int, int],
    req_range: tuple[int, int],
    resp_range: tuple[int, int],
    iat_range: tuple[float, float],
    spacing_range: tuple[float, float],
    termination: str | None = "fin",
) -> list[tuple[float, bytes]]:
    out: list[tuple[float, bytes]] = []
    for i in range(random.randint(*count_range)):
        term = termination
        if term is None:
            r = random.random()
            term = "fin" if r < 0.70 else "rst" if r < 0.95 else "none"
        out.extend(generate_tcp_session(
            client_ip=random_private_ip(), server_ip=random_private_ip(),
            client_mac=random_mac(), server_mac=random_mac(),
            client_port=random_ephemeral_port(),
            server_port=random.choice(server_ports),
            base_time=base_time + i * random.uniform(*spacing_range),
            num_rounds=random.randint(*num_rounds_range),
            request_size_range=req_range,
            response_size_range=resp_range,
            iat_range=iat_range,
            termination=term,
        ))
    return out


def generate_normal_short_sessions(base_time: float) -> list[tuple[float, bytes]]:
    """短连接 Web 请求：小载荷、快速完成、FIN 正常关闭。"""
    return _random_tcp_sessions(
        (30, 40), base_time,
        [80, 443, 8080], (1, 2), (64, 512), (128, 1024), (0.01, 0.1), (0.5, 2.0),
    )


def generate_normal_long_sessions(base_time: float) -> list[tuple[float, bytes]]:
    """长连接下载/流媒体：多轮交互、大响应载荷。"""
    return _random_tcp_sessions(
        (20, 30), base_time,
        [80, 443, 8443], (10, 20), (64, 256), (800, 1460), (0.05, 0.5), (1.0, 3.0),
    )


def generate_normal_request_response(base_time: float) -> list[tuple[float, bytes]]:
    """REST API 调用：请求/响应大小接近。"""
    return _random_tcp_sessions(
        (30, 40), base_time,
        _SERVER_PORTS, (3, 8), (100, 800), (100, 800), (0.1, 1.0), (0.8, 2.5),
    )


def generate_normal_keepalive(base_time: float) -> list[tuple[float, bytes]]:
    """数据库/监控心跳：极小载荷、长间隔。"""
    return _random_tcp_sessions(
        (20, 30), base_time,
        [3306, 5432, 6379, 27017], (2, 5), (16, 64), (16, 64), (2.0, 10.0), (2.0, 5.0),
    )


def generate_normal_mixed_termination(base_time: float) -> list[tuple[float, bytes]]:
    """70% FIN + 25% RST + 5% 无终止，覆盖多种 termination_type。"""
    return _random_tcp_sessions(
        (20, 30), base_time,
        _SERVER_PORTS, (2, 10), (64, 600), (64, 1000), (0.05, 1.0), (0.5, 2.0),
        termination=None,
    )


def generate_normal_udp_sessions(base_time: float) -> list[tuple[float, bytes]]:
    """DNS/NTP 等短 UDP 交互，确保模型见过非 TCP 正常流量。"""
    pkts: list[tuple[float, bytes]] = []
    for i in range(random.randint(20, 30)):
        c_ip, s_ip = random_private_ip(), random_private_ip()
        c_mac, s_mac = random_mac(), random_mac()
        c_port = random_ephemeral_port()
        s_port = random.choice([53, 123, 5353])
        t = base_time + i * random.uniform(0.3, 1.5)

        query_size = random.randint(20, 80)
        resp_size = random.randint(40, 512)

        pkts.append((t, build_udp_packet(c_mac, s_mac, c_ip, s_ip, c_port, s_port, query_size)))
        t += random.uniform(0.001, 0.05)
        pkts.append((t, build_udp_packet(s_mac, c_mac, s_ip, c_ip, s_port, c_port, resp_size)))

        if random.random() < 0.3:
            t += random.uniform(0.5, 2.0)
            pkts.append((t, build_udp_packet(c_mac, s_mac, c_ip, s_ip, c_port, s_port, query_size)))
            t += random.uniform(0.001, 0.05)
            pkts.append((t, build_udp_packet(s_mac, c_mac, s_ip, c_ip, s_port, c_port, resp_size)))
    return pkts


def generate_training_pcap(output_path: Path):
    """IsolationForest 训练用综合正常流量 PCAP。各场景时间错开以避免 60s 窗口误合并。"""
    print(f"Generating training PCAP: {output_path}")
    base_time = time.time()
    pkts: list[tuple[float, bytes]] = []
    pkts.extend(generate_normal_short_sessions(base_time))
    pkts.extend(generate_normal_long_sessions(base_time + 120))
    pkts.extend(generate_normal_request_response(base_time + 300))
    pkts.extend(generate_normal_keepalive(base_time + 500))
    pkts.extend(generate_normal_mixed_termination(base_time + 700))
    pkts.extend(generate_normal_udp_sessions(base_time + 900))

    pkts.sort(key=lambda x: x[0])
    with open(output_path, 'wb') as f:
        write_pcap_header(f)
        for ts, pkt in pkts:
            write_packet(f, ts, pkt)
    print(f"  生成 {len(pkts)} 个报文")


def write_packets_to_pcap(output_path: Path, packets: list[tuple[float, bytes]]) -> None:
    with open(output_path, 'wb') as f:
        write_pcap_header(f)
        for ts, pkt in sorted(packets, key=lambda x: x[0]):
            write_packet(f, ts, pkt)
    print(f"  Generated {len(packets)} packets")


def build_scan_packets(base_time: float | None = None) -> list[tuple[float, bytes]]:
    attacker_mac = b'\x00\x11\x22\x33\x44\x55'
    target_mac = b'\x66\x77\x88\x99\xaa\xbb'
    attacker_ip = "192.0.2.100"
    target_ip = "198.51.100.50"
    scan_ports = [
        21, 22, 23, 25, 53, 80, 110, 111, 135, 139,
        143, 443, 445, 993, 995, 1723, 3306, 3389, 5900, 8080,
    ]
    open_ports = {22, 80, 443}
    t0 = time.time() if base_time is None else base_time
    pkts: list[tuple[float, bytes]] = []

    for i, port in enumerate(scan_ports):
        ts = t0 + i * random.uniform(0.1, 0.3)
        src_port = random.randint(40000, 60000)
        pkts.append((ts, build_tcp_syn_packet(
            attacker_mac, target_mac, attacker_ip, target_ip, src_port, port)))

        resp_ts = ts + random.uniform(0.02, 0.05)
        if port in open_ports:
            pkts.append((resp_ts, build_tcp_syn_ack_packet(
                target_mac, attacker_mac, target_ip, attacker_ip, port, src_port)))
        else:
            pkts.append((resp_ts, build_tcp_rst_packet(
                target_mac, attacker_mac, target_ip, attacker_ip, port, src_port)))

    return pkts


def build_bruteforce_packets(
    base_time: float | None = None,
    num_attempts: int = 100,
) -> list[tuple[float, bytes]]:
    attacker_mac = b'\x00\x11\x22\x33\x44\x56'
    target_mac = b'\x66\x77\x88\x99\xaa\xbc'
    attacker_ip = "192.0.2.10"
    target_ip = "198.51.100.20"
    t0 = time.time() if base_time is None else base_time
    pkts: list[tuple[float, bytes]] = []

    for i in range(num_attempts):
        pkts.extend(generate_tcp_session(
            client_ip=attacker_ip, server_ip=target_ip,
            client_mac=attacker_mac, server_mac=target_mac,
            client_port=random.randint(40000, 60000),
            server_port=22,
            base_time=t0 + i * random.uniform(0.08, 0.2),
            num_rounds=random.randint(1, 2),
            request_size_range=(24, 96),
            response_size_range=(16, 64),
            iat_range=(0.01, 0.08),
            termination="rst" if random.random() < 0.7 else "fin",
        ))
    return pkts


def build_dos_packets(
    base_time: float | None = None,
    num_flows: int = 24,
    packets_per_flow: int = 180,
    payload_size: int = 1400,
) -> list[tuple[float, bytes]]:
    t0 = time.time() if base_time is None else base_time
    target_mac = b'\x66\x77\x88\x99\xaa\xbd'
    target_ip = "198.51.100.80"
    target_port = 8080
    pkts: list[tuple[float, bytes]] = []

    for i in range(num_flows):
        attacker_ip = f"192.0.2.{10 + (i % 40)}"
        attacker_mac = random_mac()
        src_port = 40000 + i
        t = t0 + i * random.uniform(0.2, 0.5)
        for _ in range(packets_per_flow):
            pkts.append((t, build_udp_packet(
                attacker_mac, target_mac, attacker_ip, target_ip,
                src_port, target_port, payload_size)))
            t += random.uniform(0.0004, 0.0008)
    return pkts


def generate_scan_pcap(output_path: Path):
    print(f"Generating port scan PCAP: {output_path}")
    write_packets_to_pcap(output_path, build_scan_packets())


def generate_bruteforce_pcap(output_path: Path):
    print(f"Generating SSH brute-force PCAP: {output_path}")
    write_packets_to_pcap(output_path, build_bruteforce_packets())


def generate_dos_pcap(output_path: Path):
    print(f"Generating DoS PCAP: {output_path}")
    write_packets_to_pcap(output_path, build_dos_packets())


def generate_training_attack_pcap(output_path: Path):
    print(f"Generating training attack PCAP: {output_path}")
    t0 = time.time()
    pkts: list[tuple[float, bytes]] = []
    pkts.extend(build_scan_packets(t0))
    pkts.extend(build_bruteforce_packets(t0 + 120))
    pkts.extend(build_dos_packets(t0 + 240))
    write_packets_to_pcap(output_path, pkts)


def main():
    demo_dir = Path(__file__).parent.parent / "data" / "pcaps"
    demo_dir.mkdir(parents=True, exist_ok=True)

    print("Generating demo PCAP files...")
    print(f"Output directory: {demo_dir}")
    print()

    scan_path = demo_dir / "scan_demo.pcap"
    generate_scan_pcap(scan_path)

    bruteforce_path = demo_dir / "bruteforce_demo.pcap"
    generate_bruteforce_pcap(bruteforce_path)

    training_path = demo_dir / "training_normal.pcap"
    generate_training_pcap(training_path)

    print()
    print("Done! Generated files:")
    print(f"  - {scan_path}")
    print(f"  - {bruteforce_path}")
    print(f"  - {training_path}")


if __name__ == "__main__":
    main()
