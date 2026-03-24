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
        
        # 复合分数 → 严重等级映射（阈值基于加权复合分数，非原始 anomaly_score）
        self.severity_thresholds = {
            "critical": 0.80,
            "high": 0.60,
            "medium": 0.40,
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

    @staticmethod
    def _infer_flow_type(flow: dict) -> str:
        """
        轻量级单流类型推断，仅用于聚合分组。
        不替代 _determine_type，后者在组级别做最终判定。
        """
        features = flow.get("features", {})
        dst_port = flow.get("dst_port", 0)
        syn_count = features.get("syn_count", 0)
        total_packets = features.get("total_packets", 0)

        # 高 SYN 比例 → scan 倾向
        if total_packets > 0 and syn_count / max(total_packets, 1) > 0.5:
            return "scan"

        # 暴力破解端口特征
        if dst_port in (22, 23, 3389, 21):
            return "bruteforce"

        # 高流量特征 → dos 倾向
        total_bytes = features.get("total_bytes", 0)
        if total_bytes > 200000:  # 单流 >200KB
            return "dos"

        return "anomaly"

    def _aggregate_flows(self, flows: list[dict]) -> dict[str, list[dict]]:
        """
        多维聚合：src_ip + dst_target + service_key + inferred_type + time_bucket。
        同一源 IP 在同一时间窗口内的不同攻击模式会被拆分为不同告警。
        """
        groups: dict[str, list[dict]] = {}

        for flow in flows:
            src_ip = flow.get("src_ip", "unknown")
            ts_start = flow.get("ts_start")

            # 计算时间桶（与原逻辑一致）
            if isinstance(ts_start, datetime):
                bucket = int(ts_start.timestamp()) // self.window_sec * self.window_sec
            else:
                bucket = 0

            # 推断类型
            inferred = self._infer_flow_type(flow)

            # 目标维度
            dst_ip = flow.get("dst_ip", "unknown")
            dst_port = flow.get("dst_port", 0)
            proto = flow.get("proto", "TCP")

            # scan 类型合并目标（避免每个端口一条告警）
            dst_target = "multi" if inferred == "scan" else dst_ip
            service_key = "multi" if inferred == "scan" else f"{proto}/{dst_port}"

            group_key = f"{src_ip}|{dst_target}|{service_key}|{inferred}|{bucket}"

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
        
        # 复合严重度评分（替代旧的 max_score 单因子）
        composite_score, score_breakdown = self._compute_composite_score(flows)
        severity = self._score_to_severity(composite_score)

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

        # 构建 aggregation（保留原有字段 + 新增维度信息）
        aggregation = {
            "rule": f"src_ip+dst_target+service+type+{self.window_sec}s_window",
            "group_key": group_key,
            "count_flows": len(flows),
            "dimensions": ["src_ip", "dst_target", "service_key", "inferred_type", "time_bucket"],
            "composite_score": round(composite_score, 4),
            "score_breakdown": score_breakdown,
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

    def _compute_composite_score(self, flows: list[dict]) -> tuple[float, dict]:
        """
        计算复合严重度分数（0-1），返回 (composite_score, breakdown_dict)。

        权重分配：
          - max_score:           0.40  （组内最高异常分数）
          - flow_density:        0.25  （流数量密度，归一化）
          - duration_factor:     0.20  （活动持续时长，归一化）
          - aggregation_quality: 0.15  （组内一致性/质量）
        """
        # --- max_score ---
        scores = [f.get("anomaly_score", 0) for f in flows]
        max_score = max(scores) if scores else 0.0

        # --- flow_density: min(count / 20, 1.0) ---
        flow_density = min(len(flows) / 20.0, 1.0)

        # --- duration_factor: min(duration_sec / 300, 1.0) ---
        ts_starts = [f["ts_start"] for f in flows if isinstance(f.get("ts_start"), datetime)]
        ts_ends = [f["ts_end"] for f in flows if isinstance(f.get("ts_end"), datetime)]
        if ts_starts and ts_ends:
            duration_sec = (max(ts_ends) - min(ts_starts)).total_seconds()
        else:
            duration_sec = 0.0
        duration_factor = min(duration_sec / 300.0, 1.0)

        # --- aggregation_quality ---
        # 高于阈值的流占比 × 0.6 + 分数一致性 × 0.4
        above = sum(1 for s in scores if s >= self.score_threshold)
        ratio_above = above / max(len(scores), 1)

        if len(scores) > 1:
            mean_s = sum(scores) / len(scores)
            variance = sum((s - mean_s) ** 2 for s in scores) / len(scores)
            std_dev = variance ** 0.5
        else:
            std_dev = 0.0
        coherence = 1.0 - min(std_dev, 1.0)  # 标准差越小越一致

        aggregation_quality = ratio_above * 0.6 + coherence * 0.4

        # --- 加权合成 ---
        composite = (
            max_score * 0.40
            + flow_density * 0.25
            + duration_factor * 0.20
            + aggregation_quality * 0.15
        )
        composite = min(composite, 1.0)

        breakdown = {
            "max_score": round(max_score, 4),
            "flow_density": round(flow_density, 4),
            "duration_factor": round(duration_factor, 4),
            "aggregation_quality": round(aggregation_quality, 4),
            "composite": round(composite, 4),
        }

        return composite, breakdown

    def _score_to_severity(self, score: float) -> str:
        """将复合分数映射为严重等级。"""
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
