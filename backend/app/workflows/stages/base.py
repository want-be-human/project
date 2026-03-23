"""
工作流引擎的阶段抽象基类。
所有阶段通过统一接口参与编排。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.alert import Alert


@dataclass
class StageContext:
    """传递给各工作流阶段的输入上下文。"""

    alert: Alert
    language: str = "en"
    previous_outputs: dict[str, Any] = field(default_factory=dict)
    db: Session = None  # type: ignore[assignment]


@dataclass
class StageResult:
    """各工作流阶段返回的输出结构。"""

    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseStage(ABC):
    """所有工作流阶段的抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """阶段标识符，用于注册表与执行日志。"""
        ...

    @abstractmethod
    def execute(self, context: StageContext) -> StageResult:
        """
        执行阶段逻辑。

        参数：
            context: 包含 alert、language、previous_outputs、db 的 StageContext。

        返回：
            与现有模式兼容输出的 StageResult。
        """
        ...
