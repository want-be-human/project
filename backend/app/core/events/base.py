"""
事件总线抽象基类。

定义 publish / subscribe / unsubscribe 的契约，
所有事件总线实现都必须遵循。
"""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from app.core.events.models import DomainEvent

# 处理器类型：接收 DomainEvent 的异步可调用对象。
EventHandler = Callable[[DomainEvent], Awaitable[None]]

# 通配主题：订阅者可接收任意类型事件。
WILDCARD = "*"


class EventBus(ABC):
    """事件总线抽象接口。"""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """向所有匹配订阅者发布事件。"""

    @abstractmethod
    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        为匹配 ``event_type`` 的事件注册 *handler*。

        使用 ``"*"`` 可订阅所有事件类型。
        """

    @abstractmethod
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """移除已注册的处理器。"""
