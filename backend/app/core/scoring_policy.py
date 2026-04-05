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

# ══════════════════════════════════════════════════════════════
# 复合检测架构权重配置
# ══════════════════════════════════════════════════════════════

# Layer 3 fallback 模式加权融合权重（无监督模型时使用）
COMPOSITE_DETECTION_WEIGHTS: dict[str, float] = {
    "baseline_score": 0.50,
    "rule_score": 0.35,
    "graph_score": 0.15,
}

# 复合检测阈值
COMPOSITE_DETECTION_THRESHOLDS: dict[str, float] = {
    "anomaly_threshold": 0.7,       # final_score >= 此值视为异常
    "rule_score_threshold": 0.5,    # rule_score >= 此值视为规则命中
    "baseline_high": 0.8,           # baseline_score 高异常阈值
}

# ══════════════════════════════════════════════════════════════
# 复合检测 Guardrails（保护逻辑）
# ══════════════════════════════════════════════════════════════

# 强规则类型：这些类型不应被监督模型完全压制为 normal
STRONG_RULE_TYPES: frozenset[str] = frozenset({"scan", "bruteforce", "dos"})

# Guard 1: 规则分数下限保护
# 当 rule_score >= threshold 且 rule_type 为强类型时,
# final_score 不得低于 rule_score × factor。
# 仅在 rule_score 较高时触发，避免低置信度规则产生误报
GUARD_RULE_FLOOR_THRESHOLD: float = 0.7    # rule_score >= 此值时触发下限保护
GUARD_RULE_FLOOR_FACTOR: float = 0.95      # floor = rule_score × 此系数

# Guard 2: 多源一致性保护
# 当 baseline 和 rule/graph 同时高时, final_score 不得低于 consensus_floor。
# 要求双源都达到较高水平才触发，减少单源误报传导
GUARD_CONSENSUS_BASELINE: float = 0.8      # baseline_score >= 此值时检查一致性
GUARD_CONSENSUS_SECONDARY: float = 0.5     # rule/graph 中较高者 >= 此值时触发
GUARD_CONSENSUS_FLOOR: float = 0.7         # 一致性触发时的 final_score 下限
