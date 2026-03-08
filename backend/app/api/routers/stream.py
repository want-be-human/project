"""
WebSocket stream router.
WS /api/v1/stream
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import json
import asyncio

router = APIRouter(tags=["stream"])

# Simple connection manager for WebSocket clients
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


# Helper functions for broadcasting events from other parts of the application

async def broadcast_pcap_progress(pcap_id: str, percent: int):
    """Broadcast PCAP processing progress."""
    await manager.broadcast(
        "pcap.process.progress",
        {"pcap_id": pcap_id, "percent": percent}
    )


async def broadcast_pcap_done(pcap_id: str, flow_count: int, alert_count: int):
    """Broadcast PCAP processing completion."""
    await manager.broadcast(
        "pcap.process.done",
        {"pcap_id": pcap_id, "flow_count": flow_count, "alert_count": alert_count}
    )


async def broadcast_alert_created(alert_id: str, severity: str):
    """Broadcast new alert creation."""
    await manager.broadcast(
        "alert.created",
        {"alert_id": alert_id, "severity": severity}
    )


async def broadcast_alert_updated(alert_id: str, status: str):
    """Broadcast alert status update."""
    await manager.broadcast(
        "alert.updated",
        {"alert_id": alert_id, "status": status}
    )


async def broadcast_dryrun_created(dry_run_id: str, alert_id: str, risk: float):
    """Broadcast dry-run creation."""
    await manager.broadcast(
        "twin.dryrun.created",
        {"dry_run_id": dry_run_id, "alert_id": alert_id, "risk": risk}
    )


async def broadcast_scenario_done(scenario_id: str, status: str):
    """Broadcast scenario run completion."""
    await manager.broadcast(
        "scenario.run.done",
        {"scenario_id": scenario_id, "status": status}
    )
