from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.alert import Alert


@dataclass
class StageContext:
    alert: Alert
    language: str = "en"
    previous_outputs: dict[str, Any] = field(default_factory=dict)
    db: Session = None  # type: ignore[assignment]


@dataclass
class StageResult:
    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseStage(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def execute(self, context: StageContext) -> StageResult:
        ...
