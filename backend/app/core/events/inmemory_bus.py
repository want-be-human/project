"""
内存事件总线实现。

作为事件总线的默认后端，无外部依赖。
适用于单进程部署。
"""

import asyncio
import logging
from collections import defaultdict

from app.core.events.base import WILDCARD, EventBus, EventHandler
from app.core.events.models import DomainEvent

logger = logging.getLogger(__name__)


class InMemoryEventBus(EventBus):
    """异步内存发布/订阅事件总线。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    # ── 发布 ────────────────────────────────────────────────────

    async def publish(self, event: DomainEvent) -> None:
        """
        将 *event* 分发给其类型对应的处理器，
        同时分发给通配符（``*``）处理器。

        单个处理器失败仅记录日志，不向外传播，
        以避免某个订阅者异常影响整体分发。
        """
        async with self._lock:
            handlers = list(self._handlers.get(event.event_type, []))
            handlers += list(self._handlers.get(WILDCARD, []))

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "EventBus handler %s failed for event %s",
                    getattr(handler, "__qualname__", handler),
                    event.event_type,
                )

    # ── 订阅 / 取消订阅 ─────────────────────────────────────────

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        async with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        async with self._lock:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass  # 处理器未注册，无需处理
