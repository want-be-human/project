"""
API 依赖项。
包含数据库会话与通用依赖。
"""

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.base import Base


# 基于 DATABASE_URL 创建引擎
# 对 SQLite 需设置 check_same_thread=False 以兼容 FastAPI 异步场景
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
)

# SQLite 性能优化：WAL 模式 + 减少 fsync + 大缓存
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """初始化数据库表。"""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    提供数据库会话依赖。
    产出会话并确保使用后关闭。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
