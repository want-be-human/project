"""内存事件总线：单进程默认后端，无外部依赖。"""

import asyncio
import logging
from collections import defaultdict

from app.core.events.base import WILDCARD, EventBus, EventHandler
from app.core.events.models import DomainEvent

logger = logging.getLogger(__name__)


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, event: DomainEvent) -> None:
        # 单个处理器失败仅记录日志，避免影响其他订阅者
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

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        async with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        async with self._lock:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass
