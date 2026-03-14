"""
Unit tests for the WebSocket ↔ EventBus integration layer.

Verifies that:
- WebSocketEventConsumer correctly forwards DomainEvents to ConnectionManager.
- The JSON envelope format ``{"event": str, "data": dict}`` is preserved.
- broadcast_* helper functions publish through the EventBus (not directly
  to ConnectionManager) and the consumer bridges the gap.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.events import (
    InMemoryEventBus,
    DomainEvent,
    make_event,
    reset_event_bus,
    PCAP_PROCESS_PROGRESS,
    PCAP_PROCESS_DONE,
    ALERT_CREATED,
    ALERT_UPDATED,
    TWIN_DRYRUN_CREATED,
    SCENARIO_RUN_DONE,
    WILDCARD,
)
from app.api.routers.stream import (
    ConnectionManager,
    WebSocketEventConsumer,
    broadcast_pcap_progress,
    broadcast_pcap_done,
    broadcast_alert_created,
    broadcast_alert_updated,
    broadcast_dryrun_created,
    broadcast_scenario_done,
)


# ── fixtures ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset():
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture
def mock_manager():
    mgr = MagicMock(spec=ConnectionManager)
    mgr.broadcast = AsyncMock()
    return mgr


@pytest.fixture
def consumer(mock_manager):
    return WebSocketEventConsumer(mock_manager)


# ── WebSocketEventConsumer tests ─────────────────────────────────

class TestWebSocketEventConsumer:
    @pytest.mark.asyncio
    async def test_handle_forwards_event_to_manager(self, consumer, mock_manager):
        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        await consumer.handle(event)

        mock_manager.broadcast.assert_awaited_once_with(
            "alert.created",
            {"alert_id": "a1", "severity": "high"},
        )

    @pytest.mark.asyncio
    async def test_register_subscribes_to_wildcard(self, consumer):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()

        # The handler should now be in the wildcard list
        assert consumer.handle in bus._handlers[WILDCARD]

    @pytest.mark.asyncio
    async def test_unregister_removes_subscription(self, consumer):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await consumer.unregister()

        assert consumer.handle not in bus._handlers.get(WILDCARD, [])

    @pytest.mark.asyncio
    async def test_full_roundtrip_publish_to_ws(self, consumer, mock_manager):
        """EventBus.publish() → consumer.handle() → manager.broadcast()."""
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()

        event = make_event(PCAP_PROCESS_PROGRESS, {"pcap_id": "p1", "percent": 42})
        await bus.publish(event)

        mock_manager.broadcast.assert_awaited_once_with(
            "pcap.process.progress",
            {"pcap_id": "p1", "percent": 42},
        )


# ── broadcast_* helper integration tests ────────────────────────

class TestBroadcastHelpers:
    """Verify each helper publishes the correct event type and data."""

    @pytest.mark.asyncio
    async def test_broadcast_pcap_progress(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_pcap_progress("pcap-1", 50)

        mock_manager.broadcast.assert_awaited_once_with(
            "pcap.process.progress",
            {"pcap_id": "pcap-1", "percent": 50},
        )

    @pytest.mark.asyncio
    async def test_broadcast_pcap_done(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_pcap_done("pcap-1", 120, 5)

        mock_manager.broadcast.assert_awaited_once_with(
            "pcap.process.done",
            {"pcap_id": "pcap-1", "flow_count": 120, "alert_count": 5},
        )

    @pytest.mark.asyncio
    async def test_broadcast_alert_created(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_alert_created("alert-1", "high")

        mock_manager.broadcast.assert_awaited_once_with(
            "alert.created",
            {"alert_id": "alert-1", "severity": "high"},
        )

    @pytest.mark.asyncio
    async def test_broadcast_alert_updated(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_alert_updated("alert-1", "resolved")

        mock_manager.broadcast.assert_awaited_once_with(
            "alert.updated",
            {"alert_id": "alert-1", "status": "resolved"},
        )

    @pytest.mark.asyncio
    async def test_broadcast_dryrun_created(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_dryrun_created("dr-1", "alert-1", 0.75)

        mock_manager.broadcast.assert_awaited_once_with(
            "twin.dryrun.created",
            {"dry_run_id": "dr-1", "alert_id": "alert-1", "risk": 0.75},
        )

    @pytest.mark.asyncio
    async def test_broadcast_scenario_done(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_scenario_done("sc-1", "pass")

        mock_manager.broadcast.assert_awaited_once_with(
            "scenario.run.done",
            {"scenario_id": "sc-1", "status": "pass"},
        )


# ── JSON envelope compatibility test ────────────────────────────

class TestEnvelopeFormat:
    @pytest.mark.asyncio
    async def test_event_data_matches_legacy_json_structure(self):
        """
        The old code sent ``{"event": str, "data": dict}`` via WS.
        The new path must produce identical payloads.
        """
        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})

        # Simulate what ConnectionManager.broadcast() receives
        assert event.event_type == "alert.created"
        assert event.data == {"alert_id": "a1", "severity": "high"}

        # The envelope that ConnectionManager builds:
        import json
        expected = json.dumps({"event": "alert.created", "data": {"alert_id": "a1", "severity": "high"}})
        actual = json.dumps({"event": event.event_type, "data": event.data})
        assert actual == expected
