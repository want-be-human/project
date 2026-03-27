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

# ══════════════════════════════════════════════════════════════
# Dry-Run 影响评估配置（数据驱动评分）
# ══════════════════════════════════════════════════════════════

# ── 服务重要性权重（替代硬编码 critical_services）──
SERVICE_IMPORTANCE: dict[str, float] = {
    "tcp/22":   0.85,   # SSH
    "tcp/443":  0.90,   # HTTPS
    "tcp/80":   0.75,   # HTTP
    "tcp/3389": 0.80,   # RDP
    "tcp/3306": 0.70,   # MySQL
    "tcp/5432": 0.70,   # PostgreSQL
    "udp/53":   0.85,   # DNS
    "tcp/25":   0.50,   # SMTP
    "tcp/8080": 0.55,   # HTTP-alt
}
# 未列出服务的默认重要性
SERVICE_IMPORTANCE_DEFAULT: float = 0.30

# ── 服务中断风险复合权重（各子分数加权求和）──
DISRUPTION_RISK_WEIGHTS: dict[str, float] = {
    "weighted_service":    0.25,  # 加权服务重要性
    "node_impact":         0.15,  # 受影响节点占比
    "edge_impact":         0.20,  # 受影响边占比
    "alert_severity":      0.20,  # 告警严重等级
    "traffic_proportion":  0.15,  # 流量占比
    "historical":          0.05,  # 历史演练/场景
}

# ── 告警严重等级 → 风险权重（用于 alert_severity_score 计算）──
ALERT_SEVERITY_RISK: dict[str, float] = {
    "critical": 1.0,
    "high":     0.8,
    "medium":   0.5,
    "low":      0.2,
}

# ── 可达性分析采样上限（避免大图 O(n²) 爆炸）──
REACHABILITY_PAIR_SAMPLE_LIMIT: int = 200

# ── 影响评估置信度 ──
IMPACT_CONFIDENCE_BASE: float = 0.60
IMPACT_CONFIDENCE_CAP: float = 0.95
