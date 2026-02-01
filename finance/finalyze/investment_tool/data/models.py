"""Data models for the investment tracking tool."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class TimeFrame(Enum):
    """Supported timeframes for price data."""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAILY = "1D"
    WEEKLY = "1W"
    MONTHLY = "1M"


class ChartType(Enum):
    """Supported chart types."""
    CANDLESTICK = "candlestick"
    OHLC = "ohlc"
    LINE = "line"
    AREA = "area"


class TradeType(Enum):
    """Trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class PeriodType(Enum):
    """Financial reporting period types."""
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    FY = "FY"


@dataclass
class PriceBar:
    """Single OHLCV price bar."""
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "adjusted_close": self.adjusted_close,
        }


@dataclass
class IntradayBar:
    """Intraday OHLCV price bar with timestamp."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass
class CompanyInfo:
    """Company metadata."""
    ticker: str
    name: str
    exchange: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    last_updated: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "exchange": self.exchange,
            "sector": self.sector,
            "industry": self.industry,
            "market_cap": self.market_cap,
            "country": self.country,
            "currency": self.currency,
            "pe_ratio": self.pe_ratio,
            "eps": self.eps,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class SentimentData:
    """Sentiment analysis results."""
    polarity: float
    positive: float
    negative: float
    neutral: Optional[float] = None
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "polarity": self.polarity,
            "positive": self.positive,
            "negative": self.negative,
            "neutral": self.neutral,
            "source": self.source,
        }


@dataclass
class NewsArticle:
    """News article with sentiment."""
    id: str
    ticker: str
    title: str
    summary: str
    published_at: datetime
    source: str
    url: str
    eodhd_sentiment: Optional[SentimentData] = None
    finbert_sentiment: Optional[SentimentData] = None
    ensemble_polarity: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "title": self.title,
            "summary": self.summary,
            "published_at": self.published_at.isoformat(),
            "source": self.source,
            "url": self.url,
            "eodhd_sentiment": self.eodhd_sentiment.to_dict() if self.eodhd_sentiment else None,
            "finbert_sentiment": self.finbert_sentiment.to_dict() if self.finbert_sentiment else None,
            "ensemble_polarity": self.ensemble_polarity,
        }


@dataclass
class DailySentiment:
    """Aggregated daily sentiment for a ticker."""
    ticker: str
    date: date
    news_count: int
    avg_polarity: float
    positive_ratio: float
    negative_ratio: float
    social_mentions: Optional[int] = None
    social_positive: Optional[int] = None
    social_negative: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "date": self.date.isoformat(),
            "news_count": self.news_count,
            "avg_polarity": self.avg_polarity,
            "positive_ratio": self.positive_ratio,
            "negative_ratio": self.negative_ratio,
            "social_mentions": self.social_mentions,
            "social_positive": self.social_positive,
            "social_negative": self.social_negative,
        }


@dataclass
class Fundamentals:
    """Company fundamental data."""
    ticker: str
    report_date: date
    period_type: PeriodType
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    free_cash_flow: Optional[float] = None
    raw_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "report_date": self.report_date.isoformat(),
            "period_type": self.period_type.value,
            "revenue": self.revenue,
            "net_income": self.net_income,
            "eps": self.eps,
            "pe_ratio": self.pe_ratio,
            "pb_ratio": self.pb_ratio,
            "dividend_yield": self.dividend_yield,
            "debt_to_equity": self.debt_to_equity,
            "roe": self.roe,
            "roa": self.roa,
            "free_cash_flow": self.free_cash_flow,
            "raw_data": self.raw_data,
        }


@dataclass
class Watchlist:
    """User watchlist."""
    id: int
    name: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class WatchlistItem:
    """Item in a watchlist."""
    watchlist_id: int
    ticker: str
    added_at: datetime = field(default_factory=datetime.now)
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "watchlist_id": self.watchlist_id,
            "ticker": self.ticker,
            "added_at": self.added_at.isoformat(),
            "notes": self.notes,
        }


@dataclass
class BacktestRun:
    """Backtest run configuration."""
    id: str
    name: str
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "strategy_name": self.strategy_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": self.initial_capital,
            "parameters": self.parameters,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BacktestResult:
    """Backtest results for a single ticker."""
    run_id: str
    ticker: str
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "metrics": self.metrics,
        }


@dataclass
class Trade:
    """Individual trade in backtest."""
    id: int
    run_id: str
    ticker: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    position_size: float
    pnl: float
    pnl_percent: float
    trade_type: TradeType

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "ticker": self.ticker,
            "entry_date": self.entry_date.isoformat(),
            "exit_date": self.exit_date.isoformat(),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "position_size": self.position_size,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "trade_type": self.trade_type.value,
        }


@dataclass
class CacheMetadata:
    """Metadata about cached data."""
    key: str
    provider: str
    ticker: str
    data_type: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    last_fetched: Optional[datetime] = None
    record_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "provider": self.provider,
            "ticker": self.ticker,
            "data_type": self.data_type,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "last_fetched": self.last_fetched.isoformat() if self.last_fetched else None,
            "record_count": self.record_count,
        }
