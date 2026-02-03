"""Cache operations for reading and storing data."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from data_server.config import get_settings
from data_server.db.models import (
    DailyPrice,
    IntradayPrice,
    Content,
    News,
    NewsTicker,
    Company,
    CacheMetadata,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def generate_content_id(url: str) -> str:
    """Generate a unique content ID from URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:64]


async def is_cache_valid(
    session: AsyncSession, cache_key: str, max_age_seconds: int
) -> bool:
    """Check if cache entry is still valid.

    Returns True if:
    - expires_at hasn't passed yet, OR
    - last_fetched is within max_age_seconds (allows dynamic TTL override)
    """
    result = await session.execute(
        select(CacheMetadata).where(CacheMetadata.cache_key == cache_key)
    )
    metadata = result.scalar_one_or_none()

    if not metadata:
        return False

    now = datetime.utcnow()

    # Check if within the requested max_age (allows longer TTL for historical data)
    if metadata.last_fetched:
        age = (now - metadata.last_fetched).total_seconds()
        if age < max_age_seconds:
            return True

    # Fall back to stored expires_at
    if metadata.expires_at and now < metadata.expires_at:
        return True

    return False


async def update_cache_metadata(
    session: AsyncSession,
    cache_key: str,
    data_type: str,
    ticker: Optional[str] = None,
    max_age_seconds: int = 3600,
    record_count: int = 0,
):
    """Update or insert cache metadata."""
    now = datetime.utcnow()
    stmt = insert(CacheMetadata).values(
        cache_key=cache_key,
        data_type=data_type,
        ticker=ticker,
        last_fetched=now,
        expires_at=now + timedelta(seconds=max_age_seconds),
        record_count=record_count,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["cache_key"],
        set_={
            "last_fetched": now,
            "expires_at": now + timedelta(seconds=max_age_seconds),
            "record_count": record_count,
        },
    )
    await session.execute(stmt)


# Daily Prices
async def get_daily_prices(
    session: AsyncSession,
    ticker: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> list[dict]:
    """Get cached daily prices for a ticker."""
    query = select(DailyPrice).where(DailyPrice.ticker == ticker)

    if from_date:
        query = query.where(DailyPrice.date >= from_date.date())
    if to_date:
        query = query.where(DailyPrice.date <= to_date.date())

    query = query.order_by(DailyPrice.date.asc())
    result = await session.execute(query)
    prices = result.scalars().all()

    return [
        {
            "date": p.date.isoformat(),
            "open": float(p.open) if p.open else None,
            "high": float(p.high) if p.high else None,
            "low": float(p.low) if p.low else None,
            "close": float(p.close) if p.close else None,
            "adjusted_close": float(p.adjusted_close) if p.adjusted_close else None,
            "volume": p.volume,
        }
        for p in prices
    ]


def parse_date_str(date_str: str) -> datetime:
    """Parse date string to datetime object."""
    if isinstance(date_str, datetime):
        return date_str
    return datetime.strptime(date_str, "%Y-%m-%d")


async def store_daily_prices(
    session: AsyncSession, ticker: str, prices: list[dict]
) -> int:
    """Store daily prices in cache."""
    if not prices:
        return 0

    for price in prices:
        date_val = price.get("date")
        if isinstance(date_val, str):
            date_val = parse_date_str(date_val)

        stmt = insert(DailyPrice).values(
            ticker=ticker,
            date=date_val,
            open=price.get("open"),
            high=price.get("high"),
            low=price.get("low"),
            close=price.get("close"),
            adjusted_close=price.get("adjusted_close"),
            volume=price.get("volume"),
            fetched_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={
                "open": price.get("open"),
                "high": price.get("high"),
                "low": price.get("low"),
                "close": price.get("close"),
                "adjusted_close": price.get("adjusted_close"),
                "volume": price.get("volume"),
                "fetched_at": datetime.utcnow(),
            },
        )
        await session.execute(stmt)

    return len(prices)


# Intraday Prices
async def get_intraday_prices(
    session: AsyncSession,
    ticker: str,
    from_timestamp: Optional[datetime] = None,
    to_timestamp: Optional[datetime] = None,
) -> list[dict]:
    """Get cached intraday prices for a ticker."""
    query = select(IntradayPrice).where(IntradayPrice.ticker == ticker)

    if from_timestamp:
        query = query.where(IntradayPrice.timestamp >= from_timestamp)
    if to_timestamp:
        query = query.where(IntradayPrice.timestamp <= to_timestamp)

    query = query.order_by(IntradayPrice.timestamp.asc())
    result = await session.execute(query)
    prices = result.scalars().all()

    return [
        {
            "timestamp": p.timestamp.isoformat(),
            "open": float(p.open) if p.open else None,
            "high": float(p.high) if p.high else None,
            "low": float(p.low) if p.low else None,
            "close": float(p.close) if p.close else None,
            "volume": p.volume,
        }
        for p in prices
    ]


def parse_timestamp(ts) -> datetime:
    """Parse timestamp (Unix int or ISO string) to datetime object."""
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return ts


async def store_intraday_prices(
    session: AsyncSession, ticker: str, prices: list[dict]
) -> int:
    """Store intraday prices in cache."""
    if not prices:
        return 0

    for price in prices:
        ts_val = price.get("timestamp")
        if ts_val is not None:
            ts_val = parse_timestamp(ts_val)

        stmt = insert(IntradayPrice).values(
            ticker=ticker,
            timestamp=ts_val,
            open=price.get("open"),
            high=price.get("high"),
            low=price.get("low"),
            close=price.get("close"),
            volume=price.get("volume"),
            fetched_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "timestamp"],
            set_={
                "open": price.get("open"),
                "high": price.get("high"),
                "low": price.get("low"),
                "close": price.get("close"),
                "volume": price.get("volume"),
                "fetched_at": datetime.utcnow(),
            },
        )
        await session.execute(stmt)

    return len(prices)


