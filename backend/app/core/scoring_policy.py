"""
评分策略集中配置。
所有 confidence / severity 相关常量统一在此管理，避免多处硬编码。
"""

# ── 严重等级 → 基础置信度（investigation、plan compiler 共用）──
SEVERITY_BASE: dict[str, float] = {
    "critical": 0.90,
    "high": 0.80,
    "medium": 0.65,
    "low": 0.50,
}

# ── 复合分数 → 严重等级阈值（alerting service）──
SEVERITY_THRESHOLDS: dict[str, float] = {
    "critical": 0.80,
    "high": 0.60,
    "medium": 0.40,
    "low": 0.0,
}

# ── Plan compiler 优先级加成 ──
PRIORITY_BONUS: dict[str, float] = {
    "high": 0.05,
    "medium": 0.00,
    "low": -0.05,
}

# ── 全局置信度上限 ──
CONFIDENCE_CAP: float = 0.95

# ── 复合评分权重（alerting service）──
COMPOSITE_WEIGHTS: dict[str, float] = {
    "max_score": 0.40,
    "flow_density": 0.25,
    "duration_factor": 0.20,
    "aggregation_quality": 0.15,
}
