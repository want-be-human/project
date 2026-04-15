from typing import Generator
from sqlalchemy.orm import Session

from app.core.database import engine, SessionLocal, get_db  # noqa: F401
from app.models.base import Base


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
