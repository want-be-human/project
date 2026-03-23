"""生成一个用于测试的小型示例 PCAP（依赖 dpkt）。"""
import struct
import time
import os

def make_demo_pcap(path: str, n_packets: int = 50):
    """写入一个最小可用的 PCAP，包含合成 TCP 报文。"""
    PCAP_MAGIC = 0xA1B2C3D4
    PCAP_VERSION_MAJOR = 2
    PCAP_VERSION_MINOR = 4
    LINKTYPE_ETHERNET = 1

    with open(path, "wb") as f:
        # 全局头
        f.write(struct.pack("<IHHIIII",
            PCAP_MAGIC, PCAP_VERSION_MAJOR, PCAP_VERSION_MINOR,
            0, 0, 65535, LINKTYPE_ETHERNET))

        base_ts = int(time.time()) - 300  # 5 分钟前

        for i in range(n_packets):
            ts_sec = base_ts + i
            ts_usec = 0

            # --- 构造 Ethernet + IP + TCP ---
            src_ip = bytes([192, 0, 2, 10])
            dst_ip = bytes([198, 51, 100, 20])
            src_port = 40000 + (i % 100)
            dst_port = 22
            tcp_flags = 0x02 if i % 5 == 0 else 0x10  # SYN or ACK

            # TCP 头（最小 20 字节）
            tcp_hdr = struct.pack("!HHIIBBHHH",
                src_port, dst_port,
                i, 0,              # seq, ack
                (5 << 4), tcp_flags,  # 数据偏移=5，标志位
                65535, 0, 0)       # 窗口、校验和、紧急指针

            payload = b"\x00" * 20  # 20 字节占位载荷

            # IP 头（20 字节）
            ip_total_len = 20 + len(tcp_hdr) + len(payload)
            ip_hdr = struct.pack("!BBHHHBBH4s4s",
                0x45, 0,            # 版本+IHL, DSCP
                ip_total_len, i, 0, # 总长度、标识、标志+偏移
                64, 6, 0,          # TTL、协议=TCP、校验和
                src_ip, dst_ip)

            # Ethernet 头（14 字节）
            eth_hdr = (b"\x00" * 6) + (b"\x00" * 6) + struct.pack("!H", 0x0800)

            packet = eth_hdr + ip_hdr + tcp_hdr + payload
            cap_len = len(packet)

            # 每包头
            f.write(struct.pack("<IIII", ts_sec, ts_usec, cap_len, cap_len))
            f.write(packet)

    print(f"Wrote {n_packets} packets → {path}  ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    os.makedirs("data/pcaps", exist_ok=True)
    make_demo_pcap("data/demo.pcap", 50)
