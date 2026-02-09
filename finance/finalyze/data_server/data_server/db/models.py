"""SQLAlchemy ORM models for the data cache."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    BigInteger,
    Numeric,
    DateTime,
    Date,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_server.db.database import Base


class DailyPrice(Base):
    """Cached daily prices."""

    __tablename__ = "daily_prices"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    open: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    close: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    adjusted_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IntradayPrice(Base):
    """Cached intraday prices."""

    __tablename__ = "intraday_prices"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    open: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    close: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    source: Mapped[Optional[str]] = mapped_column(String(20), default="live")  # 'live' or 'eodhd'
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Content(Base):
    """Shared content storage for news, YouTube, etc."""

    __tablename__ = "content"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    full_content: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    news_items: Mapped[list["News"]] = relationship(back_populates="content")
    youtube_videos: Mapped[list["YouTubeVideo"]] = relationship(back_populates="content")

    __table_args__ = (
        Index("idx_content_type", "content_type"),
        Index("idx_content_url", "url"),
    )


class News(Base):
    """News article metadata."""

    __tablename__ = "news"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("content.id")
    )
    source: Mapped[Optional[str]] = mapped_column(String(100))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    polarity: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    positive: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    negative: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    neutral: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    content: Mapped[Optional["Content"]] = relationship(back_populates="news_items")
    tickers: Mapped[list["NewsTicker"]] = relationship(
        back_populates="news", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_news_published", "published_at"),
        Index("idx_news_content", "content_id"),
    )


class NewsTicker(Base):
    """Many-to-many: News to tickers."""

    __tablename__ = "news_tickers"

    news_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("news.id", ondelete="CASCADE"), primary_key=True
    )
    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    relevance: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=1.0)

    # Relationships
    news: Mapped["News"] = relationship(back_populates="tickers")

    __table_args__ = (Index("idx_news_tickers_ticker", "ticker"),)


class YouTubeVideo(Base):
    """YouTube video metadata."""

    __tablename__ = "youtube_videos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("content.id")
    )
    channel_name: Mapped[Optional[str]] = mapped_column(String(255))
    channel_id: Mapped[Optional[str]] = mapped_column(String(64))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    view_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    content: Mapped[Optional["Content"]] = relationship(back_populates="youtube_videos")
    tickers: Mapped[list["YouTubeTicker"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class YouTubeTicker(Base):
    """Many-to-many: YouTube videos to tickers."""

    __tablename__ = "youtube_tickers"

    video_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("youtube_videos.id", ondelete="CASCADE"), primary_key=True
    )
    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    relevance: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=1.0)

    # Relationships
    video: Mapped["YouTubeVideo"] = relationship(back_populates="tickers")

    __table_args__ = (Index("idx_youtube_tickers_ticker", "ticker"),)


class Company(Base):
    """Cached company information."""

    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    exchange: Mapped[Optional[str]] = mapped_column(String(20))
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    market_cap: Mapped[Optional[int]] = mapped_column(BigInteger)
    shares_outstanding: Mapped[Optional[int]] = mapped_column(BigInteger)
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    eps: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrackedStock(Base):
    """Tracked stocks for background updates."""

    __tablename__ = "tracked_stocks"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(20))
    track_prices: Mapped[bool] = mapped_column(Boolean, default=True)
    track_news: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_price_update: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_news_update: Mapped[Optional[datetime]] = mapped_column(DateTime)


class LivePrice(Base):
    """Real-time price data for tracked stocks."""

    __tablename__ = "live_prices"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(20))
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    open: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    previous_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    change: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    change_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    market_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuarterlyFinancial(Base):
    """Quarterly financial data (income statement, balance sheet, cash flow)."""

    __tablename__ = "quarterly_financials"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    report_date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    quarter: Mapped[Optional[str]] = mapped_column(String(4))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    # Income Statement
    total_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    gross_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    operating_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    net_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    ebit: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    cost_of_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    research_development: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    selling_general_admin: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    interest_expense: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    tax_provision: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    # Balance Sheet
    cash: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    short_term_investments: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    total_assets: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    total_current_assets: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    total_liabilities: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    total_current_liabilities: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    stockholders_equity: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    long_term_debt: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    retained_earnings: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    # Cash Flow
    operating_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    capital_expenditure: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    free_cash_flow: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    dividends_paid: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    # Metadata
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_quarterly_financials_ticker", "ticker"),
    )


class CompanyHighlight(Base):
    """Company highlights: valuation, profitability, growth, share stats, technicals."""

    __tablename__ = "company_highlights"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    # General
    name: Mapped[Optional[str]] = mapped_column(String(255))
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    exchange: Mapped[Optional[str]] = mapped_column(String(20))
    currency: Mapped[Optional[str]] = mapped_column(String(10))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Valuation
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    forward_pe: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    peg_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    pb_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    ps_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    ev_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    ev_ebitda: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    enterprise_value: Mapped[Optional[int]] = mapped_column(BigInteger)
    # Profitability
    profit_margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    operating_margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    roe: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    roa: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    gross_profit_ttm: Mapped[Optional[int]] = mapped_column(BigInteger)
    ebitda: Mapped[Optional[int]] = mapped_column(BigInteger)
    revenue_ttm: Mapped[Optional[int]] = mapped_column(BigInteger)
    revenue_per_share: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    eps: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    diluted_eps_ttm: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    # Growth
    quarterly_revenue_growth_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    quarterly_earnings_growth_yoy: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    eps_estimate_current_year: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    wall_street_target_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    # Dividends
    dividend_yield: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    dividend_share: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    # Share Stats
    shares_outstanding: Mapped[Optional[int]] = mapped_column(BigInteger)
    shares_float: Mapped[Optional[int]] = mapped_column(BigInteger)
    percent_insiders: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    percent_institutions: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    shares_short: Mapped[Optional[int]] = mapped_column(BigInteger)
    short_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    # Technicals
    beta: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    week_52_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    week_52_low: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    day_50_ma: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    day_200_ma: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))
    # Market
    market_cap: Mapped[Optional[int]] = mapped_column(BigInteger)
    # Metadata
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SharesHistory(Base):
    """Historical shares outstanding data from multiple sources."""

    __tablename__ = "shares_history"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    report_date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), primary_key=True)  # sec_edgar, eodhd, yfinance
    shares_outstanding: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filing_type: Mapped[Optional[str]] = mapped_column(String(10))  # 10-K, 10-Q (SEC only)
    filed_date: Mapped[Optional[datetime]] = mapped_column(Date)  # SEC filing date
    fiscal_year: Mapped[Optional[int]] = mapped_column(Integer)
    fiscal_period: Mapped[Optional[str]] = mapped_column(String(4))  # Q1-Q4, FY
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_shares_history_ticker_date", "ticker", "report_date"),
    )


class CacheMetadata(Base):
    """Cache metadata for staleness checking."""

    __tablename__ = "cache_metadata"

    cache_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    data_type: Mapped[Optional[str]] = mapped_column(String(50))
    ticker: Mapped[Optional[str]] = mapped_column(String(20))
    last_fetched: Mapped[Optional[datetime]] = mapped_column(DateTime)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    record_count: Mapped[Optional[int]] = mapped_column(Integer)
