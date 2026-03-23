"""
PlanCompiler mapping rules.
All rules are deterministic, keyword-based, and auditable.
Inspired by agentic-soc-platform's modular playbook approach:
  research results are structured into actionable, standardized operations.
"""

from typing import Literal

# ── Action 类型匹配 ───────────────────────────────────────────────
# 关键字（不区分大小写）→ action_type。
# 顺序敏感：先匹配先命中。None 表示“跳过，不可编译”。
ACTION_TYPE_RULES: list[tuple[list[str], str | None]] = [
    # 封禁/防火墙规则 → block_ip
    (["block", "封禁", "ban", "blacklist", "blocklist", "firewall rule"], "block_ip"),
    # 网络分段 → segment_subnet（优先于 isolate，因为标题可能同时命中）
    (["segment", "分段", "vlan", "micro-segment"], "segment_subnet"),
    # 主机隔离 → isolate_host
    (["isolat", "隔离", "quarantine"], "isolate_host"),
    # 限流 → rate_limit_service
    (["rate limit", "rate-limit", "ratelimit", "限流", "限速", "速率限制", "throttl"], "rate_limit_service"),
    # 不可编译项：监控/日志/认证类变更 → skip
    (["monitor", "监控", "watchlist", "日志", "logging", "alert", "告警",
      "key-only", "密钥", "authentication", "认证", "audit", "审计"], None),
]

CompilableActionType = Literal["block_ip", "isolate_host", "segment_subnet", "rate_limit_service"]


def match_action_type(title: str) -> str | None:
    """
    Match a RecommendedAction title to a PlanAction action_type.

    Returns:
        action_type string if compilable, None if the action should be skipped.
    """
    lower = title.lower()
    for keywords, action_type in ACTION_TYPE_RULES:
        for kw in keywords:
            if kw in lower:
                return action_type
    return None


# ── 各 action 类型默认参数 ─────────────────────────────────────────
PARAMS_DEFAULTS: dict[str, dict] = {
    "block_ip": {"duration_minutes": 60},
    "isolate_host": {"duration_minutes": 120},
    "segment_subnet": {"direction": "both"},
    "rate_limit_service": {"max_connections_per_minute": 10},
}


# ── 回滚映射 ───────────────────────────────────────────────────────
ROLLBACK_MAPPING: dict[str, tuple[str, dict]] = {
    "block_ip": ("unblock_ip", {}),
    "isolate_host": ("restore_host", {}),
    "segment_subnet": ("unsegment_subnet", {}),
    "rate_limit_service": ("remove_rate_limit", {}),
}


# ── 置信度计算 ─────────────────────────────────────────────────────
SEVERITY_BASE: dict[str, float] = {
    "critical": 0.90,
    "high": 0.80,
    "medium": 0.65,
    "low": 0.50,
}

PRIORITY_BONUS: dict[str, float] = {
    "high": 0.05,
    "medium": 0.00,
    "low": -0.05,
}


def compute_confidence(
    severity: str,
    priority: str,
    evidence_node_count: int = 0,
    investigation_confidence: float | None = None,
) -> float:
    """
    Compute a deterministic confidence score for a compiled action.

    Formula:
        base(severity) + bonus(priority) + min(evidence_nodes * 0.01, 0.05)
        Then blend with investigation confidence if available.
    """
    base = SEVERITY_BASE.get(severity, 0.50)
    bonus = PRIORITY_BONUS.get(priority, 0.00)
    evidence_bonus = min(evidence_node_count * 0.01, 0.05)

    score = base + bonus + evidence_bonus

    # 若 investigation 含有置信度，则参与加权
    if investigation_confidence is not None:
        score = 0.7 * score + 0.3 * investigation_confidence

    return round(max(0.0, min(score, 0.95)), 2)
