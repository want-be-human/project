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
    """复合检测最终输出（每条 flow 一个）。"""
    baseline_score: float                                   # Layer 1: IF 异常分数 0-1
    rule_score: float                                       # Layer 2: 规则评分 0-1
    graph_features: dict = field(default_factory=dict)      # 图特征字典
    final_score: float = 0.0                                # Layer 3: 最终分数 0-1
    final_label: str = "normal"                             # 最终标签
    explanation: dict = field(default_factory=dict)          # 各层贡献度 + 原因汇总
    layer_outputs: dict[str, LayerOutput] = field(default_factory=dict)
