"""
Core events package — unified internal event bus.

Usage::

    from app.core.events import get_event_bus, DomainEvent, make_event

    bus = get_event_bus()
    await bus.publish(make_event("alert.created", {"alert_id": "...", "severity": "high"}))
"""

from app.core.events.base import EventBus, EventHandler, WILDCARD
from app.core.events.inmemory_bus import InMemoryEventBus
from app.core.events.models import (
    DomainEvent,
    make_event,
    PCAP_PROCESS_PROGRESS,
    PCAP_PROCESS_DONE,
    ALERT_CREATED,
    ALERT_UPDATED,
    TWIN_DRYRUN_CREATED,
    SCENARIO_RUN_DONE,
    ALL_EVENT_TYPES,
)

# ── singleton ────────────────────────────────────────────────────

_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the global EventBus singleton (lazily created)."""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = InMemoryEventBus()
    return _bus_instance


def reset_event_bus() -> None:
    """Reset the singleton — useful for tests."""
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
    "PCAP_PROCESS_PROGRESS",
    "PCAP_PROCESS_DONE",
    "ALERT_CREATED",
    "ALERT_UPDATED",
    "TWIN_DRYRUN_CREATED",
    "SCENARIO_RUN_DONE",
    "ALL_EVENT_TYPES",
]
