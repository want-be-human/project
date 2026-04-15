from app.schemas.decision import (
    DecisionAction,
    RiskProfile,
    RollbackTemplate,
)

# 6 种预定义动作的默认 risk_profile / rollback_template / expected_effect / reversible / recovery_cost
ACTION_REGISTRY: dict[str, dict] = {
    "block_ip": {
        "expected_effect": "阻断指定 IP 的所有入站和出站流量",
        "reversible": True,
        "estimated_recovery_cost": "low",
        "risk_profile": {"disruption_level": "medium", "scope": "single_host"},
        "rollback_template": {
            "action_type": "unblock_ip",
            "params": {},
            "description": "移除针对该 IP 的封锁规则，恢复正常通信",
        },
    },
    "rate_limit": {
        "expected_effect": "对指定服务或 IP 的流量进行速率限制，降低攻击流量但保留基本连通性",
        "reversible": True,
        "estimated_recovery_cost": "low",
        "risk_profile": {"disruption_level": "low", "scope": "service"},
        "rollback_template": {
            "action_type": "remove_rate_limit",
            "params": {},
            "description": "移除速率限制规则，恢复原始带宽",
        },
    },
    "isolate_host": {
        "expected_effect": "将指定主机从网络中完全隔离，阻断所有进出流量",
        "reversible": True,
        "estimated_recovery_cost": "medium",
        "risk_profile": {"disruption_level": "high", "scope": "single_host"},
        "rollback_template": {
            "action_type": "restore_host",
            "params": {},
            "description": "将被隔离主机重新接入网络，恢复所有连接",
        },
    },
    "block_port": {
        "expected_effect": "封锁指定端口的所有流量，阻止特定服务的网络访问",
        "reversible": True,
        "estimated_recovery_cost": "low",
        "risk_profile": {"disruption_level": "medium", "scope": "service"},
        "rollback_template": {
            "action_type": "unblock_port",
            "params": {},
            "description": "重新开放被封锁的端口，恢复服务访问",
        },
    },
    "apply_acl_rule": {
        "expected_effect": "应用访问控制列表规则，细粒度控制流量通行",
        "reversible": True,
        "estimated_recovery_cost": "medium",
        "risk_profile": {"disruption_level": "medium", "scope": "subnet"},
        "rollback_template": {
            "action_type": "remove_acl_rule",
            "params": {},
            "description": "移除已应用的 ACL 规则，恢复原始访问策略",
        },
    },
    "monitor_only": {
        "expected_effect": "仅增加对可疑目标的监控力度，不执行任何阻断操作",
        "reversible": True,
        "estimated_recovery_cost": "none",
        "risk_profile": {"disruption_level": "none", "scope": "single_host"},
        "rollback_template": {
            "action_type": "remove_monitoring",
            "params": {},
            "description": "取消额外的监控配置，恢复正常监控水平",
        },
    },
}

PLAN_ACTION_MAPPING: dict[str, str] = {
    "block_ip": "block_ip",
    "isolate_host": "isolate_host",
    "segment_subnet": "apply_acl_rule",
    "rate_limit_service": "rate_limit",
}

# 侵入性从低到高，用于生成 safer_alternative
ACTION_INVASIVENESS_ORDER: list[str] = [
    "monitor_only",
    "rate_limit",
    "block_port",
    "block_ip",
    "apply_acl_rule",
    "isolate_host",
]


def build_decision_action(
    action_type: str,
    params: dict | None = None,
    confidence: float = 0.5,
    affected_services_count: int = 0,
    affected_nodes_count: int = 0,
) -> DecisionAction:
    registry = ACTION_REGISTRY.get(action_type)
    if not registry:
        # 未知动作类型降级为 monitor_only
        registry = ACTION_REGISTRY["monitor_only"]
        action_type = "monitor_only"

    risk_defaults = registry["risk_profile"]
    risk_profile = RiskProfile(
        disruption_level=risk_defaults["disruption_level"],
        scope=risk_defaults["scope"],
        confidence=confidence,
        affected_services_count=affected_services_count,
        affected_nodes_count=affected_nodes_count,
    )

    rollback_tpl = None
    if registry.get("rollback_template"):
        tpl = registry["rollback_template"]
        rollback_tpl = RollbackTemplate(
            action_type=tpl["action_type"],
            params={**(params or {}), **tpl["params"]},
            description=tpl["description"],
        )

    return DecisionAction(
        action_type=action_type,
        params=params or {},
        expected_effect=registry["expected_effect"],
        risk_profile=risk_profile,
        reversible=registry["reversible"],
        rollback_template=rollback_tpl,
        estimated_recovery_cost=registry["estimated_recovery_cost"],
    )


def get_safer_action_type(current_type: str) -> str:
    """返回比 current_type 侵入性低一级的动作；已是最低则返回 monitor_only。"""
    try:
        idx = ACTION_INVASIVENESS_ORDER.index(current_type)
    except ValueError:
        return "monitor_only"

    if idx <= 0:
        return "monitor_only"
    return ACTION_INVASIVENESS_ORDER[idx - 1]
