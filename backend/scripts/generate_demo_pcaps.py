#!/usr/bin/env python3
"""
为演示与测试生成合成 PCAP 文件。

生成内容：
- scan_demo.pcap: TCP 端口扫描模式
- bruteforce_demo.pcap: SSH 暴力破解模式

用法：
    python -m scripts.generate_pcaps

依赖：dpkt
"""

import struct
import socket
import random
import time
from pathlib import Path

# PCAP 文件格式常量
PCAP_MAGIC = 0xA1B2C3D4
PCAP_VERSION_MAJOR = 2
PCAP_VERSION_MINOR = 4
PCAP_THISZONE = 0
PCAP_SIGFIGS = 0
PCAP_SNAPLEN = 65535
PCAP_LINKTYPE_ETHERNET = 1


def write_pcap_header(f):
    """写入 PCAP 全局头。"""
    f.write(struct.pack(
        '<IHHIIII',
        PCAP_MAGIC,
        PCAP_VERSION_MAJOR,
        PCAP_VERSION_MINOR,
        PCAP_THISZONE,
        PCAP_SIGFIGS,
        PCAP_SNAPLEN,
        PCAP_LINKTYPE_ETHERNET
    ))


def write_packet(f, timestamp: float, packet_data: bytes):
    """写入单个报文及其报文头。"""
    ts_sec = int(timestamp)
    ts_usec = int((timestamp - ts_sec) * 1000000)
    caplen = len(packet_data)
    origlen = caplen
    
    # 报文头
    f.write(struct.pack('<IIII', ts_sec, ts_usec, caplen, origlen))
    # 报文数据
    f.write(packet_data)


def build_ethernet_header(src_mac: bytes, dst_mac: bytes, ethertype: int = 0x0800) -> bytes:
    """构造以太网头。"""
    return dst_mac + src_mac + struct.pack('>H', ethertype)


def build_ip_header(src_ip: str, dst_ip: str, proto: int, payload_len: int) -> bytes:
    """构造 IPv4 头。"""
    version_ihl = (4 << 4) | 5
    tos = 0
    total_len = 20 + payload_len
    identification = random.randint(0, 65535)
    flags_fragment = 0x4000  # 不分片
    ttl = 64
    checksum = 0  # 简化处理，真实场景需计算
    
    src = socket.inet_aton(src_ip)
    dst = socket.inet_aton(dst_ip)
    
    header = struct.pack(
        '>BBHHHBBH4s4s',
        version_ihl, tos, total_len,
        identification, flags_fragment,
        ttl, proto, checksum,
        src, dst
    )
    
    # 计算校验和
    checksum = ip_checksum(header)
    header = struct.pack(
        '>BBHHHBBH4s4s',
        version_ihl, tos, total_len,
        identification, flags_fragment,
        ttl, proto, checksum,
        src, dst
    )
    
    return header


def ip_checksum(header: bytes) -> int:
    """计算 IP 头校验和。"""
    if len(header) % 2 == 1:
        header += b'\x00'
    
    total = 0
    for i in range(0, len(header), 2):
        word = (header[i] << 8) + header[i + 1]
        total += word
    
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    
    return ~total & 0xFFFF


def build_tcp_header(src_port: int, dst_port: int, flags: int, seq: int = 0, ack: int = 0) -> bytes:
    """按指定标志位构造 TCP 头。"""
    data_offset = (5 << 4)  # 5 * 4 = 20 字节，无选项
    window = 65535
    checksum = 0  # 简化处理
    urgent = 0
    
    return struct.pack(
        '>HHIIBBHHH',
        src_port, dst_port,
        seq, ack,
        data_offset, flags,
        window, checksum, urgent
    )


def build_tcp_syn_packet(src_mac: bytes, dst_mac: bytes, src_ip: str, dst_ip: str, 
                          src_port: int, dst_port: int) -> bytes:
    """构造 TCP SYN 报文。"""
    tcp_flags = 0x02  # SYN
    tcp_header = build_tcp_header(src_port, dst_port, tcp_flags)
    ip_header = build_ip_header(src_ip, dst_ip, 6, len(tcp_header))  # 6 表示 TCP
    eth_header = build_ethernet_header(src_mac, dst_mac)
    
    return eth_header + ip_header + tcp_header


