"""
Redis Stream 事件总线（未来实现占位）。

该模块对齐 EventBus 接口，后续将基于 Redis Streams
（XADD / XREADGROUP）实现多进程扇出。当前仅保留骨架，
调用任意方法都会抛出 ``NotImplementedError``。
"""

from app.core.events.base import EventBus, EventHandler
from app.core.events.models import DomainEvent


class RedisEventBus(EventBus):
    """基于 Redis Stream 的事件总线（尚未实现）。"""

    async def publish(self, event: DomainEvent) -> None:  # noqa: D401
        raise NotImplementedError(
            "RedisEventBus will be available in a future release"
        )

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError(
            "RedisEventBus will be available in a future release"
        )

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError(
            "RedisEventBus will be available in a future release"
        )
