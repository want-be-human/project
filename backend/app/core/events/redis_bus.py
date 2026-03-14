"""
Redis Stream event bus — placeholder for future implementation.

This module mirrors the EventBus interface but delegates to Redis Streams
(XADD / XREADGROUP), enabling multi-process fan-out.  The implementation
is intentionally left as a skeleton; calling any method will raise
``NotImplementedError``.
"""

from app.core.events.base import EventBus, EventHandler
from app.core.events.models import DomainEvent


class RedisEventBus(EventBus):
    """Redis Stream backed event bus (not yet implemented)."""

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
