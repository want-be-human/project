"""
数据库配置。
包含 SQLAlchemy 引擎与会话管理。
PostgreSQL 专用（连接池 + MVCC 并发）。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


# PostgreSQL 连接池配置
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,           # 连接池常驻连接数
    max_overflow=20,        # 超出 pool_size 时最多额外创建的连接
    pool_pre_ping=True,     # 使用前 ping 检测连接是否存活
    echo=settings.DEBUG,
)

# 会话工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """所有 SQLAlchemy 模型的基类。"""
    pass


def get_db():
    """
    提供数据库会话的依赖函数。
    通常与 FastAPI 的 Depends() 一起使用。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """创建全部数据表（用于开发/测试）。"""
    Base.metadata.create_all(bind=engine)
