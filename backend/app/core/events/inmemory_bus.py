"""
In-memory event bus implementation.

Default backend for the event bus — no external dependencies.
Suitable for single-process deployments.
"""

import asyncio
import logging
from collections import defaultdict

from app.core.events.base import WILDCARD, EventBus, EventHandler
from app.core.events.models import DomainEvent

logger = logging.getLogger(__name__)


class InMemoryEventBus(EventBus):
    """Async in-memory publish/subscribe event bus."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    # ── publish ──────────────────────────────────────────────────

    async def publish(self, event: DomainEvent) -> None:
        """
        Dispatch *event* to all handlers registered for its type
        **and** to wildcard (``*``) handlers.

        Individual handler failures are logged but never propagate —
        one broken subscriber cannot disrupt others.
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

    # ── subscribe / unsubscribe ──────────────────────────────────

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        async with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        async with self._lock:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass  # handler was not registered — nothing to do
