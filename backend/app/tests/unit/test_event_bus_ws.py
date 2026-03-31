"""
Unit tests for the WebSocket ↔ EventBus integration layer.

Verifies that:
- WebSocketEventConsumer correctly forwards DomainEvents to ConnectionManager.
- The JSON envelope format ``{"event": str, "data": dict}`` is preserved.
- v2 meta envelope is included in broadcast calls.
- broadcast_* helper functions publish through the EventBus (not directly
  to ConnectionManager) and the consumer bridges the gap.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY

from app.core.events import (
    InMemoryEventBus,
    make_event,
    reset_event_bus,
    PCAP_PROCESS_PROGRESS,
    ALERT_CREATED,
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


def _assert_broadcast_called(mock_manager, event_name: str, data: dict):
    """验证 broadcast 被正确调用，包含 event、data 和 v2 meta 信封。"""
    mock_manager.broadcast.assert_awaited_once()
    call_args = mock_manager.broadcast.call_args
    assert call_args[0][0] == event_name  # event
    assert call_args[0][1] == data        # data
    # 验证 meta 信封包含 v2 必需字段
    meta = call_args[1].get("meta") if call_args[1] else call_args[0][2] if len(call_args[0]) > 2 else None
    assert meta is not None, "broadcast 应包含 meta 参数"
    assert "event_id" in meta
    assert "trace_id" in meta
    assert meta["source"] == "nettwin-soc"
    assert meta["version"] == "2"
    assert "timestamp" in meta


# ── WebSocketEventConsumer tests ─────────────────────────────────

class TestWebSocketEventConsumer:
    @pytest.mark.asyncio
    async def test_handle_forwards_event_to_manager(self, consumer, mock_manager):
        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})
        await consumer.handle(event)

        _assert_broadcast_called(
            mock_manager, "alert.created", {"alert_id": "a1", "severity": "high"}
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

        _assert_broadcast_called(
            mock_manager, "pcap.process.progress", {"pcap_id": "p1", "percent": 42}
        )

    @pytest.mark.asyncio
    async def test_meta_contains_trace_id_from_event(self, consumer, mock_manager):
        """v2: meta.trace_id 应与 DomainEvent.trace_id 一致。"""
        event = make_event(
            ALERT_CREATED,
            {"alert_id": "a1", "severity": "high"},
            trace_id="custom-trace-123",
        )
        await consumer.handle(event)

        meta = mock_manager.broadcast.call_args[1]["meta"]
        assert meta["trace_id"] == "custom-trace-123"


# ── broadcast_* helper integration tests ────────────────────────

class TestBroadcastHelpers:
    """Verify each helper publishes the correct event type and data."""

    @pytest.mark.asyncio
    async def test_broadcast_pcap_progress(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_pcap_progress("pcap-1", 50)

        _assert_broadcast_called(
            mock_manager, "pcap.process.progress", {"pcap_id": "pcap-1", "percent": 50}
        )

    @pytest.mark.asyncio
    async def test_broadcast_pcap_done(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_pcap_done("pcap-1", 120, 5)

        _assert_broadcast_called(
            mock_manager, "pcap.process.done", {"pcap_id": "pcap-1", "flow_count": 120, "alert_count": 5}
        )

    @pytest.mark.asyncio
    async def test_broadcast_alert_created(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_alert_created("alert-1", "high")

        _assert_broadcast_called(
            mock_manager, "alert.created", {"alert_id": "alert-1", "severity": "high"}
        )

    @pytest.mark.asyncio
    async def test_broadcast_alert_updated(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_alert_updated("alert-1", "resolved")

        _assert_broadcast_called(
            mock_manager, "alert.updated", {"alert_id": "alert-1", "status": "resolved"}
        )

    @pytest.mark.asyncio
    async def test_broadcast_dryrun_created(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_dryrun_created("dr-1", "alert-1", 0.75)

        _assert_broadcast_called(
            mock_manager, "twin.dryrun.created",
            {"dry_run_id": "dr-1", "alert_id": "alert-1", "risk": 0.75, "confidence": 0.5}
        )

    @pytest.mark.asyncio
    async def test_broadcast_scenario_done(self, consumer, mock_manager):
        bus = InMemoryEventBus()
        with patch("app.api.routers.stream.get_event_bus", return_value=bus):
            await consumer.register()
            await broadcast_scenario_done("sc-1", "pass")

        _assert_broadcast_called(
            mock_manager, "scenario.run.done", {"scenario_id": "sc-1", "status": "pass"}
        )


# ── JSON envelope compatibility test ────────────────────────────

class TestEnvelopeFormat:
    @pytest.mark.asyncio
    async def test_event_data_matches_legacy_json_structure(self):
        """
        The old code sent ``{"event": str, "data": dict}`` via WS.
        The new path must produce identical core payloads (meta is additive).
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

    @pytest.mark.asyncio
    async def test_v2_envelope_includes_meta(self):
        """v2 信封在 event + data 之外附加 meta 字段。"""
        event = make_event(ALERT_CREATED, {"alert_id": "a1", "severity": "high"})

        # 模拟 WebSocketEventConsumer.handle() 构建的 meta
        meta = {
            "event_id": event.event_id,
            "trace_id": event.trace_id,
            "source": event.source,
            "version": event.version,
            "timestamp": event.timestamp.isoformat(),
        }

        import json
        envelope = json.loads(json.dumps({
            "event": event.event_type,
            "data": event.data,
            "meta": meta,
        }))

        # 旧字段保持不变
        assert envelope["event"] == "alert.created"
        assert envelope["data"] == {"alert_id": "a1", "severity": "high"}
        # v2 新增 meta
        assert envelope["meta"]["source"] == "nettwin-soc"
        assert envelope["meta"]["version"] == "2"
        assert len(envelope["meta"]["trace_id"]) > 0
