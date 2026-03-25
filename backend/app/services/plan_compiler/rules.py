"""
PlanCompiler mapping rules.
All rules are deterministic, keyword-based, and auditable.
Inspired by agentic-soc-platform's modular playbook approach:
  research results are structured into actionable, standardized operations.
"""

from typing import Literal

from app.core.scoring_policy import (
    SEVERITY_BASE,
    PRIORITY_BONUS,
    CONFIDENCE_CAP,
)

# -- Action type matching rules --
# Keywords (case-insensitive) -> action_type.
# Order matters: first match wins. None means "skip, not compilable".
ACTION_TYPE_RULES: list[tuple[list[str], str | None]] = [
    # block/firewall -> block_ip
    (["block", "\u5c01\u7981", "ban", "blacklist", "blocklist", "firewall rule",
      "deny", "reject", "drop", "\u62d2\u7edd", "\u4e22\u5f03"], "block_ip"),
    # network segmentation -> segment_subnet (before isolate, title may match both)
    (["segment", "\u5206\u6bb5", "vlan", "micro-segment",
      "partition", "\u5212\u5206", "segregate"], "segment_subnet"),
    # host isolation -> isolate_host
    (["isolat", "\u9694\u79bb", "quarantine",
      "contain", "\u904f\u5236", "restrict", "\u9650\u5236\u8bbf\u95ee"], "isolate_host"),
    # rate limiting -> rate_limit_service
    (["rate limit", "rate-limit", "ratelimit", "\u9650\u6d41", "\u9650\u901f", "\u901f\u7387\u9650\u5236", "throttl",
      "slow down", "cap", "\u63a7\u5236\u901f\u7387"], "rate_limit_service"),
    # non-compilable: monitoring/logging/auth changes -> skip
    (["monitor", "\u76d1\u63a7", "watchlist", "\u65e5\u5fd7", "logging", "alert", "\u544a\u8b66",
      "key-only", "\u5bc6\u94a5", "authentication", "\u8ba4\u8bc1", "audit", "\u5ba1\u8ba1",
      "observe", "\u89c2\u5bdf", "track", "\u8ffd\u8e2a", "review", "\u68c0\u67e5", "inspect", "\u6392\u67e5"], None),
]

COMPILABLE_ACTION_TYPES = {"block_ip", "isolate_host", "segment_subnet", "rate_limit_service"}
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


def match_action_type_with_hint(
    title: str,
    compile_hint: dict | None = None,
) -> tuple[str | None, str]:
    """
    Match action type, preferring compile_hint if present.

    Returns:
        (action_type, match_method) where match_method is "hint", "keyword", or "none".
    """
    if compile_hint and compile_hint.get("preferred_action_type"):
        preferred = compile_hint["preferred_action_type"]
        if preferred in COMPILABLE_ACTION_TYPES:
            return preferred, "hint"

    result = match_action_type(title)
    if result is not None:
        return result, "keyword"

    return None, "none"


# -- Skip reason templates --
SKIP_REASON_TEMPLATES: dict[str, dict[str, str]] = {
    "monitoring": {
        "en": "Monitoring/observability action cannot be compiled into an executable operation",
        "zh": "\u76d1\u63a7/\u53ef\u89c2\u6d4b\u6027\u52a8\u4f5c\u65e0\u6cd5\u7f16\u8bd1\u4e3a\u53ef\u6267\u884c\u64cd\u4f5c",
    },
    "advisory": {
        "en": "Advisory-only recommendation, not suitable for automated execution",
        "zh": "\u4ec5\u4e3a\u5efa\u8bae\u6027\u63a8\u8350\uff0c\u4e0d\u9002\u5408\u81ea\u52a8\u5316\u6267\u884c",
    },
    "no_match": {
        "en": "No compiler rule matched the action title",
        "zh": "\u6ca1\u6709\u7f16\u8bd1\u89c4\u5219\u5339\u914d\u8be5\u52a8\u4f5c\u6807\u9898",
    },
}

SKIP_SUGGESTION_TEMPLATES: dict[str, dict[str, str]] = {
    "monitoring": {
        "en": "This is a monitoring recommendation. Execute manually in your ops workflow.",
        "zh": "\u6b64\u52a8\u4f5c\u4e3a\u76d1\u63a7\u7c7b\u5efa\u8bae\uff0c\u65e0\u9700\u7f16\u8bd1\u3002\u53ef\u5728\u8fd0\u7ef4\u6d41\u7a0b\u4e2d\u624b\u52a8\u6267\u884c\u3002",
    },
    "advisory": {
        "en": "This is an advisory recommendation. Review and act on it manually.",
        "zh": "\u6b64\u52a8\u4f5c\u4e3a\u5efa\u8bae\u7c7b\u63a8\u8350\uff0c\u8bf7\u4eba\u5de5\u5ba1\u9605\u540e\u51b3\u5b9a\u662f\u5426\u6267\u884c\u3002",
    },
    "no_match": {
        "en": "Try re-generating recommendations, or create an action plan manually.",
        "zh": "\u53ef\u5c1d\u8bd5\u91cd\u65b0\u751f\u6210\u5efa\u8bae\uff0c\u6216\u624b\u52a8\u521b\u5efa\u52a8\u4f5c\u8ba1\u5212\u3002",
    },
}


# -- Default params per action type --
PARAMS_DEFAULTS: dict[str, dict] = {
    "block_ip": {"duration_minutes": 60},
    "isolate_host": {"duration_minutes": 120},
    "segment_subnet": {"direction": "both"},
    "rate_limit_service": {"max_connections_per_minute": 10},
}


# -- Rollback mapping --
ROLLBACK_MAPPING: dict[str, tuple[str, dict]] = {
    "block_ip": ("unblock_ip", {}),
    "isolate_host": ("restore_host", {}),
    "segment_subnet": ("unsegment_subnet", {}),
    "rate_limit_service": ("remove_rate_limit", {}),
}


# -- Confidence computation --


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

    if investigation_confidence is not None:
        score = 0.7 * score + 0.3 * investigation_confidence

    return round(max(0.0, min(score, CONFIDENCE_CAP)), 2)
