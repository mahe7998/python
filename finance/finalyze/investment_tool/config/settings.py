"""Application settings and configuration management."""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class APIKeysConfig(BaseModel):
    """API key configuration."""
    eodhd: Optional[str] = Field(default=None)
    polygon: Optional[str] = Field(default=None)
    finnhub: Optional[str] = Field(default=None)


class DataConfig(BaseModel):
    """Data storage configuration."""
    cache_dir: Path = Field(default=Path.home() / ".investment_tool" / "cache")
    database_path: Path = Field(default=Path.home() / ".investment_tool" / "data.duckdb")
    max_cache_age_days: int = Field(default=7)
    auto_refresh_interval_minutes: int = Field(default=15)


class ProvidersConfig(BaseModel):
    """Data provider priority configuration."""
    price_data: List[str] = Field(default=["eodhd", "polygon"])
    fundamentals: List[str] = Field(default=["eodhd"])
    news: List[str] = Field(default=["eodhd"])
    social_sentiment: List[str] = Field(default=["finnhub", "eodhd"])


class TreemapColorConfig(BaseModel):
    """Treemap color scale configuration."""
    min_color: str = Field(default="#EF4444")
    mid_color: str = Field(default="#FFFFFF")
    max_color: str = Field(default="#22C55E")
    min_value: float = Field(default=-5.0)
    max_value: float = Field(default=5.0)


class UIConfig(BaseModel):
    """UI configuration."""
    theme: str = Field(default="dark")
    default_chart_type: str = Field(default="candlestick")
    default_timeframe: str = Field(default="1D")
    treemap_color_scale: TreemapColorConfig = Field(default_factory=TreemapColorConfig)


class SentimentConfig(BaseModel):
    """Sentiment analysis configuration."""
    use_finbert: bool = Field(default=True)
    finbert_model: str = Field(default="ProsusAI/finbert")
    ensemble_weights: Dict[str, float] = Field(default={"eodhd": 0.4, "finbert": 0.6})


class IndicatorsConfig(BaseModel):
    """Technical indicators configuration."""
    default_sma_periods: List[int] = Field(default=[20, 50, 200])
    default_ema_periods: List[int] = Field(default=[12, 26])
    rsi_period: int = Field(default=14)
    macd_fast: int = Field(default=12)
    macd_slow: int = Field(default=26)
    macd_signal: int = Field(default=9)


class AnalysisConfig(BaseModel):
    """Analysis settings configuration."""
    sentiment: SentimentConfig = Field(default_factory=SentimentConfig)
    indicators: IndicatorsConfig = Field(default_factory=IndicatorsConfig)


class BacktestingConfig(BaseModel):
    """Backtesting configuration."""
    default_initial_capital: float = Field(default=100000.0)
    commission_per_trade: float = Field(default=0.001)
    slippage: float = Field(default=0.0005)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default="INFO")
    file: Path = Field(default=Path.home() / ".investment_tool" / "logs" / "app.log")
    max_size_mb: int = Field(default=10)
    backup_count: int = Field(default=5)


class AppConfig(BaseModel):
    """Main application configuration."""
    api_keys: APIKeysConfig = Field(default_factory=APIKeysConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    backtesting: BacktestingConfig = Field(default_factory=BacktestingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AppConfig":
        """Load configuration from file and environment variables."""
        config_dict: Dict[str, Any] = {}

        if config_path and config_path.exists():
            with open(config_path, "r") as f:
                config_dict = yaml.safe_load(f) or {}

        api_keys = config_dict.get("api_keys", {})
        api_keys["eodhd"] = api_keys.get("eodhd") or os.getenv("EODHD_API_KEY")
        api_keys["polygon"] = api_keys.get("polygon") or os.getenv("POLYGON_API_KEY")
        api_keys["finnhub"] = api_keys.get("finnhub") or os.getenv("FINNHUB_API_KEY")
        config_dict["api_keys"] = api_keys

        return cls(**config_dict)

    def save(self, config_path: Path) -> None:
        """Save configuration to file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_dict = self.model_dump()
        for key in ["cache_dir", "database_path", "file"]:
            for section in config_dict.values():
                if isinstance(section, dict) and key in section:
                    section[key] = str(section[key])

        with open(config_path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False)

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.data.cache_dir.mkdir(parents=True, exist_ok=True)
        self.data.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.logging.file.parent.mkdir(parents=True, exist_ok=True)


_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        default_config_path = Path.home() / ".investment_tool" / "settings.yaml"
        _config = AppConfig.load(default_config_path)
        _config.ensure_directories()
    return _config


def set_config(config: AppConfig) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config
