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


class CacheMetadata(Base):
    """Cache metadata for staleness checking."""

    __tablename__ = "cache_metadata"

    cache_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    data_type: Mapped[Optional[str]] = mapped_column(String(50))
    ticker: Mapped[Optional[str]] = mapped_column(String(20))
    last_fetched: Mapped[Optional[datetime]] = mapped_column(DateTime)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    record_count: Mapped[Optional[int]] = mapped_column(Integer)