def build_tcp_syn_ack_packet(src_mac: bytes, dst_mac: bytes, src_ip: str, dst_ip: str,
                              src_port: int, dst_port: int) -> bytes:
    """构造 TCP SYN-ACK 报文。"""
    tcp_flags = 0x12  # SYN + ACK
    tcp_header = build_tcp_header(src_port, dst_port, tcp_flags)
    ip_header = build_ip_header(src_ip, dst_ip, 6, len(tcp_header))
    eth_header = build_ethernet_header(src_mac, dst_mac)
    
    return eth_header + ip_header + tcp_header


def build_tcp_rst_packet(src_mac: bytes, dst_mac: bytes, src_ip: str, dst_ip: str,
                          src_port: int, dst_port: int) -> bytes:
    """构造 TCP RST 报文。"""
    tcp_flags = 0x04  # RST
    tcp_header = build_tcp_header(src_port, dst_port, tcp_flags)
    ip_header = build_ip_header(src_ip, dst_ip, 6, len(tcp_header))
    eth_header = build_ethernet_header(src_mac, dst_mac)

    return eth_header + ip_header + tcp_header


def build_tcp_ack_packet(src_mac: bytes, dst_mac: bytes, src_ip: str, dst_ip: str,
                          src_port: int, dst_port: int, seq: int = 0, ack: int = 0) -> bytes:
    """构造 TCP ACK 报文（三次握手第三步等场景）。"""
    tcp_header = build_tcp_header(src_port, dst_port, 0x10, seq, ack)  # ACK
    ip_header = build_ip_header(src_ip, dst_ip, 6, len(tcp_header))
    eth_header = build_ethernet_header(src_mac, dst_mac)
    return eth_header + ip_header + tcp_header


def build_tcp_data_packet(src_mac: bytes, dst_mac: bytes, src_ip: str, dst_ip: str,
                           src_port: int, dst_port: int, payload_size: int,
                           seq: int = 0, ack: int = 0) -> bytes:
    """构造携带数据的 TCP PSH+ACK 报文。"""
    tcp_header = build_tcp_header(src_port, dst_port, 0x18, seq, ack)  # PSH+ACK
    payload = b'\x00' * payload_size
    ip_header = build_ip_header(src_ip, dst_ip, 6, len(tcp_header) + payload_size)
    eth_header = build_ethernet_header(src_mac, dst_mac)
    return eth_header + ip_header + tcp_header + payload


def build_tcp_fin_packet(src_mac: bytes, dst_mac: bytes, src_ip: str, dst_ip: str,
                          src_port: int, dst_port: int, seq: int = 0, ack: int = 0) -> bytes:
    """构造 TCP FIN+ACK 报文（正常关闭连接）。"""
    tcp_header = build_tcp_header(src_port, dst_port, 0x11, seq, ack)  # FIN+ACK
    ip_header = build_ip_header(src_ip, dst_ip, 6, len(tcp_header))
    eth_header = build_ethernet_header(src_mac, dst_mac)
    return eth_header + ip_header + tcp_header


def build_udp_packet(src_mac: bytes, dst_mac: bytes, src_ip: str, dst_ip: str,
                      src_port: int, dst_port: int, payload_size: int) -> bytes:
    """构造 UDP 数据报。"""
    payload = b'\x00' * payload_size
    udp_len = 8 + payload_size  # UDP 头 8 字节 + 载荷
    udp_header = struct.pack('>HHHH', src_port, dst_port, udp_len, 0)  # 校验和置 0
    ip_header = build_ip_header(src_ip, dst_ip, 17, len(udp_header) + payload_size)  # 17 = UDP
    eth_header = build_ethernet_header(src_mac, dst_mac)
    return eth_header + ip_header + udp_header + payload


# ================================================================
#                    随机化工具函数
# ================================================================

# 常见服务端口列表，用于随机选取目标端口
_SERVER_PORTS = [22, 25, 53, 80, 110, 143, 443, 993, 995,
                 3306, 5432, 6379, 8080, 8443, 27017]


def random_private_ip() -> str:
    """从 RFC 1918 私有地址空间随机生成一个 IP。"""
    pool = random.choice(["10", "172", "192"])
    if pool == "10":
        return f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
    elif pool == "172":
        return f"172.{random.randint(16,31)}.{random.randint(0,255)}.{random.randint(1,254)}"
    else:
        return f"192.168.{random.randint(0,255)}.{random.randint(1,254)}"


