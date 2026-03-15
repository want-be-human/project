"""
Application configuration.
Environment variables and constants.
"""

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings

# Resolve BASE_DIR to the backend/ directory regardless of CWD
# config.py → core/ → app/ → backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "NetTwin-SOC Backend"
    APP_VERSION: str = "1.1"
    DEBUG: bool = False

    # Database – absolute path derived from backend/
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'data' / 'nettwin.db').as_posix()}"

    # Data storage – absolute paths derived from backend/
    DATA_DIR: Path = BASE_DIR / "data"
    PCAP_DIR: Path = BASE_DIR / "data" / "pcaps"

    # Detection model parameters (JSON string, parsed in detection service)
    MODEL_PARAMS: str = "{}"

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Feature flags
    WORKFLOW_ENGINE_ENABLED: bool = True
    THREAT_ENRICHMENT_ENABLED: bool = True
    PIPELINE_OBSERVABILITY_ENABLED: bool = True
    STRUCTURED_LOG_ENABLED: bool = False

    # CORS (for development)
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()

# Ensure directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.PCAP_DIR.mkdir(parents=True, exist_ok=True)
