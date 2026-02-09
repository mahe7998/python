"""Configuration settings for the data server."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://dataserver:password@localhost:5432/data_cache"

    # EODHD API
    eodhd_api_key: str = ""
    eodhd_base_url: str = "https://eodhd.com/api"

    # YouTube API
    google_youtube_api_key: str = ""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Cache durations (seconds)
    cache_daily_prices: int = 86400  # 24 hours
    cache_intraday_prices: int = 60  # 1 minute
    cache_live_quotes: int = 15  # 15 seconds
    cache_news: int = 900  # 15 minutes
    cache_fundamentals: int = 86400  # 1 day
    cache_company_info: int = 604800  # 7 days
    cache_search: int = 3600  # 1 hour

    # SEC EDGAR
    sec_edgar_user_agent: str = "FinalyzeApp admin@finalyze.local"
    sec_edgar_rate_limit: float = 0.15  # seconds between requests

    # Worker intervals (seconds)
    worker_price_interval: int = 15
    worker_news_interval: int = 900  # 15 minutes
    worker_daily_time: str = "16:30"  # 4:30 PM ET

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
