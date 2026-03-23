"""
API 路由集合。
所有路由均遵循 DOC C v1.1 规范。
"""

from app.api.routers import health
from app.api.routers import pcaps
from app.api.routers import flows
from app.api.routers import alerts
from app.api.routers import topology
from app.api.routers import agent
from app.api.routers import evidence
from app.api.routers import twin
from app.api.routers import scenarios
from app.api.routers import stream
from app.api.routers import pipeline

__all__ = [
    "health",
    "pcaps",
    "flows",
    "alerts",
    "topology",
    "agent",
    "evidence",
    "twin",
    "scenarios",
    "stream",
    "pipeline",
]
