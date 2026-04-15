"""事件总线抽象接口：publish / subscribe / unsubscribe 契约。"""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from app.core.events.models import DomainEvent

EventHandler = Callable[[DomainEvent], Awaitable[None]]

# 通配主题：订阅所有事件类型
WILDCARD = "*"


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event: DomainEvent) -> None: ...

    @abstractmethod
    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """event_type="*" 订阅所有类型。"""

    @abstractmethod
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None: ...
