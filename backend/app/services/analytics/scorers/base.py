from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.schemas.analytics import ScoreResultSchema


class BaseScorer(ABC):
    version: str = "unknown"

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def compute(self, **kwargs) -> ScoreResultSchema:
        ...
