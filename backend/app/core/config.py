from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings

# config.py → core/ → app/ → backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    APP_NAME: str = "NetTwin-SOC Backend"
    APP_VERSION: str = "1.1"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql://nettwin:yun211314@localhost:15432/nettwin"

    DATA_DIR: Path = BASE_DIR / "data"
    PCAP_DIR: Path = BASE_DIR / "data" / "pcaps"

    # JSON 字符串，在 detection 服务中解析
    MODEL_PARAMS: str = "{}"

    API_V1_PREFIX: str = "/api/v1"

    THREAT_ENRICHMENT_ENABLED: bool = True
    PIPELINE_OBSERVABILITY_ENABLED: bool = True
    STRUCTURED_LOG_ENABLED: bool = False

    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.PCAP_DIR.mkdir(parents=True, exist_ok=True)
