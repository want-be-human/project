"""
SQLAlchemy 基类与通用混入。
"""

from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.utils import generate_uuid, utc_now


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""
    pass


class BaseModel(Base):
    """包含 id、version、created_at 的抽象模型基类。"""

    __abstract__ = True

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
        nullable=False,
    )
    version: Mapped[str] = mapped_column(
        String(10),
        default="1.1",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