def random_mac() -> bytes:
    """生成 6 字节随机 MAC 地址。"""
    return bytes(random.randint(0, 255) for _ in range(6))


def random_ephemeral_port() -> int:
    """随机临时端口（客户端源端口）。"""
    return random.randint(32768, 60999)


def random_server_port() -> int:
    """从常见服务端口列表中随机选取。"""
    return random.choice(_SERVER_PORTS)


# ================================================================
#          TCP 会话模板：生成一个完整双向 TCP 会话
# ================================================================

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
    """
    生成一个完整双向 TCP 会话的报文序列。

    参数：
        client_ip/server_ip: 客户端/服务端 IP
        client_mac/server_mac: 客户端/服务端 MAC
        client_port/server_port: 客户端/服务端端口
        base_time: 会话起始时间戳
        num_rounds: 请求-响应轮数
        request_size_range: 请求载荷大小范围 (min, max)
        response_size_range: 响应载荷大小范围 (min, max)
        iat_range: 轮间间隔范围 (min_sec, max_sec)
        termination: 终止方式 "fin" | "rst" | "none"

    返回：
        (timestamp, packet_bytes) 元组列表
    """
    packets = []
    t = base_time
    seq_c, seq_s = random.randint(1000, 99999), random.randint(1000, 99999)

    # ── 三次握手 ──
    # SYN
    packets.append((t, build_tcp_syn_packet(
        client_mac, server_mac, client_ip, server_ip, client_port, server_port)))
    t += random.uniform(0.001, 0.01)
    # SYN-ACK
    packets.append((t, build_tcp_syn_ack_packet(
        server_mac, client_mac, server_ip, client_ip, server_port, client_port)))
    t += random.uniform(0.001, 0.01)
    # ACK
    packets.append((t, build_tcp_ack_packet(
        client_mac, server_mac, client_ip, server_ip, client_port, server_port,
        seq=seq_c, ack=seq_s + 1)))
    t += random.uniform(0.001, 0.005)

    # ── 数据交换轮次 ──
    for _ in range(num_rounds):
        req_size = random.randint(*request_size_range)
        resp_size = random.randint(*response_size_range)

        # 客户端请求 (PSH+ACK)
        packets.append((t, build_tcp_data_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port, req_size, seq=seq_c, ack=seq_s)))
        seq_c += req_size
        t += random.uniform(0.0005, 0.005)

        # 服务端 ACK
        packets.append((t, build_tcp_ack_packet(
            server_mac, client_mac, server_ip, client_ip,
            server_port, client_port, seq=seq_s, ack=seq_c)))
        t += random.uniform(0.005, 0.05)

        # 服务端响应 (PSH+ACK)
        packets.append((t, build_tcp_data_packet(
            server_mac, client_mac, server_ip, client_ip,
            server_port, client_port, resp_size, seq=seq_s, ack=seq_c)))
        seq_s += resp_size
        t += random.uniform(0.0005, 0.005)

        # 客户端 ACK
        packets.append((t, build_tcp_ack_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port, seq=seq_c, ack=seq_s)))

        # 轮间间隔
        t += random.uniform(*iat_range)

    # ── 连接终止 ──
    if termination == "fin":
        # 四次挥手（简化为三步）
        packets.append((t, build_tcp_fin_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port, seq=seq_c, ack=seq_s)))
        t += random.uniform(0.001, 0.01)
        packets.append((t, build_tcp_fin_packet(
            server_mac, client_mac, server_ip, client_ip,
            server_port, client_port, seq=seq_s, ack=seq_c + 1)))
        t += random.uniform(0.001, 0.01)
        packets.append((t, build_tcp_ack_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port, seq=seq_c + 1, ack=seq_s + 1)))
    elif termination == "rst":
        # RST 异常终止
        packets.append((t, build_tcp_rst_packet(
            client_mac, server_mac, client_ip, server_ip,
            client_port, server_port)))

    return packets


# ================================================================
#          正常流量场景生成器
# ================================================================

