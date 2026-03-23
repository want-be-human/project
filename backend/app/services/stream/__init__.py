"""用于 WebSocket 广播与 EventBus 访问的流式服务。"""

from app.api.routers.stream import (
    get_connection_manager,
    broadcast_pcap_progress,
    broadcast_pcap_done,
    broadcast_alert_created,
    broadcast_alert_updated,
    broadcast_dryrun_created,
    broadcast_scenario_done,
)
from app.core.events import (
    get_event_bus,
    DomainEvent,
    make_event,
    PCAP_PROCESS_PROGRESS,
    PCAP_PROCESS_DONE,
    ALERT_CREATED,
    ALERT_UPDATED,
    TWIN_DRYRUN_CREATED,
    SCENARIO_RUN_DONE,
)

__all__ = [
    # 连接管理器与广播辅助函数
    "get_connection_manager",
    "broadcast_pcap_progress",
    "broadcast_pcap_done",
    "broadcast_alert_created",
    "broadcast_alert_updated",
    "broadcast_dryrun_created",
    "broadcast_scenario_done",
    # 事件总线
    "get_event_bus",
    "DomainEvent",
    "make_event",
    # 事件类型常量
    "PCAP_PROCESS_PROGRESS",
    "PCAP_PROCESS_DONE",
    "ALERT_CREATED",
    "ALERT_UPDATED",
    "TWIN_DRYRUN_CREATED",
    "SCENARIO_RUN_DONE",
]
