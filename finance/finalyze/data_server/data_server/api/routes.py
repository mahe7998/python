"""REST API routes - EODHD proxy endpoints."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from data_server.config import get_settings
from data_server.db.database import get_session
from data_server.db import cache
from data_server.services.eodhd_client import get_eodhd_client

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


@router.get("/eod/{symbol}")
async def get_eod_prices(
    symbol: str,
    api_token: str = Query(None, description="API token (ignored, uses server key)"),
    from_: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: str = Query("d", description="Period: d, w, m"),
    fmt: str = Query("json", description="Format (always json)"),
    session: AsyncSession = Depends(get_session),
):
    """Get end-of-day prices for a symbol (cached)."""
    cache_key = f"eod:{symbol}:{from_}:{to}:{period}"

    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, settings.cache_daily_prices):
        logger.debug(f"Cache hit for {cache_key}")
        from_date = datetime.fromisoformat(from_) if from_ else None
        to_date = datetime.fromisoformat(to) if to else None
        cached_data = await cache.get_daily_prices(session, symbol, from_date, to_date)
        if cached_data:
            return cached_data

    # Fetch from EODHD
    logger.info(f"Cache miss for {cache_key}, fetching from EODHD")
    client = await get_eodhd_client()
    try:
        data = await client.get_eod(symbol, from_, to, period)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Store in cache
    count = await cache.store_daily_prices(session, symbol, data)
    await cache.update_cache_metadata(
        session,
        cache_key,
        "daily_prices",
        symbol.split(".")[0],
        settings.cache_daily_prices,
        count,
    )
    await session.commit()

    return data


@router.get("/intraday/{symbol}")
async def get_intraday_prices(
    symbol: str,
    api_token: str = Query(None),
    interval: str = Query("1m", description="Interval: 1m, 5m, 1h"),
    from_: Optional[int] = Query(None, alias="from", description="Start timestamp"),
    to: Optional[int] = Query(None, description="End timestamp"),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get intraday prices for a symbol (cached)."""
    cache_key = f"intraday:{symbol}:{interval}:{from_}:{to}"

    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, settings.cache_intraday_prices):
        logger.debug(f"Cache hit for {cache_key}")
        from_ts = datetime.fromtimestamp(from_) if from_ else None
        to_ts = datetime.fromtimestamp(to) if to else None
        cached_data = await cache.get_intraday_prices(session, symbol, from_ts, to_ts)
        if cached_data:
            return cached_data

    # Fetch from EODHD
    logger.info(f"Cache miss for {cache_key}, fetching from EODHD")
    client = await get_eodhd_client()
    try:
        data = await client.get_intraday(symbol, interval, from_, to)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Store in cache
    count = await cache.store_intraday_prices(session, symbol, data)
    await cache.update_cache_metadata(
        session,
        cache_key,
        "intraday_prices",
        symbol.split(".")[0],
        settings.cache_intraday_prices,
        count,
    )
    await session.commit()

    return data


@router.get("/real-time/{symbol}")
async def get_real_time_quote(
    symbol: str,
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get real-time quote for a symbol (cached briefly)."""
    cache_key = f"realtime:{symbol}"

    # Real-time quotes have very short cache
    if await cache.is_cache_valid(session, cache_key, settings.cache_live_quotes):
        logger.debug(f"Cache hit for {cache_key}")
        # Return from cache metadata for real-time (stored as JSON)
        # For simplicity, always fetch real-time data
        pass

    # Fetch from EODHD
    client = await get_eodhd_client()
    try:
        data = await client.get_real_time(symbol)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Update cache metadata
    await cache.update_cache_metadata(
        session,
        cache_key,
        "real_time",
        symbol.split(".")[0],
        settings.cache_live_quotes,
        1,
    )
    await session.commit()

    return data


@router.get("/fundamentals/{symbol}")
async def get_fundamentals(
    symbol: str,
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get company fundamentals (cached)."""
    cache_key = f"fundamentals:{symbol}"

    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, settings.cache_fundamentals):
        logger.debug(f"Cache hit for {cache_key}")
        company = await cache.get_company(session, symbol.split(".")[0])
        if company:
            return company

    # Fetch from EODHD
    logger.info(f"Cache miss for {cache_key}, fetching from EODHD")
    client = await get_eodhd_client()
    try:
        data = await client.get_fundamentals(symbol)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Store in cache (extract relevant fields)
    if data:
        general = data.get("General", {})
        highlights = data.get("Highlights", {})
        company_data = {
            "ticker": symbol.split(".")[0],
            "name": general.get("Name"),
            "exchange": general.get("Exchange"),
            "sector": general.get("Sector"),
            "industry": general.get("Industry"),
            "market_cap": highlights.get("MarketCapitalization"),
            "pe_ratio": highlights.get("PERatio"),
            "eps": highlights.get("EarningsShare"),
        }
        await cache.store_company(session, company_data)
        await cache.update_cache_metadata(
            session,
            cache_key,
            "fundamentals",
            symbol.split(".")[0],
            settings.cache_fundamentals,
            1,
        )
        await session.commit()

    return data


