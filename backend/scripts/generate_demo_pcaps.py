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
    
    # 生成扫描示例
    scan_path = demo_dir / "scan_demo.pcap"
    generate_scan_pcap(scan_path)
    
    # 生成暴力破解示例
    bruteforce_path = demo_dir / "bruteforce_demo.pcap"
    generate_bruteforce_pcap(bruteforce_path)
    
    print()
    print("Done! Generated files:")
    print(f"  - {scan_path}")
    print(f"  - {bruteforce_path}")


if __name__ == "__main__":
    main()
