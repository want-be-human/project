from dataclasses import dataclass, field


@dataclass
class LayerOutput:
    score: float
    label: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class DetectionResult:
    baseline_score: float
    rule_score: float
    graph_score: float = 0.0
    graph_features: dict = field(default_factory=dict)
    final_score: float = 0.0
    final_label: str = "normal"
    rule_type: str = "anomaly"
    rule_reasons: list[str] = field(default_factory=list)
    explanation: dict = field(default_factory=dict)
    guard_triggers: list[str] = field(default_factory=list)
    model_mode: str = "unknown"
    threshold: float = 0.7
    layer_outputs: dict[str, LayerOutput] = field(default_factory=dict)
