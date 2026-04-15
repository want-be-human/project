"""Layer 2 rule-based scorer. Independent of AlertingService to avoid a circular import."""

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

_AUTH_PORTS = frozenset({
    22, 23, 21, 3389,
    3306, 5432, 1433,
    6379, 27017,
    445, 5900,
})


class RuleEnricher:
    RULE_FEATURE_NAMES: list[str] = [
        "rule_scan_score",
        "rule_is_scan",
        "rule_is_bruteforce",
        "rule_is_dos",
        "rule_auth_port",
        "rule_syn_ratio_high",
        "rule_handshake_low",
        "rule_rst_ratio_high",
        "rule_short_flow",
        "rule_high_pps",
        "rule_high_volume",
        "rule_asymmetric",
        "rule_reason_count",
    ]

    _TYPE_WEIGHTS = {"scan": 0.7, "bruteforce": 0.8, "dos": 0.9, "anomaly": 0.3}

    def __init__(self):
        pass

    def enrich(self, flows: list[dict]) -> list[dict]:
        if not flows:
            return flows

        n = len(flows)

        dst_port = np.zeros(n, dtype=np.int32)
        syn_count = np.zeros(n)
        total_packets = np.zeros(n)
        total_bytes = np.zeros(n)
        rst_ratio = np.zeros(n)
        handshake = np.ones(n)
        is_short = np.zeros(n)
        pps = np.zeros(n)
        bps = np.zeros(n)
        bytes_asym = np.zeros(n)

        for i, flow in enumerate(flows):
            feat = flow.get("features", {})
            dst_port[i] = flow.get("dst_port", 0) or 0
            syn_count[i] = feat.get("syn_count", 0) or 0
            total_packets[i] = feat.get("total_packets", 0) or 0
            total_bytes[i] = feat.get("total_bytes", 0) or 0
            rst_ratio[i] = feat.get("rst_ratio", 0.0) or 0.0
            handshake[i] = feat.get("handshake_completeness", 1.0) or 1.0
            is_short[i] = feat.get("is_short_flow", 0) or 0
            pps[i] = feat.get("packets_per_second", 0) or 0
            bps[i] = feat.get("bytes_per_second", 0) or 0
            bytes_asym[i] = feat.get("bytes_asymmetry", 0) or 0

        syn_ratio = syn_count / np.maximum(total_packets, 1)

        cond_syn_high = syn_ratio > 0.5
        cond_handshake_low = handshake < 0.5
        cond_rst_high = rst_ratio > 0.3
        cond_short = is_short > 0
        cond_auth_port = np.array([p in _AUTH_PORTS for p in dst_port], dtype=bool)
        cond_high_volume = total_bytes > 200000
        cond_high_pps = pps > 1000
        cond_high_bps = bps > 500000
        cond_asym = bytes_asym > 0.8


        scan_score = (
            np.where(cond_syn_high, 2, 0)
            + np.where(cond_handshake_low, 1, 0)
            + np.where(cond_rst_high, 1, 0)
            + np.where(cond_short, 1, 0)
        )
        is_scan = scan_score >= 2
        is_brute = cond_auth_port & ~is_scan
        is_dos = (cond_high_volume | cond_high_pps | cond_high_bps | cond_asym) & ~is_scan & ~is_brute

        type_arr = np.full(n, "anomaly", dtype=object)
        type_arr[is_scan] = "scan"
        type_arr[is_brute] = "bruteforce"
        type_arr[is_dos] = "dos"

        rf_scan_score = np.minimum(scan_score / 5.0, 1.0)
        rf_is_scan = is_scan.astype(float)
        rf_is_brute = is_brute.astype(float)
        rf_is_dos = is_dos.astype(float)
        rf_auth = cond_auth_port.astype(float)
        rf_syn_high = cond_syn_high.astype(float)
        rf_hs_low = cond_handshake_low.astype(float)
        rf_rst_high = cond_rst_high.astype(float)
        rf_short = cond_short.astype(float)
        rf_high_pps = (cond_high_pps | cond_high_bps).astype(float)
        rf_high_vol = cond_high_volume.astype(float)
        rf_asym = cond_asym.astype(float)

        for i, flow in enumerate(flows):
            reasons: list[str] = []
            t = type_arr[i]

            if t == "scan":
                if cond_syn_high[i]: reasons.append("SCAN_SYN_RATIO")
                if cond_handshake_low[i]: reasons.append("SCAN_INCOMPLETE_HANDSHAKE")
                if cond_rst_high[i]: reasons.append("SCAN_HIGH_RST")
                if cond_short[i]: reasons.append("SCAN_SHORT_FLOW")
            elif t == "bruteforce":
                reasons.append("BRUTE_AUTH_PORT")
                if cond_short[i]: reasons.append("BRUTE_SHORT_FLOW")
                if cond_rst_high[i]: reasons.append("BRUTE_HIGH_RST")
                if handshake[i] < 0.7: reasons.append("BRUTE_LOW_HANDSHAKE")
            elif t == "dos":
                if cond_high_volume[i]: reasons.append("DOS_HIGH_VOLUME")
                if cond_high_pps[i]: reasons.append("DOS_HIGH_PPS")
                if cond_high_bps[i]: reasons.append("DOS_HIGH_BPS")
                if cond_asym[i]: reasons.append("DOS_ASYMMETRIC")
            else:
                reasons.append("ANOMALY_DEFAULT")

            base = self._TYPE_WEIGHTS.get(t, 0.3)
            extra = max(len(reasons) - 1, 0)
            rule_score = min(round(base * (1.0 + 0.1 * extra), 4), 1.0)

            det = flow.setdefault("_detection", {})
            det["rule_score"] = rule_score
            det["rule_type"] = t
            det["rule_reasons"] = reasons
            det["rule_features"] = {
                "rule_scan_score": float(rf_scan_score[i]),
                "rule_is_scan": float(rf_is_scan[i]),
                "rule_is_bruteforce": float(rf_is_brute[i]),
                "rule_is_dos": float(rf_is_dos[i]),
                "rule_auth_port": float(rf_auth[i]),
                "rule_syn_ratio_high": float(rf_syn_high[i]),
                "rule_handshake_low": float(rf_hs_low[i]),
                "rule_rst_ratio_high": float(rf_rst_high[i]),
                "rule_short_flow": float(rf_short[i]),
                "rule_high_pps": float(rf_high_pps[i]),
                "rule_high_volume": float(rf_high_vol[i]),
                "rule_asymmetric": float(rf_asym[i]),
                "rule_reason_count": float(len(reasons)),
            }

        logger.info(
            "RuleEnricher 评分完成: %d 条流, max_rule=%.3f",
            n,
            max((f.get("_detection", {}).get("rule_score", 0) for f in flows), default=0),
        )
        return flows
