"""评分策略集中配置：confidence / severity 相关常量统一管理。"""

# 严重等级 → 基础置信度（investigation、plan compiler 共用）
SEVERITY_BASE: dict[str, float] = {
    "critical": 0.90,
    "high": 0.80,
    "medium": 0.65,
    "low": 0.50,
}

# 复合分数 → 严重等级阈值（alerting service）
SEVERITY_THRESHOLDS: dict[str, float] = {
    "critical": 0.80,
    "high": 0.60,
    "medium": 0.40,
    "low": 0.0,
}

# Plan compiler 优先级加成
PRIORITY_BONUS: dict[str, float] = {
    "high": 0.05,
    "medium": 0.00,
    "low": -0.05,
}

CONFIDENCE_CAP: float = 0.95

# 复合评分权重（alerting service）
COMPOSITE_WEIGHTS: dict[str, float] = {
    "max_score": 0.40,
    "flow_density": 0.25,
    "duration_factor": 0.20,
    "aggregation_quality": 0.15,
}

# Dry-Run 影响评估 

# 服务重要性权重
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
SERVICE_IMPORTANCE_DEFAULT: float = 0.30

# 服务中断风险复合权重（各子分数加权求和）
DISRUPTION_RISK_WEIGHTS: dict[str, float] = {
    "weighted_service":    0.25,
    "node_impact":         0.15,
    "edge_impact":         0.20,
    "alert_severity":      0.20,
    "traffic_proportion":  0.15,
    "historical":          0.05,
}

# 告警严重等级风险权重
ALERT_SEVERITY_RISK: dict[str, float] = {
    "critical": 1.0,
    "high":     0.8,
    "medium":   0.5,
    "low":      0.2,
}

# 可达性分析采样上限
REACHABILITY_PAIR_SAMPLE_LIMIT: int = 200

IMPACT_CONFIDENCE_BASE: float = 0.60
IMPACT_CONFIDENCE_CAP: float = 0.95

# 复合检测架构权重

# Layer 3 fallback 加权融合
COMPOSITE_DETECTION_WEIGHTS: dict[str, float] = {
    "baseline_score": 0.50,
    "rule_score": 0.35,
    "graph_score": 0.15,
}

COMPOSITE_DETECTION_THRESHOLDS: dict[str, float] = {
    "anomaly_threshold": 0.7,
    "rule_score_threshold": 0.5,
    "baseline_high": 0.8,
}

# 复合检测 Guardrails

STRONG_RULE_TYPES: frozenset[str] = frozenset({"scan", "bruteforce", "dos"})

# Guard 1: rule_score >= threshold 且 rule_type 为强类型时, final_score >= rule_score × factor
GUARD_RULE_FLOOR_THRESHOLD: float = 0.7
GUARD_RULE_FLOOR_FACTOR: float = 0.95

# Guard 2: baseline 与 rule/graph 双高时, final_score >= consensus_floor
GUARD_CONSENSUS_BASELINE: float = 0.8
GUARD_CONSENSUS_SECONDARY: float = 0.5
GUARD_CONSENSUS_FLOOR: float = 0.7
