"""
Abstract base class for the event bus.

Defines the publish / subscribe / unsubscribe contract that all
event bus implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from app.core.events.models import DomainEvent

# Handler type: an async callable that receives a DomainEvent.
EventHandler = Callable[[DomainEvent], Awaitable[None]]

# Wildcard topic — subscribers receive every event regardless of type.
WILDCARD = "*"


class EventBus(ABC):
    """Abstract event bus interface."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all matching subscribers."""

    @abstractmethod
    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        Register *handler* for events whose ``event_type`` matches.

        Use ``"*"`` to subscribe to all event types.
        """

    @abstractmethod
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a previously registered handler."""
