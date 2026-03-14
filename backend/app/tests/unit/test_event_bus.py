"""
Unit tests for the internal EventBus infrastructure.

Covers:
- InMemoryEventBus publish / subscribe / unsubscribe
- Wildcard (*) subscription
- Exception isolation between handlers
- DomainEvent model serialisation & immutability
"""

import asyncio
import pytest
from unittest.mock import AsyncMock

from app.core.events import (
    InMemoryEventBus,
    DomainEvent,
    make_event,
    get_event_bus,
    reset_event_bus,
    WILDCARD,
    PCAP_PROCESS_PROGRESS,
    PCAP_PROCESS_DONE,
    ALERT_CREATED,
    ALERT_UPDATED,
    TWIN_DRYRUN_CREATED,
    SCENARIO_RUN_DONE,
    ALL_EVENT_TYPES,
)


# ── fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def bus():
    return InMemoryEventBus()


@pytest.fixture(autouse=True)
def _reset_bus():
    """Ensure global singleton is fresh for every test."""
    reset_event_bus()
    yield
    reset_event_bus()


# ── DomainEvent model tests ─────────────────────────────────────

class TestDomainEvent:
    def test_make_event_creates_valid_event(self):
        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        assert event.event_type == "alert.created"
        assert event.data == {"alert_id": "a1", "severity": "high"}
        assert event.event_id  # non-empty UUID
        assert event.timestamp is not None

    def test_event_is_immutable(self):
        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        with pytest.raises(Exception):
            event.event_type = "other"  # type: ignore[misc]

    def test_event_type_constants_match_ws_names(self):
        """Event type constants must exactly match existing WS event names."""
        assert PCAP_PROCESS_PROGRESS == "pcap.process.progress"
        assert PCAP_PROCESS_DONE == "pcap.process.done"
        assert ALERT_CREATED == "alert.created"
        assert ALERT_UPDATED == "alert.updated"
        assert TWIN_DRYRUN_CREATED == "twin.dryrun.created"
        assert SCENARIO_RUN_DONE == "scenario.run.done"

    def test_all_event_types_list(self):
        assert len(ALL_EVENT_TYPES) == 6


# ── InMemoryEventBus core tests ─────────────────────────────────

class TestInMemoryEventBus:
    @pytest.mark.asyncio
    async def test_publish_to_subscriber(self, bus: InMemoryEventBus):
        handler = AsyncMock()
        await bus.subscribe(ALERT_CREATED, handler)

        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        await bus.publish(event)

        handler.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_no_cross_topic_delivery(self, bus: InMemoryEventBus):
        handler = AsyncMock()
        await bus.subscribe(ALERT_CREATED, handler)

        event = make_event(PCAP_PROCESS_DONE, {"pcap_id": "p1", "flow_count": 10, "alert_count": 2})
        await bus.publish(event)

        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_topic(self, bus: InMemoryEventBus):
        h1 = AsyncMock()
        h2 = AsyncMock()
        await bus.subscribe(ALERT_CREATED, h1)
        await bus.subscribe(ALERT_CREATED, h2)

        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "low"})
        await bus.publish(event)

        h1.assert_awaited_once_with(event)
        h2.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_handler(self, bus: InMemoryEventBus):
        handler = AsyncMock()
        await bus.subscribe(ALERT_CREATED, handler)
        await bus.unsubscribe(ALERT_CREATED, handler)

        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        await bus.publish(event)

        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unsubscribe_non_existent_handler_is_noop(self, bus: InMemoryEventBus):
        """Unsubscribing a handler that was never registered should not raise."""
        handler = AsyncMock()
        await bus.unsubscribe(ALERT_CREATED, handler)  # should not raise

    @pytest.mark.asyncio
    async def test_duplicate_subscribe_ignored(self, bus: InMemoryEventBus):
        handler = AsyncMock()
        await bus.subscribe(ALERT_CREATED, handler)
        await bus.subscribe(ALERT_CREATED, handler)  # duplicate

        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        await bus.publish(event)

        # Should be called only once despite double-subscribe
        handler.assert_awaited_once_with(event)


# ── Wildcard subscription tests ──────────────────────────────────

class TestWildcardSubscription:
    @pytest.mark.asyncio
    async def test_wildcard_receives_all_events(self, bus: InMemoryEventBus):
        handler = AsyncMock()
        await bus.subscribe(WILDCARD, handler)

        for etype in ALL_EVENT_TYPES:
            await bus.publish(make_event(etype, {"test": True}))

        assert handler.await_count == len(ALL_EVENT_TYPES)

    @pytest.mark.asyncio
    async def test_wildcard_and_specific_both_called(self, bus: InMemoryEventBus):
        wild = AsyncMock()
        specific = AsyncMock()
        await bus.subscribe(WILDCARD, wild)
        await bus.subscribe(ALERT_CREATED, specific)

        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        await bus.publish(event)

        wild.assert_awaited_once_with(event)
        specific.assert_awaited_once_with(event)


# ── Exception isolation tests ────────────────────────────────────

class TestExceptionIsolation:
    @pytest.mark.asyncio
    async def test_failing_handler_does_not_break_others(self, bus: InMemoryEventBus):
        failing = AsyncMock(side_effect=RuntimeError("boom"))
        ok = AsyncMock()
        await bus.subscribe(ALERT_CREATED, failing)
        await bus.subscribe(ALERT_CREATED, ok)

        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        await bus.publish(event)  # should NOT raise

        ok.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_failing_wildcard_does_not_break_specific(self, bus: InMemoryEventBus):
        failing_wild = AsyncMock(side_effect=ValueError("wild fail"))
        specific = AsyncMock()
        await bus.subscribe(WILDCARD, failing_wild)
        await bus.subscribe(ALERT_CREATED, specific)

        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        await bus.publish(event)

        specific.assert_awaited_once_with(event)


# ── Singleton factory tests ──────────────────────────────────────

class TestGetEventBus:
    def test_returns_same_instance(self):
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_clears_singleton(self):
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2

    def test_is_inmemory_by_default(self):
        bus = get_event_bus()
        assert isinstance(bus, InMemoryEventBus)
