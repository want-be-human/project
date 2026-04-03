"""评分器抽象基类。"""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.schemas.analytics import ScoreResultSchema


class BaseScorer(ABC):
    """
    评分器基类。
    所有评分器必须实现 compute() 方法，返回标准化 ScoreResultSchema。
    子类通过 version 属性声明算法版本号。
    """

    # 子类必须声明版本号
    version: str = "unknown"

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def compute(self, **kwargs) -> ScoreResultSchema:
        """计算评分，返回标准化结果。"""
        ...
