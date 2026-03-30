"""
WebSocket 流式路由。
WS /api/v1/stream

当前广播链路统一经过内部 EventBus：

    broadcast_* helper  →  EventBus.publish(DomainEvent)
                                ↓
                    WebSocketEventConsumer（订阅者）
                                ↓
                    ConnectionManager.broadcast()  →  WS 客户端

现有辅助函数签名保持 100% 不变，
因此调用方（pcaps.py、alerts.py、twin.py、scenarios.py）无需改动。
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


# ── WebSocket 连接管理器（保持不变） ──────────────────────────────

class ConnectionManager:
    """管理 WebSocket 连接。"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """接受并跟踪新连接。"""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        """从跟踪集合中移除连接。"""
        self.active_connections.discard(websocket)

    async def broadcast(self, event: str, data: dict):
        """向所有已连接客户端广播事件。"""
        message = json.dumps({"event": event, "data": data})
        disconnected = set()

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)

        # 清理已断开连接的客户端
        self.active_connections -= disconnected

    async def send_to(self, websocket: WebSocket, event: str, data: dict):
        """向指定客户端发送事件。"""
        message = json.dumps({"event": event, "data": data})
        await websocket.send_text(message)


# 全局连接管理器实例
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """获取连接管理器实例。"""
    return manager


# ── WebSocket 事件消费者（EventBus → WS） ───────────────────────

class WebSocketEventConsumer:
    """
    连接 EventBus 与 WebSocket 客户端。

    订阅 **所有** 领域事件（通配符 ``*``），并将每条事件转发到
    ``ConnectionManager.broadcast()``，保持现有
    ``{"event": str, "data": dict}`` JSON 包装格式不变。
    """

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self._manager = connection_manager

    async def handle(self, event: DomainEvent) -> None:
        """将领域事件转发给所有已连接 WS 客户端。"""
        await self._manager.broadcast(event.event_type, event.data)

    async def register(self) -> None:
        """在全局总线上订阅全部事件类型。"""
        bus = get_event_bus()
        await bus.subscribe(WILDCARD, self.handle)

    async def unregister(self) -> None:
        """从全局总线取消订阅。"""
        bus = get_event_bus()
        await bus.unsubscribe(WILDCARD, self.handle)


# 单例消费者：在应用启动阶段通过 ``register()`` 初始化。
ws_consumer = WebSocketEventConsumer(manager)


# ── WebSocket 端点（保持不变） ───────────────────────────────────

@router.websocket("/stream")
@router.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    """
    实时事件 WebSocket 端点。

    事件（DOC C C7.2）：
    - pcap.process.progress: { pcap_id, percent }
    - pcap.process.done: { pcap_id, flow_count, alert_count }
    - alert.created: { alert_id, severity }
    - alert.updated: { alert_id, status }
    - twin.dryrun.created: { dry_run_id, alert_id, risk }
    - scenario.run.done: { scenario_id, status }
    """
    await manager.connect(websocket)

    try:
        # 保持连接存活并处理入站消息
        while True:
            try:
                # 等待消息（ping/pong 或其他指令）
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # Heartbeat timeout
                )

                # 处理 ping
                if data == "ping":
                    await websocket.send_text("pong")

            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_text(json.dumps({"event": "heartbeat", "data": {}}))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


# ── 广播辅助函数 ─────────────────────────────────────────────────
# 函数签名保持不变，调用方无需改动。
# 内部改为经由 EventBus 发布，再由
# WebSocketEventConsumer 转发到 WS 客户端。

async def broadcast_pcap_progress(pcap_id: str, percent: int):
    """广播 PCAP 处理进度。"""
    bus = get_event_bus()
    await bus.publish(make_event(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": percent}))


async def broadcast_pcap_done(pcap_id: str, flow_count: int, alert_count: int):
    """广播 PCAP 处理完成事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(PCAP_PROCESS_DONE, {"pcap_id": pcap_id, "flow_count": flow_count, "alert_count": alert_count}))


async def broadcast_alert_created(alert_id: str, severity: str):
    """广播新告警创建事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(ALERT_CREATED, {"alert_id": alert_id, "severity": severity}))


async def broadcast_alert_updated(alert_id: str, status: str):
    """广播告警状态更新事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(ALERT_UPDATED, {"alert_id": alert_id, "status": status}))


async def broadcast_dryrun_created(dry_run_id: str, alert_id: str, risk: float, confidence: float = 0.5):
    """广播 dry-run 创建事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(TWIN_DRYRUN_CREATED, {
        "dry_run_id": dry_run_id, "alert_id": alert_id,
        "risk": risk, "confidence": confidence,
    }))


async def broadcast_scenario_done(scenario_id: str, status: str):
    """
    广播场景运行完成事件（已废弃，由 ScenarioRunTracker 内部发布）。
    保留此函数以兼容旧代码，但不再执行双重广播。
    """
    bus = get_event_bus()
    await bus.publish(make_event(SCENARIO_RUN_DONE, {"scenario_id": scenario_id, "status": status}))


# ── 场景运行实时阶段流事件广播 helpers ──────────────────────────

async def broadcast_scenario_run_started(
    scenario_id: str, run_id: str, scenario_name: str, total_stages: int
):
    """广播场景运行开始事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(
        "scenario.run.started",
        {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "scenario_name": scenario_name,
            "total_stages": total_stages,
        }
    ))


async def broadcast_scenario_stage_started(
    scenario_id: str, run_id: str, stage: str, stage_index: int, total_stages: int
):
    """广播场景阶段开始事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(
        "scenario.stage.started",
        {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "stage": stage,
            "stage_index": stage_index,
            "total_stages": total_stages,
        }
    ))


async def broadcast_scenario_stage_completed(
    scenario_id: str, run_id: str, stage: str, latency_ms: float, key_metrics: dict
):
    """广播场景阶段完成事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(
        "scenario.stage.completed",
        {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "stage": stage,
            "status": "completed",
            "latency_ms": latency_ms,
            "key_metrics": key_metrics,
        }
    ))


async def broadcast_scenario_stage_failed(
    scenario_id: str, run_id: str, stage: str, error_summary: str, failure_attribution: dict | None
):
    """广播场景阶段失败事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(
        "scenario.stage.failed",
        {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "stage": stage,
            "status": "failed",
            "error_summary": error_summary,
            "failure_attribution": failure_attribution,
        }
    ))


async def broadcast_scenario_run_progress(
    scenario_id: str, run_id: str, completed_stages: int, total_stages: int, percent: float
):
    """广播场景运行进度事件。"""
    bus = get_event_bus()
    await bus.publish(make_event(
        "scenario.run.progress",
        {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "completed_stages": completed_stages,
            "total_stages": total_stages,
            "percent": percent,
        }
    ))