def generate_normal_short_sessions(base_time: float) -> list[tuple[float, bytes]]:
    """
    短连接场景：模拟快速 Web 请求。

    特征：1-2 轮交互、小载荷、短持续时间、FIN 正常关闭。
    覆盖：is_short_flow、低 flow_duration_ms、高 packets_per_second。
    """
    all_packets = []
    for i in range(random.randint(30, 40)):
        c_ip, s_ip = random_private_ip(), random_private_ip()
        session = generate_tcp_session(
            client_ip=c_ip, server_ip=s_ip,
            client_mac=random_mac(), server_mac=random_mac(),
            client_port=random_ephemeral_port(), server_port=random.choice([80, 443, 8080]),
            base_time=base_time + i * random.uniform(0.5, 2.0),
            num_rounds=random.randint(1, 2),
            request_size_range=(64, 512),
            response_size_range=(128, 1024),
            iat_range=(0.01, 0.1),
            termination="fin",
        )
        all_packets.extend(session)
    return all_packets


def generate_normal_long_sessions(base_time: float) -> list[tuple[float, bytes]]:
    """
    长连接场景：模拟文件下载或流媒体。

    特征：10-20 轮交互、大响应载荷、较长持续时间。
    覆盖：高 total_bytes、bytes_asymmetry、大 avg_pkt_size_bwd。
    """
    all_packets = []
    for i in range(random.randint(20, 30)):
        c_ip, s_ip = random_private_ip(), random_private_ip()
        session = generate_tcp_session(
            client_ip=c_ip, server_ip=s_ip,
            client_mac=random_mac(), server_mac=random_mac(),
            client_port=random_ephemeral_port(), server_port=random.choice([80, 443, 8443]),
            base_time=base_time + i * random.uniform(1.0, 3.0),
            num_rounds=random.randint(10, 20),
            request_size_range=(64, 256),
            response_size_range=(800, 1460),
            iat_range=(0.05, 0.5),
            termination="fin",
        )
        all_packets.extend(session)
    return all_packets


def generate_normal_request_response(base_time: float) -> list[tuple[float, bytes]]:
    """
    请求-响应场景：模拟 REST API 调用。

    特征：3-8 轮交互、请求与响应大小接近。
    覆盖：均衡 fwd_ratio、低 bytes_asymmetry。
    """
    all_packets = []
    for i in range(random.randint(30, 40)):
        c_ip, s_ip = random_private_ip(), random_private_ip()
        session = generate_tcp_session(
            client_ip=c_ip, server_ip=s_ip,
            client_mac=random_mac(), server_mac=random_mac(),
            client_port=random_ephemeral_port(), server_port=random_server_port(),
            base_time=base_time + i * random.uniform(0.8, 2.5),
            num_rounds=random.randint(3, 8),
            request_size_range=(100, 800),
            response_size_range=(100, 800),
            iat_range=(0.1, 1.0),
            termination="fin",
        )
        all_packets.extend(session)
    return all_packets


def generate_normal_keepalive(base_time: float) -> list[tuple[float, bytes]]:
    """
    低频心跳/控制场景：模拟数据库连接保活或监控探针。

    特征：2-5 轮交互、极小载荷、长间隔。
    覆盖：高 iat_mean_ms、高 iat_std_ms、长 flow_duration_ms。
    """
    all_packets = []
    for i in range(random.randint(20, 30)):
        c_ip, s_ip = random_private_ip(), random_private_ip()
        session = generate_tcp_session(
            client_ip=c_ip, server_ip=s_ip,
            client_mac=random_mac(), server_mac=random_mac(),
            client_port=random_ephemeral_port(),
            server_port=random.choice([3306, 5432, 6379, 27017]),
            base_time=base_time + i * random.uniform(2.0, 5.0),
            num_rounds=random.randint(2, 5),
            request_size_range=(16, 64),
            response_size_range=(16, 64),
            iat_range=(2.0, 10.0),
            termination="fin",
        )
        all_packets.extend(session)
    return all_packets


