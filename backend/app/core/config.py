"""
Application configuration.
Environment variables and constants.
"""

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "NetTwin-SOC Backend"
    APP_VERSION: str = "1.1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./data/nettwin.db"

    # Data storage
    DATA_DIR: Path = Path("./data")
    PCAP_DIR: Path = Path("./data/pcaps")

    # Detection model parameters (JSON string, parsed in detection service)
    MODEL_PARAMS: str = "{}"

    # API
    API_V1_PREFIX: str = "/api/v1"

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
