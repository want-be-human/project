"""
Layer 2: 规则增强评分器。
基于可解释规则对每条 flow 进行评分，同时将规则匹配结果编码为数值特征供 Layer 3 使用。
规则逻辑独立实现（不依赖 AlertingService），避免循环依赖。
"""

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── 服务端口语义分类（与 AlertingService 保持一致）──
_AUTH_PORTS = frozenset({
    22, 23, 21, 3389,           # SSH, Telnet, FTP, RDP
    3306, 5432, 1433,           # MySQL, PostgreSQL, MSSQL
    6379, 27017,                # Redis, MongoDB
    445, 5900,                  # SMB, VNC
})


class RuleEnricher:
    """
    基于可解释规则的评分器。
    输出 rule_score（0-1）+ 13 个规则语义特征。
    """

    # 规则语义特征名列表（编码规则匹配结果为数值特征）
    RULE_FEATURE_NAMES: list[str] = [
        "rule_scan_score",          # scan 评分制得分 (0-5 归一化)
        "rule_is_scan",             # 是否命中 scan (0/1)
        "rule_is_bruteforce",       # 是否命中 bruteforce (0/1)
        "rule_is_dos",              # 是否命中 dos (0/1)
        "rule_auth_port",           # 是否为认证端口 (0/1)
        "rule_syn_ratio_high",      # SYN 比例是否偏高 (0/1)
        "rule_handshake_low",       # 握手完成度是否偏低 (0/1)
        "rule_rst_ratio_high",      # RST 比例是否偏高 (0/1)
        "rule_short_flow",          # 是否短流 (0/1)
        "rule_high_pps",            # 是否高 PPS (0/1)
        "rule_high_volume",         # 是否高流量 (0/1)
        "rule_asymmetric",          # 是否不对称 (0/1)
        "rule_reason_count",        # 命中的 reason_code 总数
    ]

    # 各规则类型的基础权重（用于计算 rule_score）
    _TYPE_WEIGHTS: dict[str, float] = {
        "scan": 0.7,
        "bruteforce": 0.8,
        "dos": 0.9,
        "anomaly": 0.3,
    }

    def __init__(self):
        pass

    def enrich(self, flows: list[dict]) -> list[dict]:
        """
        为每条 flow 计算 rule_score 和规则语义特征。

        写入：
            flow["_detection"]["rule_score"]    — 规则评分 0-1
            flow["_detection"]["rule_features"] — 规则语义特征字典
            flow["_detection"]["rule_type"]     — 规则推断类型
            flow["_detection"]["rule_reasons"]  — 规则原因码列表

        参数：
            flows: 包含 features 字段的流字典列表
        返回：
            已填充规则评分和特征的流列表
        """
        if not flows:
            return flows

        for flow in flows:
            rule_score, inferred_type, reason_codes, rule_features = (
                self._score_single_flow(flow)
            )
            det = flow.setdefault("_detection", {})
            det["rule_score"] = rule_score
            det["rule_features"] = rule_features
            det["rule_type"] = inferred_type
            det["rule_reasons"] = reason_codes

        logger.info(
            "RuleEnricher 评分完成: %d 条流, max_rule=%.3f",
            len(flows),
            max((f.get("_detection", {}).get("rule_score", 0) for f in flows), default=0),
        )
        return flows

    def _score_single_flow(self, flow: dict) -> tuple[float, str, list[str], dict]:
        """
        单流规则评分。

        返回：
            (rule_score, inferred_type, reason_codes, rule_feature_dict)
        """
        features = flow.get("features", {})
        dst_port = flow.get("dst_port", 0) or 0

        # ── 提取关键特征值 ──
        syn_count = features.get("syn_count", 0) or 0
        total_packets = features.get("total_packets", 0) or 0
        total_bytes = features.get("total_bytes", 0) or 0
        syn_ratio = syn_count / max(total_packets, 1)
        rst_ratio = features.get("rst_ratio", 0.0) or 0.0
        handshake = features.get("handshake_completeness", 1.0)
        is_short = features.get("is_short_flow", 0) or 0
        pps = features.get("packets_per_second", 0) or 0
        bps = features.get("bytes_per_second", 0) or 0
        bytes_asymmetry = features.get("bytes_asymmetry", 0) or 0

        # ── 初始化规则语义特征 ──
        rf: dict[str, float] = {name: 0.0 for name in self.RULE_FEATURE_NAMES}

        reason_codes: list[str] = []

        # ── scan 判定：评分制，≥2 分命中 ──
        scan_score = 0
        if syn_ratio > 0.5:
            scan_score += 2
            reason_codes.append("SCAN_SYN_RATIO")
            rf["rule_syn_ratio_high"] = 1.0
        if handshake < 0.5:
            scan_score += 1
            reason_codes.append("SCAN_INCOMPLETE_HANDSHAKE")
            rf["rule_handshake_low"] = 1.0
        if rst_ratio > 0.3:
            scan_score += 1
            reason_codes.append("SCAN_HIGH_RST")
            rf["rule_rst_ratio_high"] = 1.0
        if is_short:
            scan_score += 1
            reason_codes.append("SCAN_SHORT_FLOW")
            rf["rule_short_flow"] = 1.0

        rf["rule_scan_score"] = min(scan_score / 5.0, 1.0)  # 归一化到 0-1

        if scan_score >= 2:
            rf["rule_is_scan"] = 1.0
            rf["rule_reason_count"] = float(len(reason_codes))
            rule_score = self._compute_rule_score("scan", reason_codes)
            return rule_score, "scan", reason_codes, rf

        # ── bruteforce 判定：认证端口语义 ──
        is_auth = dst_port in _AUTH_PORTS
        if is_auth:
            rf["rule_auth_port"] = 1.0
            reason_codes.append("BRUTE_AUTH_PORT")
            if is_short:
                reason_codes.append("BRUTE_SHORT_FLOW")
                rf["rule_short_flow"] = 1.0
            if rst_ratio > 0.3:
                reason_codes.append("BRUTE_HIGH_RST")
                rf["rule_rst_ratio_high"] = 1.0
            if handshake < 0.7:
                reason_codes.append("BRUTE_LOW_HANDSHAKE")
                rf["rule_handshake_low"] = 1.0

            rf["rule_is_bruteforce"] = 1.0
            rf["rule_reason_count"] = float(len(reason_codes))
            rule_score = self._compute_rule_score("bruteforce", reason_codes)
            return rule_score, "bruteforce", reason_codes, rf

        # ── dos 判定：流量/速率多维度 ──
        dos_reasons: list[str] = []
        if total_bytes > 200000:
            dos_reasons.append("DOS_HIGH_VOLUME")
            rf["rule_high_volume"] = 1.0
        if pps > 1000:
            dos_reasons.append("DOS_HIGH_PPS")
            rf["rule_high_pps"] = 1.0
        if bps > 500000:
            dos_reasons.append("DOS_HIGH_BPS")
            rf["rule_high_pps"] = 1.0  # 复用高速率标记
        if bytes_asymmetry > 0.8:
            dos_reasons.append("DOS_ASYMMETRIC")
            rf["rule_asymmetric"] = 1.0

        if dos_reasons:
            reason_codes.extend(dos_reasons)
            rf["rule_is_dos"] = 1.0
            rf["rule_reason_count"] = float(len(reason_codes))
            rule_score = self._compute_rule_score("dos", reason_codes)
            return rule_score, "dos", reason_codes, rf

        # ── 默认 anomaly ──
        reason_codes.append("ANOMALY_DEFAULT")
        rf["rule_reason_count"] = float(len(reason_codes))
        rule_score = self._compute_rule_score("anomaly", reason_codes)
        return rule_score, "anomaly", reason_codes, rf

    def _compute_rule_score(self, inferred_type: str, reason_codes: list[str]) -> float:
        """
        基于推断类型和命中规则数量计算 rule_score。

        公式：base_weight × (1 + 0.1 × extra_reasons)，上限 1.0
        """
        base = self._TYPE_WEIGHTS.get(inferred_type, 0.3)
        # 额外原因码数量加成（第一个原因码已包含在 base 中）
        extra = max(len(reason_codes) - 1, 0)
        score = base * (1.0 + 0.1 * extra)
        return min(round(score, 4), 1.0)