@router.get("/news")
async def get_news(
    api_token: str = Query(None),
    s: Optional[str] = Query(None, description="Symbol (e.g., AAPL.US)"),
    from_: Optional[str] = Query(None, alias="from", description="Start date"),
    to: Optional[str] = Query(None, description="End date"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get news articles (returns metadata only for fast transfer)."""
    ticker = s.split(".")[0] if s else None
    cache_key = f"news:{s}:{from_}:{to}:{limit}:{offset}"

    # Check cache validity
    if ticker and await cache.is_cache_valid(session, cache_key, settings.cache_news):
        logger.debug(f"Cache hit for {cache_key}")
        cached_data = await cache.get_news_for_ticker(session, ticker, limit, offset)
        if cached_data:
            return cached_data

    # Fetch from EODHD
    logger.info(f"Cache miss for {cache_key}, fetching from EODHD")
    client = await get_eodhd_client()
    try:
        data = await client.get_news(s, from_, to, limit, offset)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Store in cache
    for article in data:
        tickers = [t.split(".")[0] for t in article.get("symbols", [])]
        sentiment = article.get("sentiment") or {}
        news_data = {
            "id": None,  # Will be generated
            "source": article.get("source"),
            "published_at": article.get("date"),
            "polarity": sentiment.get("polarity"),
            "positive": sentiment.get("pos"),
            "negative": sentiment.get("neg"),
            "neutral": sentiment.get("neu"),
        }
        content_data = {
            "url": article.get("link"),
            "title": article.get("title"),
            "summary": article.get("content"),
            "full_content": article.get("content"),  # EODHD provides full content
        }
        await cache.store_news_article(session, news_data, content_data, tickers)

    await cache.update_cache_metadata(
        session,
        cache_key,
        "news",
        ticker,
        settings.cache_news,
        len(data),
    )
    await session.commit()

    # Return news metadata (not full content) for the response
    if ticker:
        return await cache.get_news_for_ticker(session, ticker, limit, offset)

    # For general news, return the data as-is but strip content
    return [
        {
            "id": cache.generate_content_id(article.get("link", "")),
            "content_id": cache.generate_content_id(article.get("link", "")),
            "title": article.get("title"),
            "source": article.get("source"),
            "published_at": article.get("date"),
            "symbols": article.get("symbols", []),
            "polarity": (article.get("sentiment") or {}).get("polarity"),
        }
        for article in data
    ]


@router.get("/search/{query}")
async def search_symbols(
    query: str,
    api_token: str = Query(None),
    limit: int = Query(15, ge=1, le=50),
    exchange: Optional[str] = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Search for symbols (cached)."""
    cache_key = f"search:{query}:{exchange}:{limit}"

    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, settings.cache_search):
        logger.debug(f"Cache hit for {cache_key}")
        # For search, we don't store results in DB, just use cache metadata
        pass

    # Fetch from EODHD
    client = await get_eodhd_client()
    try:
        data = await client.search(query, limit, exchange)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Update cache metadata
    await cache.update_cache_metadata(
        session, cache_key, "search", None, settings.cache_search, len(data)
    )
    await session.commit()

    return data


@router.get("/exchanges-list")
async def get_exchanges_list(
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get list of exchanges (cached)."""
    cache_key = "exchanges-list"

    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, settings.cache_company_info):
        logger.debug(f"Cache hit for {cache_key}")
        # For exchanges, we don't store in DB, just use cache metadata
        pass

    # Fetch from EODHD
    client = await get_eodhd_client()
    try:
        data = await client.get_exchanges_list()
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Update cache metadata
    await cache.update_cache_metadata(
        session, cache_key, "exchanges", None, settings.cache_company_info, len(data)
    )
    await session.commit()

    return data


@router.get("/exchange-symbol-list/{exchange}")
async def get_exchange_symbols(
    exchange: str,
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get symbols for an exchange (cached)."""
    cache_key = f"exchange-symbols:{exchange}"

    # Check cache validity
    if await cache.is_cache_valid(session, cache_key, settings.cache_company_info):
        logger.debug(f"Cache hit for {cache_key}")
        pass

    # Fetch from EODHD
    client = await get_eodhd_client()
    try:
        data = await client.get_exchange_symbol_list(exchange)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    # Update cache metadata
    await cache.update_cache_metadata(
        session, cache_key, "exchange_symbols", None, settings.cache_company_info, len(data)
    )
    await session.commit()

    return data


# Content API (new endpoints)
@router.get("/content/{content_id}")
async def get_content(
    content_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get full content by ID."""
    content = await cache.get_content(session, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    return content


@router.post("/content/batch")
async def get_content_batch(
    content_ids: list[str],
    session: AsyncSession = Depends(get_session),
):
    """Get multiple content items by IDs."""
    return await cache.get_content_batch(session, content_ids)
