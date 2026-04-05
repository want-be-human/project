"""
告警服务。
将 Flow 生成并聚合为 Alert。
"""

import json
from datetime import datetime

from app.core.logging import get_logger
from app.core.scoring_policy import SEVERITY_THRESHOLDS, COMPOSITE_WEIGHTS
from app.core.utils import generate_uuid, utc_now

logger = get_logger(__name__)

# ── 服务端口语义分类 ──
_AUTH_PORTS = frozenset({
    22, 23, 21, 3389,           # SSH, Telnet, FTP, RDP
    3306, 5432, 1433,           # MySQL, PostgreSQL, MSSQL
    6379, 27017,                # Redis, MongoDB
    445, 5900,                  # SMB, VNC
})
_WEB_PORTS = frozenset({80, 443, 8080, 8443})
_DNS_PORTS = frozenset({53})
_MAIL_PORTS = frozenset({25, 587, 465, 993, 995})


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
        self.severity_thresholds = SEVERITY_THRESHOLDS

    def generate_alerts(
        self,
        flows: list[dict],
        pcap_id: str,
    ) -> list[dict]:
        """
        从评分后的流量中生成告警。

        Args:
            flows: 包含 anomaly_score 的流量列表
            pcap_id: 来源 PCAP 的 ID

        Returns:
            告警字典列表
        """
        # 筛选异常流
        anomalous = [
            f for f in flows
            if (f.get("anomaly_score") or 0) >= self.score_threshold
        ]
        
        if not anomalous:
            logger.info("未发现超过阈值的异常流")
            return []
        
        logger.info(f"发现 {len(anomalous)} 条异常流")
        
        # 按聚合规则分组：same_src_ip + window
        groups = self._aggregate_flows(anomalous)
        
        # 基于分组生成告警
        alerts = []
        for group_key, group_flows in groups.items():
            alert = self._create_alert(group_key, group_flows, pcap_id)
            alerts.append(alert)
        
        logger.info(f"已生成 {len(alerts)} 条告警")
        return alerts

    @staticmethod
    def _infer_flow_type(flow: dict) -> str:
        """
        检测层优先的单流类型推断，启发式兜底。

        优先级：
          1. features.final_label（如果是具体攻击类型，非 normal/anomaly）
          2. features.rule_type（检测层规则推断）
          3. 启发式规则（向后兼容 fallback）
        """
        features = flow.get("features", {})

        # Priority 1: 检测层 final_label
        final_label = features.get("final_label")
        if final_label and final_label not in ("normal", "anomaly"):
            return final_label

        # Priority 2: 检测层 rule_type
        rule_type = features.get("rule_type")
        if rule_type and rule_type not in ("anomaly",):
            return rule_type

        # Priority 3: 启发式 fallback
        result, _, _ = AlertingService._infer_flow_type_detailed(flow)
        return result

    @staticmethod
    def _infer_flow_type_detailed(flow: dict) -> tuple[str, list[str], dict]:
        """
        增强版单流类型推断，返回 (type, reason_codes, details)。
        不替代 _determine_type，后者在组级别做最终判定。
        """
        features = flow.get("features", {})
        dst_port = flow.get("dst_port", 0)

        syn_count = features.get("syn_count", 0)
        total_packets = features.get("total_packets", 0)
        total_bytes = features.get("total_bytes", 0)
        syn_ratio = syn_count / max(total_packets, 1)
        rst_ratio = features.get("rst_ratio", 0.0)
        handshake = features.get("handshake_completeness", 1.0)
        is_short = features.get("is_short_flow", 0)
        pps = features.get("packets_per_second", 0)
        bps = features.get("bytes_per_second", 0)
        bytes_asymmetry = features.get("bytes_asymmetry", 0)

        # ── scan 判定：评分制，≥2 分命中 ──
        scan_reasons: list[str] = []
        scan_score = 0
        if syn_ratio > 0.5:
            scan_score += 2
            scan_reasons.append("SCAN_SYN_RATIO")
        if handshake < 0.5:
            scan_score += 1
            scan_reasons.append("SCAN_INCOMPLETE_HANDSHAKE")
        if rst_ratio > 0.3:
            scan_score += 1
            scan_reasons.append("SCAN_HIGH_RST")
        if is_short:
            scan_score += 1
            scan_reasons.append("SCAN_SHORT_FLOW")

        if scan_score >= 2:
            details = {"syn_ratio": round(syn_ratio, 4), "rst_ratio": round(rst_ratio, 4),
                       "handshake_completeness": round(handshake, 4), "scan_score": scan_score}
            return "scan", scan_reasons, details

        # ── bruteforce 判定：认证端口语义 ──
        if dst_port in _AUTH_PORTS:
            brute_reasons = ["BRUTE_AUTH_PORT"]
            if is_short:
                brute_reasons.append("BRUTE_SHORT_FLOW")
            if rst_ratio > 0.3:
                brute_reasons.append("BRUTE_HIGH_RST")
            if handshake < 0.7:
                brute_reasons.append("BRUTE_LOW_HANDSHAKE")
            details = {"dst_port": dst_port, "rst_ratio": round(rst_ratio, 4),
                       "handshake_completeness": round(handshake, 4)}
            return "bruteforce", brute_reasons, details

        # ── dos 判定：流量/速率多维度 ──
        dos_reasons: list[str] = []
        if total_bytes > 200000:
            dos_reasons.append("DOS_HIGH_VOLUME")
        if pps > 1000:
            dos_reasons.append("DOS_HIGH_PPS")
        if bps > 500000:
            dos_reasons.append("DOS_HIGH_BPS")
        if bytes_asymmetry > 0.8:
            dos_reasons.append("DOS_ASYMMETRIC")

        if dos_reasons:
            details = {"total_bytes": total_bytes, "packets_per_second": pps,
                       "bytes_per_second": bps, "bytes_asymmetry": round(bytes_asymmetry, 4)}
            return "dos", dos_reasons, details

        # ── 默认 anomaly ──
        return "anomaly", ["ANOMALY_DEFAULT"], {}

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

        # 基于模式判断告警类型（增强版，附带判定原因）
        alert_type, type_reason = self._determine_type(flows)

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

        # 构建 aggregation（保留原有字段 + 新增维度信息 + 可追溯摘要）
        dimensions = ["src_ip", "dst_target", "service_key", "inferred_type", "time_bucket"]

        # 检测层标签汇总
        from collections import Counter
        det_labels = [
            f.get("features", {}).get("final_label")
            for f in flows
            if f.get("features", {}).get("final_label")
        ]
        detection_summary = {
            "detection_source": type_reason.get("details", {}).get("source") == "detection_layer",
            "detection_labels": dict(Counter(det_labels)) if det_labels else {},
            "guard_triggered": any(
                bool(f.get("features", {}).get("guard_triggers"))
                for f in flows
            ),
        }

        aggregation = {
            "rule": f"src_ip+dst_target+service+type+{self.window_sec}s_window",
            "group_key": group_key,
            "count_flows": len(flows),
            "dimensions": dimensions,
            "composite_score": round(composite_score, 4),
            "score_breakdown": score_breakdown,
            "type_reason": type_reason,  # 类型判定原因（含 reason_codes 和 details）
            "detection_summary": detection_summary,  # 检测层透传摘要
            # 人类可读的可追溯摘要
            "aggregation_summary": self._build_aggregation_summary(group_key, len(flows), dimensions),
            "type_summary": self._build_type_summary(type_reason),
            "severity_summary": self._build_severity_summary(composite_score, score_breakdown, severity),
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
            max_score * COMPOSITE_WEIGHTS["max_score"]
            + flow_density * COMPOSITE_WEIGHTS["flow_density"]
            + duration_factor * COMPOSITE_WEIGHTS["duration_factor"]
            + aggregation_quality * COMPOSITE_WEIGHTS["aggregation_quality"]
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

    def _determine_type(self, flows: list[dict]) -> tuple[str, dict]:
        """
        检测层优先的组级类型判定，启发式兜底。

        优先级：
          1. 汇总组内所有 flow 的 features.final_label，取多数具体攻击类型
          2. 若无具体攻击类型，回退到启发式组级分析
        """
        from collections import Counter

        # 收集检测层标签和原因
        detection_labels: list[str] = []
        detection_reasons: list[str] = []
        for f in flows:
            feat = f.get("features", {})
            label = feat.get("final_label")
            if label and label != "normal":
                detection_labels.append(label)
            reasons = feat.get("rule_reasons")
            if isinstance(reasons, list):
                detection_reasons.extend(reasons)

        # 检测层提供了具体攻击类型（非 anomaly）
        specific = [lbl for lbl in detection_labels if lbl != "anomaly"]
        if specific:
            label_counts = Counter(specific)
            primary = label_counts.most_common(1)[0][0]

            base_details = self._compute_base_details(flows)
            base_details["source"] = "detection_layer"
            base_details["label_distribution"] = dict(label_counts)

            unique_reasons = list(dict.fromkeys(detection_reasons))

            return primary, {
                "type": primary,
                "reason_codes": unique_reasons or [f"DETECTION_{primary.upper()}"],
                "details": base_details,
            }

        # 回退到启发式
        return self._determine_type_heuristic(flows)

    def _compute_base_details(self, flows: list[dict]) -> dict:
        """计算组级基础统计信息（类型判定的共用数据）。"""
        dst_ips = set(f.get("dst_ip") for f in flows)
        dst_ports = set(f.get("dst_port") for f in flows)
        n_flows = len(flows)

        total_syn = sum(f.get("features", {}).get("syn_count", 0) for f in flows)
        total_packets = sum(f.get("features", {}).get("total_packets", 0) for f in flows)
        total_bytes = sum(f.get("features", {}).get("total_bytes", 0) for f in flows)
        syn_ratio = total_syn / max(total_packets, 1)

        avg_handshake = (
            sum(f.get("features", {}).get("handshake_completeness", 1.0) for f in flows)
            / max(n_flows, 1)
        )
        avg_rst_ratio = (
            sum(f.get("features", {}).get("rst_ratio", 0.0) for f in flows)
            / max(n_flows, 1)
        )

        return {
            "unique_dst_ips": len(dst_ips),
            "unique_dst_ports": len(dst_ports),
            "total_flows": n_flows,
            "syn_ratio": round(syn_ratio, 4),
            "total_bytes": total_bytes,
            "total_packets": total_packets,
            "avg_handshake_completeness": round(avg_handshake, 4),
            "avg_rst_ratio": round(avg_rst_ratio, 4),
        }

    def _determine_type_heuristic(self, flows: list[dict]) -> tuple[str, dict]:
        """
        根据流量组模式判定告警类型（启发式），返回 (type, type_reason)。
        type_reason 包含 reason_codes 和 details，用于可解释性。
        当检测层无具体攻击类型标签时，由 _determine_type() 调用此方法作为兜底。
        """
        # ── 聚合统计 ──
        base_details = self._compute_base_details(flows)
        dst_ips = set(f.get("dst_ip") for f in flows)
        dst_ports = set(f.get("dst_port") for f in flows)
        n_flows = len(flows)
        total_packets = base_details["total_packets"]
        total_bytes = base_details["total_bytes"]
        syn_ratio = base_details["syn_ratio"]
        avg_handshake = base_details["avg_handshake_completeness"]
        avg_rst_ratio = base_details["avg_rst_ratio"]
        base_details["source"] = "heuristic"

        # 额外统计（heuristic 特有）
        max_pps = max(
            (f.get("features", {}).get("packets_per_second", 0) for f in flows), default=0
        )
        max_bps = max(
            (f.get("features", {}).get("bytes_per_second", 0) for f in flows), default=0
        )
        avg_asymmetry = (
            sum(f.get("features", {}).get("bytes_asymmetry", 0) for f in flows)
            / max(n_flows, 1)
        )
        short_flow_count = sum(
            1 for f in flows if f.get("features", {}).get("is_short_flow", 0)
        )

        # ── scan 检测（多子类型）──
        scan_reasons: list[str] = []

        # 水平扫描：多目标 IP，少端口
        if len(dst_ips) > 5 and len(dst_ports) <= 3:
            scan_reasons.append("SCAN_HORIZONTAL")

        # 垂直扫描：单目标 IP，多端口
        if len(dst_ips) <= 2 and len(dst_ports) > 10:
            scan_reasons.append("SCAN_VERTICAL")

        # 广泛扫描：多 IP + 多端口
        if len(dst_ips) > 5 and len(dst_ports) > 10:
            scan_reasons.append("SCAN_MULTI_DST_IP")
            scan_reasons.append("SCAN_MULTI_PORT")

        # 通用多目标/多端口（兼容原逻辑，避免重复添加）
        if len(dst_ips) > 5 or len(dst_ports) > 10:
            if not scan_reasons:
                scan_reasons.append(
                    "SCAN_MULTI_DST_IP" if len(dst_ips) > 5 else "SCAN_MULTI_PORT"
                )

        # SYN 扫描特征
        if total_packets > 100 and syn_ratio > 0.5:
            scan_reasons.append("SCAN_SYN_RATIO")

        # 不完整握手（组级）
        if avg_handshake < 0.5 and n_flows > 3:
            scan_reasons.append("SCAN_INCOMPLETE_HANDSHAKE")

        # 高 RST 回复率（目标拒绝连接）
        if avg_rst_ratio > 0.3 and n_flows > 3:
            scan_reasons.append("SCAN_HIGH_RST")

        if scan_reasons:
            # 握手/RST 信号仅作为辅助，需要至少一个主要 scan 指标才判定
            _primary_scan = {"SCAN_HORIZONTAL", "SCAN_VERTICAL", "SCAN_MULTI_DST_IP",
                             "SCAN_MULTI_PORT", "SCAN_SYN_RATIO"}
            if _primary_scan & set(scan_reasons):
                return "scan", {
                    "type": "scan",
                    "reason_codes": scan_reasons,
                    "details": base_details,
                }

        # ── bruteforce 检测 ──
        brute_reasons: list[str] = []
        # 收集组内所有目标端口，取众数作为主要端口
        all_dst_ports = [f.get("dst_port", 0) for f in flows]
        primary_port = max(set(all_dst_ports), key=all_dst_ports.count) if all_dst_ports else 0

        if primary_port in _AUTH_PORTS:
            brute_reasons.append("BRUTE_AUTH_PORT")

        # 重复流模式：多条流到同一认证端口
        if n_flows > 3 and len(dst_ips) <= 2 and primary_port in _AUTH_PORTS:
            brute_reasons.append("BRUTE_REPEATED_FLOWS")

        # 短流占比高
        if n_flows > 3 and short_flow_count / max(n_flows, 1) > 0.5:
            brute_reasons.append("BRUTE_REPEATED_SHORT_FLOWS")

        # 高 RST / 低握手完成度 → 连接被拒绝
        if avg_rst_ratio > 0.3:
            brute_reasons.append("BRUTE_HIGH_RST")
        if avg_handshake < 0.7 and n_flows > 3:
            brute_reasons.append("BRUTE_LOW_HANDSHAKE")

        # 需要端口匹配 + 至少一个行为指标才判定（避免仅凭端口误判）
        if "BRUTE_AUTH_PORT" in brute_reasons and len(brute_reasons) >= 2:
            return "bruteforce", {
                "type": "bruteforce",
                "reason_codes": brute_reasons,
                "details": {**base_details, "primary_port": primary_port,
                            "short_flow_ratio": round(short_flow_count / max(n_flows, 1), 4)},
            }

        # ── dos 检测 ──
        dos_reasons: list[str] = []

        # 流量型
        if total_bytes > 1000000 and len(dst_ips) <= 2:
            dos_reasons.append("DOS_HIGH_VOLUME")

        # 包速率型
        if max_pps > 1000:
            dos_reasons.append("DOS_HIGH_RATE")

        # 带宽速率型
        if max_bps > 1000000:
            dos_reasons.append("DOS_HIGH_BPS")

        # SYN Flood：高 SYN + 低握手 + 单目标
        if syn_ratio > 0.7 and avg_handshake < 0.5 and len(dst_ips) <= 2:
            dos_reasons.append("DOS_SYN_FLOOD")

        # 流量不对称（单向洪泛）
        if avg_asymmetry > 0.8 and total_bytes > 500000:
            dos_reasons.append("DOS_ASYMMETRIC")

        if dos_reasons:
            return "dos", {
                "type": "dos",
                "reason_codes": dos_reasons,
                "details": {**base_details, "max_pps": max_pps, "max_bps": max_bps,
                            "avg_asymmetry": round(avg_asymmetry, 4)},
            }

        # ── 默认 anomaly ──
        return "anomaly", {
            "type": "anomaly",
            "reason_codes": ["ANOMALY_DEFAULT"],
            "details": base_details,
        }

    def _get_top_flows(self, flows: list[dict]) -> list[dict]:
        """获取用于证据展示的高优先级流摘要，含检测层信息。"""
        result = []
        for flow in flows:
            summary = f"{flow.get('proto', 'TCP')}/{flow.get('dst_port', 0)}"
            if flow.get("features", {}).get("syn_count", 0) > 5:
                summary += " SYN burst"

            entry: dict = {
                "flow_id": flow.get("id", ""),
                "anomaly_score": flow.get("anomaly_score", 0),
                "summary": summary,
            }

            # 透传检测层分数（如果可用）
            feat = flow.get("features", {})
            if feat.get("final_score") is not None:
                entry["detection"] = {
                    "baseline_score": feat.get("baseline_score"),
                    "rule_score": feat.get("rule_score"),
                    "graph_score": feat.get("graph_score"),
                    "final_label": feat.get("final_label"),
                    "detection_mode": feat.get("detection_mode"),
                }

            result.append(entry)
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

    # ── 可追溯摘要生成 ──

    @staticmethod
    def _build_aggregation_summary(group_key: str, count_flows: int, dimensions: list[str]) -> str:
        """根据聚合键和维度生成人类可读的聚合依据摘要。"""
        parts = group_key.split("|")
        labels = {
            "src_ip": "源IP",
            "dst_target": "目标",
            "service_key": "服务",
            "inferred_type": "类型",
            "time_bucket": "时间桶",
        }
        segments = []
        for dim, val in zip(dimensions, parts):
            label = labels.get(dim, dim)
            segments.append(f"{label} {val}")
        return f"按 {' + '.join(segments)} 聚合，共 {count_flows} 条流"

    @staticmethod
    def _build_type_summary(type_reason: dict) -> str:
        """根据类型判定原因生成人类可读的类型摘要。"""
        alert_type = type_reason.get("type", "anomaly")
        reason_codes = type_reason.get("reason_codes", [])
        details = type_reason.get("details", {})

        # 类型中文映射
        type_labels = {
            "scan": "扫描",
            "bruteforce": "暴力破解",
            "dos": "拒绝服务",
            "anomaly": "异常行为",
        }
        type_label = type_labels.get(alert_type, alert_type)

        # 根据 reason_codes 构建描述片段
        desc_parts: list[str] = []

        # reason_code 中文映射
        code_labels = {
            "SCAN_HORIZONTAL": "水平扫描(多目标IP少端口)",
            "SCAN_VERTICAL": "垂直扫描(少目标IP多端口)",
            "SCAN_MULTI_DST_IP": "多目标IP",
            "SCAN_MULTI_PORT": "多端口",
            "SCAN_SYN_RATIO": "高SYN比例",
            "SCAN_INCOMPLETE_HANDSHAKE": "不完整握手",
            "SCAN_HIGH_RST": "高RST回复率",
            "BRUTE_AUTH_PORT": "认证端口",
            "BRUTE_REPEATED_FLOWS": "重复连接模式",
            "BRUTE_REPEATED_SHORT_FLOWS": "大量短连接",
            "BRUTE_HIGH_RST": "高RST(连接被拒绝)",
            "BRUTE_LOW_HANDSHAKE": "低握手完成度",
            "DOS_HIGH_VOLUME": "高流量",
            "DOS_HIGH_RATE": "高包速率",
            "DOS_HIGH_BPS": "高带宽",
            "DOS_SYN_FLOOD": "SYN洪泛",
            "DOS_ASYMMETRIC": "流量不对称",
            "ANOMALY_DEFAULT": "未匹配已知攻击模式",
        }
        for code in reason_codes:
            desc_parts.append(code_labels.get(code, code))

        # 补充关键数值
        stats: list[str] = []
        if "unique_dst_ips" in details:
            stats.append(f"{details['unique_dst_ips']}个目标IP")
        if "unique_dst_ports" in details:
            stats.append(f"{details['unique_dst_ports']}个目标端口")
        if "total_flows" in details:
            stats.append(f"{details['total_flows']}条流")
        if "syn_ratio" in details and details["syn_ratio"] > 0:
            stats.append(f"SYN比例{details['syn_ratio']}")

        summary = f"判定为{type_label}：{', '.join(desc_parts)}"
        if stats:
            summary += f"（{', '.join(stats)}）"
        return summary

    @staticmethod
    def _build_severity_summary(
        composite_score: float,
        score_breakdown: dict,
        severity: str,
    ) -> str:
        """根据复合评分和分项明细生成严重度来源摘要。"""
        # 严重度中文映射
        sev_labels = {"critical": "严重", "high": "高", "medium": "中", "low": "低"}
        sev_label = sev_labels.get(severity, severity)

        parts = []
        field_labels = {
            "max_score": ("最高异常分", 0.40),
            "flow_density": ("流密度", 0.25),
            "duration_factor": ("持续时长", 0.20),
            "aggregation_quality": ("聚合质量", 0.15),
        }
        for key, (label, weight) in field_labels.items():
            val = score_breakdown.get(key, 0)
            pct = int(weight * 100)
            parts.append(f"{label}{val}×{pct}%")

        return (
            f"复合评分 {round(composite_score, 4)}（{sev_label}）："
            f"{' + '.join(parts)}"
        )
