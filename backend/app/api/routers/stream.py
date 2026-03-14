"""
WebSocket stream router.
WS /api/v1/stream

Broadcasting now goes through the internal EventBus:

    broadcast_* helper  →  EventBus.publish(DomainEvent)
                                ↓
                    WebSocketEventConsumer (subscriber)
                                ↓
                    ConnectionManager.broadcast()  →  WS clients

Existing helper function signatures are 100 % unchanged so that
callers (pcaps.py, alerts.py, twin.py, scenarios.py) need zero edits.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import json
import asyncio
import logging

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
    WILDCARD,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])


# ── WebSocket connection manager (unchanged) ─────────────────────

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept and track new connection."""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove connection from tracking."""
        self.active_connections.discard(websocket)

    async def broadcast(self, event: str, data: dict):
        """Broadcast event to all connected clients."""
        message = json.dumps({"event": event, "data": data})
        disconnected = set()

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)

        # Clean up disconnected clients
        self.active_connections -= disconnected

    async def send_to(self, websocket: WebSocket, event: str, data: dict):
        """Send event to specific client."""
        message = json.dumps({"event": event, "data": data})
        await websocket.send_text(message)


# Global connection manager instance
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the connection manager instance."""
    return manager


# ── WebSocket event consumer (EventBus → WS) ────────────────────

class WebSocketEventConsumer:
    """
    Bridges the EventBus to WebSocket clients.

    Subscribes to **all** domain events (wildcard ``*``) and forwards
    each one to ``ConnectionManager.broadcast()``, preserving the
    existing ``{"event": str, "data": dict}`` JSON envelope.
    """

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self._manager = connection_manager

    async def handle(self, event: DomainEvent) -> None:
        """Forward a domain event to all connected WS clients."""
        await self._manager.broadcast(event.event_type, event.data)

    async def register(self) -> None:
        """Subscribe to every event type on the global bus."""
        bus = get_event_bus()
        await bus.subscribe(WILDCARD, self.handle)

    async def unregister(self) -> None:
        """Unsubscribe from the global bus."""
        bus = get_event_bus()
        await bus.unsubscribe(WILDCARD, self.handle)


# Singleton consumer — initialised on app startup via ``register()``.
ws_consumer = WebSocketEventConsumer(manager)


# ── WebSocket endpoint (unchanged) ──────────────────────────────

@router.websocket("/stream")
@router.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time events.

    Events (DOC C C7.2):
    - pcap.process.progress: { pcap_id, percent }
    - pcap.process.done: { pcap_id, flow_count, alert_count }
    - alert.created: { alert_id, severity }
    - alert.updated: { alert_id, status }
    - twin.dryrun.created: { dry_run_id, alert_id, risk }
    - scenario.run.done: { scenario_id, status }
    """
    await manager.connect(websocket)

    try:
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages (ping/pong or commands)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # Heartbeat timeout
                )

                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_text(json.dumps({"event": "heartbeat", "data": {}}))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


# ── Broadcast helpers ────────────────────────────────────────────
# Signatures are *unchanged* — callers need zero modifications.
# Internally they now publish through the EventBus; the
# WebSocketEventConsumer forwards each event to WS clients.

async def broadcast_pcap_progress(pcap_id: str, percent: int):
    """Broadcast PCAP processing progress."""
    bus = get_event_bus()
    await bus.publish(make_event(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": percent}))


async def broadcast_pcap_done(pcap_id: str, flow_count: int, alert_count: int):
    """Broadcast PCAP processing completion."""
    bus = get_event_bus()
    await bus.publish(make_event(PCAP_PROCESS_DONE, {"pcap_id": pcap_id, "flow_count": flow_count, "alert_count": alert_count}))


async def broadcast_alert_created(alert_id: str, severity: str):
    """Broadcast new alert creation."""
    bus = get_event_bus()
    await bus.publish(make_event(ALERT_CREATED, {"alert_id": alert_id, "severity": severity}))


async def broadcast_alert_updated(alert_id: str, status: str):
    """Broadcast alert status update."""
    bus = get_event_bus()
    await bus.publish(make_event(ALERT_UPDATED, {"alert_id": alert_id, "status": status}))


async def broadcast_dryrun_created(dry_run_id: str, alert_id: str, risk: float):
    """Broadcast dry-run creation."""
    bus = get_event_bus()
    await bus.publish(make_event(TWIN_DRYRUN_CREATED, {"dry_run_id": dry_run_id, "alert_id": alert_id, "risk": risk}))


async def broadcast_scenario_done(scenario_id: str, status: str):
    """Broadcast scenario run completion."""
    bus = get_event_bus()
    await bus.publish(make_event(SCENARIO_RUN_DONE, {"scenario_id": scenario_id, "status": status}))
    await manager.broadcast(
        "scenario.run.done",
        {"scenario_id": scenario_id, "status": status}
    )
