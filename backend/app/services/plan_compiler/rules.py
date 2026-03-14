"""
PlanCompiler mapping rules.
All rules are deterministic, keyword-based, and auditable.
Inspired by agentic-soc-platform's modular playbook approach:
  research results are structured into actionable, standardized operations.
"""

from typing import Literal

# ── Action type matching ───────────────────────────────────────────
# Keywords (case-insensitive) → action_type.
# Order matters: first match wins. None means "skip, not compilable".
ACTION_TYPE_RULES: list[tuple[list[str], str | None]] = [
    # Blocking / firewall rules → block_ip
    (["block", "封禁", "ban", "blacklist", "blocklist", "firewall rule"], "block_ip"),
    # Network segmentation → segment_subnet (before isolate, since titles may contain both)
    (["segment", "分段", "vlan", "micro-segment"], "segment_subnet"),
    # Host isolation → isolate_host
    (["isolat", "隔离", "quarantine"], "isolate_host"),
    # Rate limiting → rate_limit_service
    (["rate limit", "rate-limit", "ratelimit", "限流", "限速", "速率限制", "throttl"], "rate_limit_service"),
    # Non-compilable: monitoring / logging / auth changes → skip
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


# ── Default params per action type ─────────────────────────────────
PARAMS_DEFAULTS: dict[str, dict] = {
    "block_ip": {"duration_minutes": 60},
    "isolate_host": {"duration_minutes": 120},
    "segment_subnet": {"direction": "both"},
    "rate_limit_service": {"max_connections_per_minute": 10},
}


# ── Rollback mapping ──────────────────────────────────────────────
ROLLBACK_MAPPING: dict[str, tuple[str, dict]] = {
    "block_ip": ("unblock_ip", {}),
    "isolate_host": ("restore_host", {}),
    "segment_subnet": ("unsegment_subnet", {}),
    "rate_limit_service": ("remove_rate_limit", {}),
}


# ── Confidence calculation ─────────────────────────────────────────
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

    # If investigation has its own confidence, weight it in
    if investigation_confidence is not None:
        score = 0.7 * score + 0.3 * investigation_confidence

    return round(max(0.0, min(score, 0.95)), 2)
