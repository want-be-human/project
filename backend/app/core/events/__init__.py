"""
统一内部事件总线。
用法:

    from app.core.events import get_event_bus, DomainEvent, make_event

    bus = get_event_bus()
    await bus.publish(make_event("alert.created", {"alert_id": "...", "severity": "high"}))
"""

from app.core.events.base import EventBus, EventHandler, WILDCARD
from app.core.events.inmemory_bus import InMemoryEventBus
from app.core.events.models import (
    DomainEvent,
    make_event,
    # PCAP 处理事件
    PCAP_PROCESS_PROGRESS,
    PCAP_PROCESS_DONE,
    PCAP_PROCESS_FAILED,
    # 告警事件
    ALERT_CREATED,
    ALERT_UPDATED,
    # 数字孪生事件
    TWIN_DRYRUN_CREATED,
    # 场景运行事件
    SCENARIO_RUN_DONE,
    SCENARIO_RUN_STARTED,
    SCENARIO_STAGE_STARTED,
    SCENARIO_STAGE_COMPLETED,
    SCENARIO_STAGE_FAILED,
    SCENARIO_RUN_PROGRESS,
    # 流水线可观测性事件
    PIPELINE_RUN_STARTED,
    PIPELINE_STAGE_COMPLETED,
    PIPELINE_STAGE_FAILED,
    PIPELINE_RUN_DONE,
    ALL_EVENT_TYPES,
)

# 单例

_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    """返回全局 EventBus 单例（按需懒加载）。"""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = InMemoryEventBus()
    return _bus_instance


def reset_event_bus() -> None:
    """重置单例（便于测试）。"""
    global _bus_instance
    _bus_instance = None


__all__ = [
    "EventBus",
    "EventHandler",
    "InMemoryEventBus",
    "DomainEvent",
    "make_event",
    "get_event_bus",
    "reset_event_bus",
    "WILDCARD",
    # PCAP 处理事件
    "PCAP_PROCESS_PROGRESS",
    "PCAP_PROCESS_DONE",
    "PCAP_PROCESS_FAILED",
    # 告警事件
    "ALERT_CREATED",
    "ALERT_UPDATED",
    # 数字孪生事件
    "TWIN_DRYRUN_CREATED",
    # 场景运行事件
    "SCENARIO_RUN_DONE",
    "SCENARIO_RUN_STARTED",
    "SCENARIO_STAGE_STARTED",
    "SCENARIO_STAGE_COMPLETED",
    "SCENARIO_STAGE_FAILED",
    "SCENARIO_RUN_PROGRESS",
    # 流水线可观测性事件
    "PIPELINE_RUN_STARTED",
    "PIPELINE_STAGE_COMPLETED",
    "PIPELINE_STAGE_FAILED",
    "PIPELINE_RUN_DONE",
    "ALL_EVENT_TYPES",
]
