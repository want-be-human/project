"""
API 依赖项。
包含数据库会话与通用依赖。
统一使用 core.database 中的引擎和会话工厂，避免重复创建。
"""

from typing import Generator
from sqlalchemy.orm import Session

from app.core.database import engine, SessionLocal, get_db  # noqa: F401
from app.models.base import Base


def init_db() -> None:
    """初始化数据库表。"""
    Base.metadata.create_all(bind=engine)
