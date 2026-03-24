"""
应用配置。
环境变量与常量定义。
"""

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings

# 无论当前工作目录如何，都将 BASE_DIR 解析到 backend/ 目录
# config.py → core/ → app/ → backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """从环境变量加载的应用配置。"""

    # 应用基础配置
    APP_NAME: str = "NetTwin-SOC Backend"
    APP_VERSION: str = "1.1"
    DEBUG: bool = False

    # 数据库：基于 backend/ 推导绝对路径
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'data' / 'nettwin.db').as_posix()}"

    # 数据存储：基于 backend/ 推导绝对路径
    DATA_DIR: Path = BASE_DIR / "data"
    PCAP_DIR: Path = BASE_DIR / "data" / "pcaps"

    # 检测模型参数（JSON 字符串，在 detection 服务中解析）
    MODEL_PARAMS: str = "{}"

    # API
    API_V1_PREFIX: str = "/api/v1"

    # 功能开关
    THREAT_ENRICHMENT_ENABLED: bool = True
    PIPELINE_OBSERVABILITY_ENABLED: bool = True
    STRUCTURED_LOG_ENABLED: bool = False

    # CORS（开发环境）
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """获取缓存后的配置实例。"""
    return Settings()


settings = get_settings()

# 确保目录存在
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.PCAP_DIR.mkdir(parents=True, exist_ok=True)
