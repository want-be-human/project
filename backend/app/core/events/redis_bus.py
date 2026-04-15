"""Redis Stream 事件总线占位：未来基于 XADD / XREADGROUP 实现多进程扇出。"""

from app.core.events.base import EventBus, EventHandler
from app.core.events.models import DomainEvent

_NOT_IMPL_MSG = "RedisEventBus will be available in a future release"


class RedisEventBus(EventBus):
    async def publish(self, event: DomainEvent) -> None:  # noqa: D401
        raise NotImplementedError(_NOT_IMPL_MSG)

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError(_NOT_IMPL_MSG)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError(_NOT_IMPL_MSG)
