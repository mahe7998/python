"""EODHD proxy utilities - shared caching logic."""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, TypeVar, Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from data_server.config import get_settings
from data_server.db import cache
from data_server.services.eodhd_client import get_eodhd_client

logger = logging.getLogger(__name__)
settings = get_settings()

T = TypeVar("T")


async def cached_fetch(
    session: AsyncSession,
    cache_key: str,
    data_type: str,
    ticker: Optional[str],
    max_age_seconds: int,
    fetch_fn: Callable[[], Awaitable[T]],
    cache_get_fn: Optional[Callable[[], Awaitable[Optional[T]]]] = None,
    cache_store_fn: Optional[Callable[[T], Awaitable[int]]] = None,
) -> T:
    """
    Generic cached fetch pattern.

    Args:
        session: Database session
        cache_key: Unique cache key
        data_type: Type of data for metadata
        ticker: Associated ticker (if any)
        max_age_seconds: Cache duration
        fetch_fn: Async function to fetch fresh data
        cache_get_fn: Optional function to get cached data
        cache_store_fn: Optional function to store fetched data

    Returns:
        Data from cache or freshly fetched
    """
    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, max_age_seconds):
        logger.debug(f"Cache hit for {cache_key}")
        if cache_get_fn:
            cached_data = await cache_get_fn()
            if cached_data:
                return cached_data

    # Fetch fresh data
    logger.info(f"Cache miss for {cache_key}, fetching fresh data")
    data = await fetch_fn()

    # Store in cache if function provided
    record_count = 0
    if cache_store_fn and data:
        record_count = await cache_store_fn(data)

    # Update cache metadata
    await cache.update_cache_metadata(
        session,
        cache_key,
        data_type,
        ticker,
        max_age_seconds,
        record_count,
    )
    await session.commit()

    return data


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


def format_symbol(ticker: str, exchange: str = "US") -> str:
    """Format ticker symbol for EODHD API."""
    if "." in ticker:
        return ticker
    return f"{ticker}.{exchange}"


def extract_ticker(symbol: str) -> str:
    """Extract ticker from symbol string."""
    return symbol.split(".")[0]
