"""
数据库配置。
包含 SQLAlchemy 引擎与会话管理。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


# 创建 SQLAlchemy 引擎
# 对 SQLite 使用 connect_args 以支持多线程
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
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
