"""
复合检测内部数据结构。
定义各层输出和最终检测结果的标准格式。
"""

from dataclasses import dataclass, field


@dataclass
class LayerOutput:
    """单层检测输出。"""
    score: float                                            # 该层评分 0-1
    label: str | None = None                                # 可选标签
    reason_codes: list[str] = field(default_factory=list)   # 判定原因码
    details: dict = field(default_factory=dict)             # 详细信息


@dataclass
class DetectionResult:
    """
    复合检测最终输出（每条 flow 一个）。

    字段契约：
      - baseline_score: Layer 1 IsolationForest 异常分数 (0-1)
      - rule_score: Layer 2 规则评分 (0-1)
      - graph_score: 图特征聚合分数 (0-1)
      - graph_features: 12 维图特征字典
      - final_score: Layer 3 最终分数 (0-1)，已经过 guardrails 修正
      - final_label: 最终标签 ("normal" / "scan" / "bruteforce" / "dos" / "anomaly")
      - rule_type: 规则层推断的攻击类型
      - rule_reasons: 规则层判定原因码列表
      - explanation: 各层贡献度 + 原因汇总 + 保护逻辑信息
      - guard_triggers: 触发的保护逻辑列表
      - model_mode: 推理模式 ("persisted" / "fallback" / "guarded_persisted" / "guarded_fallback")
      - threshold: 使用的分类阈值
      - layer_outputs: 各层原始输出
    """
    baseline_score: float                                   # Layer 1: IF 异常分数 0-1
    rule_score: float                                       # Layer 2: 规则评分 0-1
    graph_score: float = 0.0                                # 图特征聚合分数 0-1
    graph_features: dict = field(default_factory=dict)      # 图特征字典
    final_score: float = 0.0                                # Layer 3: 最终分数 0-1
    final_label: str = "normal"                             # 最终标签
    rule_type: str = "anomaly"                              # 规则层推断类型
    rule_reasons: list[str] = field(default_factory=list)   # 规则层原因码
    explanation: dict = field(default_factory=dict)          # 各层贡献度 + 原因汇总
    guard_triggers: list[str] = field(default_factory=list)  # 保护逻辑触发记录
    model_mode: str = "unknown"                             # 推理模式
    threshold: float = 0.7                                  # 分类阈值
    layer_outputs: dict[str, LayerOutput] = field(default_factory=dict)