def generate_normal_mixed_termination(base_time: float) -> list[tuple[float, bytes]]:
    """
    混合终止方式场景：70% FIN + 25% RST + 5% 无终止。

    覆盖：termination_type、fin_count、rst_count、rst_ratio 的多样性。
    """
    all_packets = []
    for i in range(random.randint(20, 30)):
        c_ip, s_ip = random_private_ip(), random_private_ip()
        # 随机选择终止方式
        r = random.random()
        if r < 0.70:
            term = "fin"
        elif r < 0.95:
            term = "rst"
        else:
            term = "none"
        session = generate_tcp_session(
            client_ip=c_ip, server_ip=s_ip,
            client_mac=random_mac(), server_mac=random_mac(),
            client_port=random_ephemeral_port(), server_port=random_server_port(),
            base_time=base_time + i * random.uniform(0.5, 2.0),
            num_rounds=random.randint(2, 10),
            request_size_range=(64, 600),
            response_size_range=(64, 1000),
            iat_range=(0.05, 1.0),
            termination=term,
        )
        all_packets.extend(session)
    return all_packets


def generate_normal_udp_sessions(base_time: float) -> list[tuple[float, bytes]]:
    """
    UDP 正常流量场景：模拟 DNS 查询等短交互。

    覆盖：is_udp=1 特征，确保模型见过非 TCP 正常流量。
    """
    all_packets = []
    for i in range(random.randint(20, 30)):
        c_ip, s_ip = random_private_ip(), random_private_ip()
        c_mac, s_mac = random_mac(), random_mac()
        c_port = random_ephemeral_port()
        s_port = random.choice([53, 123, 5353])  # DNS / NTP / mDNS
        t = base_time + i * random.uniform(0.3, 1.5)

        # 查询报文（客户端 → 服务端）
        query_size = random.randint(20, 80)
        all_packets.append((t, build_udp_packet(
            c_mac, s_mac, c_ip, s_ip, c_port, s_port, query_size)))

        # 响应报文（服务端 → 客户端）
        t += random.uniform(0.001, 0.05)
        resp_size = random.randint(40, 512)
        all_packets.append((t, build_udp_packet(
            s_mac, c_mac, s_ip, c_ip, s_port, c_port, resp_size)))

        # 部分会话有多轮交互（如 DNS 重试）
        if random.random() < 0.3:
            t += random.uniform(0.5, 2.0)
            all_packets.append((t, build_udp_packet(
                c_mac, s_mac, c_ip, s_ip, c_port, s_port, query_size)))
            t += random.uniform(0.001, 0.05)
            all_packets.append((t, build_udp_packet(
                s_mac, c_mac, s_ip, c_ip, s_port, c_port, resp_size)))

    return all_packets


# ================================================================
#          训练 PCAP 组合函数
# ================================================================

def generate_training_pcap(output_path: Path):
    """
    生成用于 IsolationForest 训练的综合正常流量 PCAP。

    包含六类场景：短连接、长连接、请求-响应、低频心跳、混合终止、UDP。
    各场景 base_time 错开以避免 ParsingService 60s 窗口误合并。
    """
    print(f"Generating training PCAP: {output_path}")

    base_time = time.time()
    all_packets = []

    # 各场景错开时间，避免 60s 窗口内不同场景的会话被合并
    all_packets.extend(generate_normal_short_sessions(base_time))
    all_packets.extend(generate_normal_long_sessions(base_time + 120))
    all_packets.extend(generate_normal_request_response(base_time + 300))
    all_packets.extend(generate_normal_keepalive(base_time + 500))
    all_packets.extend(generate_normal_mixed_termination(base_time + 700))
    all_packets.extend(generate_normal_udp_sessions(base_time + 900))

    # 按时间戳排序后写入
    all_packets.sort(key=lambda x: x[0])

    with open(output_path, 'wb') as f:
        write_pcap_header(f)
        for ts, pkt in all_packets:
            write_packet(f, ts, pkt)

    print(f"  生成 {len(all_packets)} 个报文")


# ================================================================
#          既有攻击场景（保留不变）
# ================================================================

