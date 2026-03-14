"""Stream service for WebSocket broadcasting & EventBus access."""

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
    # Connection manager & broadcast helpers
    "get_connection_manager",
    "broadcast_pcap_progress",
    "broadcast_pcap_done",
    "broadcast_alert_created",
    "broadcast_alert_updated",
    "broadcast_dryrun_created",
    "broadcast_scenario_done",
    # EventBus
    "get_event_bus",
    "DomainEvent",
    "make_event",
    # Event type constants
    "PCAP_PROCESS_PROGRESS",
    "PCAP_PROCESS_DONE",
    "ALERT_CREATED",
    "ALERT_UPDATED",
    "TWIN_DRYRUN_CREATED",
    "SCENARIO_RUN_DONE",
]
