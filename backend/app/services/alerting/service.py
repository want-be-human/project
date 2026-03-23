"""
告警服务。
将 Flow 生成并聚合为 Alert。
"""

import json
from datetime import datetime

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now

logger = get_logger(__name__)


class AlertingService:
    """
用于生成并聚合告警的服务。

遵循 DOC B B4.5 规范。
"""

    def __init__(
        self,
        score_threshold: float = 0.7,
        window_sec: int = 60,
    ):
        self.score_threshold = score_threshold
        self.window_sec = window_sec
        
        # 基于分数的严重等级映射
        self.severity_thresholds = {
            "critical": 0.95,
            "high": 0.85,
            "medium": 0.70,
            "low": 0.0,
        }

    def generate_alerts(
        self,
        flows: list[dict],
        pcap_id: str,
    ) -> list[dict]:
        """
        Generate alerts from scored flows.
        
        Args:
            flows: List of flows with anomaly_score
            pcap_id: ID of the source PCAP
            
        Returns:
            List of alert dictionaries
        """
        # 筛选异常流
        anomalous = [
            f for f in flows
            if (f.get("anomaly_score") or 0) >= self.score_threshold
        ]
        
        if not anomalous:
            logger.info("No anomalous flows found above threshold")
            return []
        
        logger.info(f"Found {len(anomalous)} anomalous flows")
        
        # 按聚合规则分组：same_src_ip + window
        groups = self._aggregate_flows(anomalous)
        
        # 基于分组生成告警
        alerts = []
        for group_key, group_flows in groups.items():
            alert = self._create_alert(group_key, group_flows, pcap_id)
            alerts.append(alert)
        
        logger.info(f"Generated {len(alerts)} alerts")
        return alerts

    def _aggregate_flows(self, flows: list[dict]) -> dict[str, list[dict]]:
        """
        Aggregate flows by src_ip + time window.
        
        Returns dict mapping group_key to list of flows.
        """
        groups = {}
        
        for flow in flows:
            src_ip = flow.get("src_ip", "unknown")
            ts_start = flow.get("ts_start")
            
            # 计算时间桶
            if isinstance(ts_start, datetime):
                bucket = int(ts_start.timestamp()) // self.window_sec * self.window_sec
            else:
                bucket = 0
            
            group_key = f"{src_ip}@{bucket}"
            
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(flow)
        
        return groups

    def _create_alert(
        self,
        group_key: str,
        flows: list[dict],
        pcap_id: str,
    ) -> dict:
        """根据一组流量创建告警。"""
        now = utc_now()
        
        # 计算时间窗口
        ts_starts = [f.get("ts_start") for f in flows if f.get("ts_start")]
        ts_ends = [f.get("ts_end") for f in flows if f.get("ts_end")]
        
        window_start = min(t for t in ts_starts if t is not None) if ts_starts else now
        window_end = max(t for t in ts_ends if t is not None) if ts_ends else now
        
        # 从最异常流中提取主要实体
        flows_sorted = sorted(flows, key=lambda x: x.get("anomaly_score", 0), reverse=True)
        primary_flow = flows_sorted[0]
        
        # 由最高分计算严重等级
        max_score = max(f.get("anomaly_score", 0) for f in flows)
        severity = self._score_to_severity(max_score)
        
        # 基于模式判断告警类型
        alert_type = self._determine_type(flows)
        
        # 构建 evidence
        flow_ids = [f.get("id") for f in flows if f.get("id")]
        top_flows = self._get_top_flows(flows_sorted[:5])
        top_features = self._get_top_features(flows)
        
        evidence = {
            "flow_ids": flow_ids,
            "top_flows": top_flows,
            "top_features": top_features,
            "pcap_ref": {"pcap_id": pcap_id, "offset_hint": None},
        }
        
        # 构建 aggregation
        aggregation = {
            "rule": f"same_src_ip + {self.window_sec}s_window",
            "group_key": group_key,
            "count_flows": len(flows),
        }
        
        alert = {
            "id": generate_uuid(),
            "version": "1.1",
            "created_at": now,
            "severity": severity,
            "status": "new",
            "type": alert_type,
            "time_window_start": window_start,
            "time_window_end": window_end,
            "primary_src_ip": primary_flow.get("src_ip", "0.0.0.0"),
            "primary_dst_ip": primary_flow.get("dst_ip", "0.0.0.0"),
            "primary_proto": primary_flow.get("proto", "TCP"),
            "primary_dst_port": primary_flow.get("dst_port", 0),
            "evidence": json.dumps(evidence),
            "aggregation": json.dumps(aggregation),
            "agent": json.dumps({
                "triage_summary": None,
                "investigation_id": None,
                "recommendation_id": None,
            }),
            "twin": json.dumps({
                "plan_id": None,
                "dry_run_id": None,
            }),
            "tags": json.dumps(["auto"]),
            "notes": "",
            "_flow_ids": flow_ids,  # 用于创建 alert_flows 关联
        }
        
        return alert

    def _score_to_severity(self, score: float) -> str:
        """将异常分数映射为严重等级。"""
        for severity, threshold in self.severity_thresholds.items():
            if score >= threshold:
                return severity
        return "low"

    def _determine_type(self, flows: list[dict]) -> str:
        """根据流量模式判定告警类型。"""
        # 统计唯一目标
        dst_ips = set(f.get("dst_ip") for f in flows)
        dst_ports = set(f.get("dst_port") for f in flows)
        
        # SYN 数高且目标多 -> 扫描（scan）
        total_syn = sum(f.get("features", {}).get("syn_count", 0) for f in flows)
        total_packets = sum(f.get("features", {}).get("total_packets", 0) for f in flows)
        
        if len(dst_ips) > 5 or len(dst_ports) > 10:
            return "scan"
        
        if total_packets > 100 and total_syn / max(total_packets, 1) > 0.5:
            return "scan"
        
        # 单目标且连接多 -> bruteforce
        if len(dst_ips) == 1 and len(flows) > 5:
            dst_port = flows[0].get("dst_port", 0)
            if dst_port in [22, 23, 3389, 21]:  # SSH、Telnet、RDP、FTP
                return "bruteforce"
        
        # 单目标高流量 -> dos
        total_bytes = sum(f.get("features", {}).get("total_bytes", 0) for f in flows)
        if total_bytes > 1000000 and len(dst_ips) == 1:  # >1MB
            return "dos"
        
        # 默认归类为 anomaly
        return "anomaly"

    def _get_top_flows(self, flows: list[dict]) -> list[dict]:
        """获取用于证据展示的高优先级流摘要。"""
        result = []
        for flow in flows:
            summary = f"{flow.get('proto', 'TCP')}/{flow.get('dst_port', 0)}"
            if flow.get("features", {}).get("syn_count", 0) > 5:
                summary += " SYN burst"
            
            result.append({
                "flow_id": flow.get("id", ""),
                "anomaly_score": flow.get("anomaly_score", 0),
                "summary": summary,
            })
        return result

    def _get_top_features(self, flows: list[dict]) -> list[dict]:
        """获取跨流量的主要贡献特征。"""
        # 聚合特征
        feature_values = {}
        
        for flow in flows:
            features = flow.get("features", {})
            for name, value in features.items():
                if isinstance(value, (int, float)):
                    if name not in feature_values:
                        feature_values[name] = []
                    feature_values[name].append(value)
        
        # 找出方差较高或极值特征
        top_features = []
        
        # 检查 SYN 计数是否偏高
        syn_counts = feature_values.get("syn_count", [])
        if syn_counts and max(syn_counts) > 10:
            top_features.append({
                "name": "syn_count",
                "value": int(max(syn_counts)),
                "direction": "high",
            })
        
        # 检查包速率是否偏高
        total_packets = feature_values.get("total_packets", [])
        if total_packets and max(total_packets) > 100:
            top_features.append({
                "name": "total_packets",
                "value": int(max(total_packets)),
                "direction": "high",
            })
        
        # 检查 RST 比例
        rst_ratios = feature_values.get("rst_ratio", [])
        if rst_ratios and max(rst_ratios) > 0.3:
            top_features.append({
                "name": "rst_ratio",
                "value": round(max(rst_ratios), 2),
                "direction": "high",
            })

        # --- 低阈值补充候选特征 ---
        # bytes_per_packet 特征
        bpp = feature_values.get("bytes_per_packet", [])
        if bpp and max(bpp) > 0:
            top_features.append({
                "name": "bytes_per_packet",
                "value": round(max(bpp), 2),
                "direction": "high",
            })
        # flow_duration_ms（极短时长/扫描特征）
        dur = feature_values.get("flow_duration_ms", [])
        if dur:
            min_dur = min(dur)
            top_features.append({
                "name": "flow_duration_ms",
                "value": round(min_dur, 2),
                "direction": "low" if min_dur < 100 else "high",
            })
        # fwd_ratio_packets（单向流特征）
        fwd = feature_values.get("fwd_ratio_packets", [])
        if fwd and max(fwd) >= 0.9:
            top_features.append({
                "name": "fwd_ratio_packets",
                "value": round(max(fwd), 2),
                "direction": "high",
            })
        
        return top_features[:5]  # 最多保留 5 项
