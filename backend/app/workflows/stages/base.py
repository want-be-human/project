"""
Base stage abstraction for workflow engine.
All stages implement a unified interface for orchestration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.alert import Alert


@dataclass
class StageContext:
    """Input context passed to each workflow stage."""

    alert: Alert
    language: str = "en"
    previous_outputs: dict[str, Any] = field(default_factory=dict)
    db: Session = None  # type: ignore[assignment]


@dataclass
class StageResult:
    """Output returned by each workflow stage."""

    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseStage(ABC):
    """Abstract base class for all workflow stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage identifier used in registry and execution logs."""
        ...

    @abstractmethod
    def execute(self, context: StageContext) -> StageResult:
        """
        Execute stage logic.

        Args:
            context: StageContext with alert, language, previous_outputs, db.

        Returns:
            StageResult with output compatible with existing schemas.
        """
        ...