def generate_scan_pcap(output_path: Path):
    """
    生成端口扫描场景 PCAP。

    模式：单源 IP 对目标多个端口进行扫描。
    """
    print(f"Generating port scan PCAP: {output_path}")
    
    attacker_mac = b'\x00\x11\x22\x33\x44\x55'
    target_mac = b'\x66\x77\x88\x99\xaa\xbb'
    attacker_ip = "192.0.2.100"
    target_ip = "198.51.100.50"
    
    # 常见扫描端口
    scan_ports = [21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 
                  993, 995, 1723, 3306, 3389, 5900, 8080]
    
    # 开放端口（会返回 SYN-ACK）
    open_ports = {22, 80, 443}
    
    base_time = time.time()
    packets = []
    
    for i, port in enumerate(scan_ports):
        # 增加时间抖动（探测间隔 100-300ms）
        timestamp = base_time + i * random.uniform(0.1, 0.3)
        src_port = random.randint(40000, 60000)
        
        # 攻击方发起 SYN 报文
        syn = build_tcp_syn_packet(attacker_mac, target_mac, attacker_ip, target_ip, src_port, port)
        packets.append((timestamp, syn))
        
        # 响应（20-50ms 后）
        resp_time = timestamp + random.uniform(0.02, 0.05)
        
        if port in open_ports:
            # SYN-ACK 响应
            syn_ack = build_tcp_syn_ack_packet(target_mac, attacker_mac, target_ip, attacker_ip, port, src_port)
            packets.append((resp_time, syn_ack))
        else:
            # RST 响应（端口关闭）
            rst = build_tcp_rst_packet(target_mac, attacker_mac, target_ip, attacker_ip, port, src_port)
            packets.append((resp_time, rst))
    
    # 写入 PCAP 文件
    with open(output_path, 'wb') as f:
        write_pcap_header(f)
        for ts, pkt in packets:
            write_packet(f, ts, pkt)
    
    print(f"  Generated {len(packets)} packets")


def generate_bruteforce_pcap(output_path: Path):
    """
    生成 SSH 暴力破解场景 PCAP。

    模式：对 SSH 22 端口进行高频连接尝试。
    """
    print(f"Generating SSH brute-force PCAP: {output_path}")
    
    attacker_mac = b'\x00\x11\x22\x33\x44\x56'
    target_mac = b'\x66\x77\x88\x99\xaa\xbc'
    attacker_ip = "192.0.2.10"
    target_ip = "198.51.100.20"
    target_port = 22
    
    base_time = time.time()
    packets = []
    
    # 生成 100 次快速连接尝试
    num_attempts = 100
    
    for i in range(num_attempts):
        # 极快尝试（间隔 10-50ms）- 暴力破解典型特征
        timestamp = base_time + i * random.uniform(0.01, 0.05)
        src_port = random.randint(40000, 60000)
        
        # SYN 报文
        syn = build_tcp_syn_packet(attacker_mac, target_mac, attacker_ip, target_ip, src_port, target_port)
        packets.append((timestamp, syn))
        
        # SYN-ACK 响应（SSH 端口开放）
        resp_time = timestamp + random.uniform(0.005, 0.015)
        syn_ack = build_tcp_syn_ack_packet(target_mac, attacker_mac, target_ip, attacker_ip, target_port, src_port)
        packets.append((resp_time, syn_ack))
        
        # 有时补充 RST（认证失败，连接关闭）
        if random.random() < 0.7:
            rst_time = resp_time + random.uniform(0.1, 0.3)
            rst = build_tcp_rst_packet(target_mac, attacker_mac, target_ip, attacker_ip, target_port, src_port)
            packets.append((rst_time, rst))
    
    # 写入 PCAP 文件
    with open(output_path, 'wb') as f:
        write_pcap_header(f)
        for ts, pkt in sorted(packets, key=lambda x: x[0]):
            write_packet(f, ts, pkt)
    
    print(f"  Generated {len(packets)} packets")


def main():
    """生成示例 PCAP 文件。"""
    # 创建输出目录
    demo_dir = Path(__file__).parent.parent / "data" / "pcaps"
    demo_dir.mkdir(parents=True, exist_ok=True)

    print("Generating demo PCAP files...")
    print(f"Output directory: {demo_dir}")
    print()

    # 既有攻击场景
    scan_path = demo_dir / "scan_demo.pcap"
    generate_scan_pcap(scan_path)

    bruteforce_path = demo_dir / "bruteforce_demo.pcap"
    generate_bruteforce_pcap(bruteforce_path)

    # 训练用正常流量
    training_path = demo_dir / "training_normal.pcap"
    generate_training_pcap(training_path)

    print()
    print("Done! Generated files:")
    print(f"  - {scan_path}")
    print(f"  - {bruteforce_path}")
    print(f"  - {training_path}")


if __name__ == "__main__":
    main()