# News
async def get_news_for_ticker(
    session: AsyncSession,
    ticker: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Get cached news for a ticker with content (EODHD-compatible format).

    Optimized to only select needed columns (excludes full_content for speed).
    """
    # Select only needed columns to avoid loading large full_content field
    query = (
        select(
            News.published_at,
            News.source,
            News.polarity,
            News.positive,
            News.negative,
            News.neutral,
            Content.title,
            Content.summary,
            Content.url,
        )
        .select_from(NewsTicker)
        .join(News, NewsTicker.news_id == News.id)
        .outerjoin(Content, News.content_id == Content.id)
        .where(NewsTicker.ticker == ticker)
        .order_by(News.published_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    rows = result.all()

    news_list = []
    for row in rows:
        # Return EODHD-compatible format for client compatibility
        news_list.append(
            {
                "title": row.title or "",
                "content": row.summary or "",
                "link": row.url or "",
                "date": row.published_at.isoformat() if row.published_at else None,
                "source": row.source,
                "sentiment": {
                    "polarity": float(row.polarity) if row.polarity else 0,
                    "pos": float(row.positive) if row.positive else 0,
                    "neg": float(row.negative) if row.negative else 0,
                    "neu": float(row.neutral) if row.neutral else 0,
                },
            }
        )

    return news_list


async def get_newest_news_date_for_ticker(
    session: AsyncSession, ticker: str
) -> Optional[datetime]:
    """Get the newest (most recent) news date for a ticker in the database."""
    query = (
        select(func.max(News.published_at))
        .select_from(NewsTicker)
        .join(News, NewsTicker.news_id == News.id)
        .where(NewsTicker.ticker == ticker)
    )
    result = await session.execute(query)
    newest_date = result.scalar_one_or_none()
    return newest_date


async def store_news_article(
    session: AsyncSession,
    news_data: dict,
    content_data: dict,
    tickers: list[str],
) -> str:
    """Store a news article with its content and ticker associations."""
    # Generate content ID from URL
    content_id = generate_content_id(content_data.get("url", ""))

    # Insert or update content
    content_stmt = insert(Content).values(
        id=content_id,
        content_type="news",
        url=content_data.get("url"),
        title=content_data.get("title"),
        summary=content_data.get("summary"),
        full_content=content_data.get("full_content"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    content_stmt = content_stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "title": content_data.get("title"),
            "summary": content_data.get("summary"),
            "full_content": content_data.get("full_content"),
            "updated_at": datetime.utcnow(),
        },
    )
    await session.execute(content_stmt)

    # Generate news ID
    news_id = news_data.get("id") or generate_content_id(
        f"{content_data.get('url', '')}_{news_data.get('published_at', '')}"
    )

    # Parse published_at and ensure it's timezone-naive
    published_at = news_data.get("published_at")
    if published_at:
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at.replace(" ", "T").replace("Z", "+00:00"))
            except ValueError:
                published_at = None
        # Remove timezone info if present (convert to naive UTC)
        if published_at and hasattr(published_at, 'tzinfo') and published_at.tzinfo is not None:
            published_at = published_at.replace(tzinfo=None)

    # Insert or update news metadata
    news_stmt = insert(News).values(
        id=news_id,
        content_id=content_id,
        source=news_data.get("source"),
        published_at=published_at,
        polarity=news_data.get("polarity"),
        positive=news_data.get("positive"),
        negative=news_data.get("negative"),
        neutral=news_data.get("neutral"),
        fetched_at=datetime.utcnow(),
    )
    news_stmt = news_stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "polarity": news_data.get("polarity"),
            "positive": news_data.get("positive"),
            "negative": news_data.get("negative"),
            "neutral": news_data.get("neutral"),
            "fetched_at": datetime.utcnow(),
        },
    )
    await session.execute(news_stmt)

    # Delete existing ticker associations and insert new ones
    await session.execute(delete(NewsTicker).where(NewsTicker.news_id == news_id))
    for ticker in tickers:
        ticker_stmt = insert(NewsTicker).values(
            news_id=news_id,
            ticker=ticker,
            relevance=1.0,
        )
        ticker_stmt = ticker_stmt.on_conflict_do_nothing()
        await session.execute(ticker_stmt)

    return news_id


# Content
async def get_content(session: AsyncSession, content_id: str) -> Optional[dict]:
    """Get full content by ID."""
    result = await session.execute(
        select(Content).where(Content.id == content_id)
    )
    content = result.scalar_one_or_none()

    if not content:
        return None

    return {
        "id": content.id,
        "content_type": content.content_type,
        "url": content.url,
        "title": content.title,
        "summary": content.summary,
        "full_content": content.full_content,
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
    }


async def get_content_batch(
    session: AsyncSession, content_ids: list[str]
) -> list[dict]:
    """Get multiple content items by IDs."""
    result = await session.execute(
        select(Content).where(Content.id.in_(content_ids))
    )
    contents = result.scalars().all()

    return [
        {
            "id": c.id,
            "content_type": c.content_type,
            "url": c.url,
            "title": c.title,
            "summary": c.summary,
            "full_content": c.full_content,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in contents
    ]


# Company
async def get_company(session: AsyncSession, ticker: str) -> Optional[dict]:
    """Get cached company information."""
    result = await session.execute(
        select(Company).where(Company.ticker == ticker)
    )
    company = result.scalar_one_or_none()

    if not company:
        return None

    return {
        "ticker": company.ticker,
        "name": company.name,
        "exchange": company.exchange,
        "sector": company.sector,
        "industry": company.industry,
        "market_cap": company.market_cap,
        "pe_ratio": float(company.pe_ratio) if company.pe_ratio else None,
        "eps": float(company.eps) if company.eps else None,
        "fetched_at": company.fetched_at.isoformat() if company.fetched_at else None,
    }


async def store_company(session: AsyncSession, company_data: dict) -> None:
    """Store company information in cache."""
    stmt = insert(Company).values(
        ticker=company_data.get("ticker"),
        name=company_data.get("name"),
        exchange=company_data.get("exchange"),
        sector=company_data.get("sector"),
        industry=company_data.get("industry"),
        market_cap=company_data.get("market_cap"),
        pe_ratio=company_data.get("pe_ratio"),
        eps=company_data.get("eps"),
        fetched_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "name": company_data.get("name"),
            "exchange": company_data.get("exchange"),
            "sector": company_data.get("sector"),
            "industry": company_data.get("industry"),
            "market_cap": company_data.get("market_cap"),
            "pe_ratio": company_data.get("pe_ratio"),
            "eps": company_data.get("eps"),
            "fetched_at": datetime.utcnow(),
        },
    )
    await session.execute(stmt)
