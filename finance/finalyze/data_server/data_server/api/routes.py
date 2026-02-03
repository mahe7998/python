"""REST API routes - EODHD proxy endpoints."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from data_server.config import get_settings
from data_server.db.database import get_session
from data_server.db import cache
from data_server.services.eodhd_client import get_eodhd_client, get_eodhd_stats

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

# Per-key locks to prevent concurrent fetches for the same data
_fetch_locks: Dict[str, asyncio.Lock] = {}
_fetch_locks_lock = asyncio.Lock()


async def get_fetch_lock(cache_key: str) -> asyncio.Lock:
    """Get or create a lock for a specific cache key."""
    async with _fetch_locks_lock:
        if cache_key not in _fetch_locks:
            _fetch_locks[cache_key] = asyncio.Lock()
        return _fetch_locks[cache_key]


def log_timing(endpoint: str, cache_hit: bool, cache_time_ms: float, eodhd_time_ms: float = 0, total_time_ms: float = 0):
    """Log cache hit/miss and timing information."""
    status = "CACHE HIT" if cache_hit else "CACHE MISS"
    if cache_hit:
        logger.info(f"[{status}] {endpoint} | cache lookup: {cache_time_ms:.1f}ms | total: {total_time_ms:.1f}ms")
    else:
        logger.info(f"[{status}] {endpoint} | cache lookup: {cache_time_ms:.1f}ms | EODHD fetch: {eodhd_time_ms:.1f}ms | total: {total_time_ms:.1f}ms")


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
    start_time = time.time()
    cache_key = f"eod:{symbol}:{from_}:{to}:{period}"
    endpoint = f"GET /eod/{symbol}?from={from_}&to={to}"

    # Check cache validity
    cache_start = time.time()
    is_valid = await cache.is_cache_valid(session, cache_key, settings.cache_daily_prices)
    cache_time = (time.time() - cache_start) * 1000

    if is_valid:
        from_date = datetime.fromisoformat(from_) if from_ else None
        to_date = datetime.fromisoformat(to) if to else None
        cached_data = await cache.get_daily_prices(session, symbol, from_date, to_date)
        # Return cached data even if empty list (empty means no data exists for this symbol)
        if cached_data is not None:
            total_time = (time.time() - start_time) * 1000
            log_timing(endpoint, True, cache_time, 0, total_time)
            return cached_data

    # Use lock to prevent concurrent fetches for the same data
    fetch_lock = await get_fetch_lock(cache_key)
    async with fetch_lock:
        # Expire session cache to see changes from other transactions
        session.expire_all()

        # Double-check cache after acquiring lock (another request may have populated it)
        is_valid = await cache.is_cache_valid(session, cache_key, settings.cache_daily_prices)
        if is_valid:
            from_date = datetime.fromisoformat(from_) if from_ else None
            to_date = datetime.fromisoformat(to) if to else None
            cached_data = await cache.get_daily_prices(session, symbol, from_date, to_date)
            if cached_data is not None:  # Note: check for None, not truthiness (empty list is valid)
                total_time = (time.time() - start_time) * 1000
                logger.info(f"[CACHE HIT after lock] {endpoint}")
                return cached_data

        # Fetch from EODHD
        eodhd_start = time.time()
        client = await get_eodhd_client()
        try:
            data = await client.get_eod(symbol, from_, to, period)
        except Exception as e:
            logger.error(f"EODHD error: {e}")
            raise HTTPException(status_code=502, detail=f"Error fetching from EODHD API: {e}")
        eodhd_time = (time.time() - eodhd_start) * 1000

        # Store in cache (even if empty, to avoid repeated fetches for missing data)
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

        total_time = (time.time() - start_time) * 1000
        log_timing(endpoint, False, cache_time, eodhd_time, total_time)

        return data


@router.get("/intraday/{symbol}")
async def get_intraday_prices(
    symbol: str,
    api_token: str = Query(None),
    interval: str = Query("1m", description="Interval: 1m, 5m, 1h"),
    from_: Optional[int] = Query(None, alias="from", description="Start timestamp"),
    to: Optional[int] = Query(None, description="End timestamp"),
    fmt: str = Query("json"),
    force_eodhd: bool = Query(False, description="Force fetch from EODHD API (bypass price worker data)"),
    session: AsyncSession = Depends(get_session),
):
    """Get intraday prices for a symbol.

    For today's data: returns data from intraday_prices table (price worker snapshots)
    unless force_eodhd=true, which fetches proper OHLC bars from EODHD API.

    For historical data: fetches from EODHD and caches.
    """
    start_time = time.time()
    ticker = symbol.split(".")[0]  # Extract ticker from symbol (e.g., AAPL from AAPL.US)
    cache_key = f"intraday:{symbol}:{interval}:{from_}:{to}"
    endpoint = f"GET /intraday/{symbol}?interval={interval}"
    from_ts = datetime.fromtimestamp(from_) if from_ else None
    to_ts = datetime.fromtimestamp(to) if to else None

    # Check if requesting today's data
    today = datetime.utcnow().date()
    is_today = False
    if to_ts:
        is_today = to_ts.date() >= today
    elif from_ts:
        is_today = from_ts.date() >= today
    else:
        is_today = True  # No date filter = today

    # Initialize cache_time for logging
    cache_time = 0

    # For historical data, use longer cache TTL (24h) since it won't change
    # For today's data, use shorter TTL (60s) to get fresh updates
    cache_ttl = settings.cache_daily_prices if not is_today else settings.cache_intraday_prices

    # force_eodhd means "use EODHD OHLC data, not price worker snapshots"
    # But we can still use cached EODHD data if it's valid
    if force_eodhd:
        # Check if we have valid cached EODHD data for this request
        cache_start = time.time()
        is_valid = await cache.is_cache_valid(session, cache_key, cache_ttl)
        if is_valid:
            cached_data = await cache.get_intraday_prices(session, ticker, from_ts, to_ts)
            cache_time = (time.time() - cache_start) * 1000
            if cached_data:
                total_time = (time.time() - start_time) * 1000
                log_timing(endpoint, True, cache_time, 0, total_time)
                logger.info(f"[CACHE HIT] force_eodhd but cache valid for {cache_key}")
                return cached_data
        logger.info(f"force_eodhd=true, cache stale/missing for {symbol}")
    else:
        # Check cached data first (from price worker)
        cache_start = time.time()
        cached_data = await cache.get_intraday_prices(session, ticker, from_ts, to_ts)
        cache_time = (time.time() - cache_start) * 1000

        if cached_data:
            total_time = (time.time() - start_time) * 1000
            log_timing(endpoint, True, cache_time, 0, total_time)
            return cached_data

        # If requesting today and no cached data, return empty (data will build up from price worker)
        if is_today:
            logger.info(f"No intraday data yet for {ticker} today - data will accumulate from price worker")
            return []

    # For historical data or force_eodhd with stale cache, fetch from EODHD
    fetch_lock = await get_fetch_lock(cache_key)
    async with fetch_lock:
        # Double-check cache after acquiring lock
        is_valid = await cache.is_cache_valid(session, cache_key, cache_ttl)
        if is_valid:
            cached_data = await cache.get_intraday_prices(session, ticker, from_ts, to_ts)
            if cached_data:
                total_time = (time.time() - start_time) * 1000
                logger.info(f"[CACHE HIT after lock] {endpoint}")
                return cached_data

        # Fetch from EODHD
        logger.info(f"Cache miss for {cache_key}, fetching from EODHD")
        eodhd_start = time.time()
        client = await get_eodhd_client()
        try:
            data = await client.get_intraday(symbol, interval, from_, to)
        except Exception as e:
            logger.error(f"EODHD error: {e}")
            raise HTTPException(status_code=502, detail=f"Error fetching from EODHD API: {e}")
        eodhd_time = (time.time() - eodhd_start) * 1000

        # Store in cache
        count = await cache.store_intraday_prices(session, ticker, data)
        await cache.update_cache_metadata(
            session,
            cache_key,
            "intraday_prices",
            ticker,
            cache_ttl,
            count,
        )
        await session.commit()

        total_time = (time.time() - start_time) * 1000
        log_timing(endpoint, False, cache_time, eodhd_time, total_time)

        return data


@router.get("/real-time/{symbol}")
async def get_real_time_quote(
    symbol: str,
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get real-time quote for a symbol (from cached live_prices or EODHD)."""
    from sqlalchemy import select
    from data_server.db.models import LivePrice

    ticker = symbol.split(".")[0]

    # First, check if we have a recent live price in the database
    result = await session.execute(
        select(LivePrice).where(LivePrice.ticker == ticker)
    )
    live_price = result.scalar_one_or_none()

    # If we have a recent price (less than 30 seconds old), return it
    if live_price and live_price.updated_at:
        age = (datetime.utcnow() - live_price.updated_at).total_seconds()
        if age < 30:
            logger.debug(f"Returning cached live price for {ticker} (age: {age:.1f}s)")
            return {
                "code": symbol,
                "timestamp": int(live_price.market_timestamp.timestamp()) if live_price.market_timestamp else None,
                "gmtoffset": 0,
                "open": float(live_price.open) if live_price.open else None,
                "high": float(live_price.high) if live_price.high else None,
                "low": float(live_price.low) if live_price.low else None,
                "close": float(live_price.price) if live_price.price else None,
                "volume": live_price.volume,
                "previousClose": float(live_price.previous_close) if live_price.previous_close else None,
                "change": float(live_price.change) if live_price.change else None,
                "change_p": float(live_price.change_percent) if live_price.change_percent else None,
            }

    # Fetch from EODHD if no cached price or it's stale
    client = await get_eodhd_client()
    try:
        data = await client.get_real_time(symbol)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail="Error fetching from EODHD API")

    return data


@router.get("/live-prices")
async def get_all_live_prices(
    api_token: str = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get all cached live prices for tracked stocks."""
    from sqlalchemy import select
    from data_server.db.models import LivePrice

    result = await session.execute(select(LivePrice))
    prices = result.scalars().all()

    return [
        {
            "ticker": p.ticker,
            "exchange": p.exchange,
            "price": float(p.price) if p.price else None,
            "open": float(p.open) if p.open else None,
            "high": float(p.high) if p.high else None,
            "low": float(p.low) if p.low else None,
            "previous_close": float(p.previous_close) if p.previous_close else None,
            "change": float(p.change) if p.change else None,
            "change_percent": float(p.change_percent) if p.change_percent else None,
            "volume": p.volume,
            "market_timestamp": p.market_timestamp.isoformat() if p.market_timestamp else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in prices
    ]


@router.get("/fundamentals/{symbol}")
async def get_fundamentals(
    symbol: str,
    api_token: str = Query(None),
    fmt: str = Query("json"),
    session: AsyncSession = Depends(get_session),
):
    """Get company fundamentals (cached)."""
    start_time = time.time()
    cache_key = f"fundamentals:{symbol}"
    endpoint = f"GET /fundamentals/{symbol}"

    # Check cache validity
    cache_start = time.time()
    is_valid = await cache.is_cache_valid(session, cache_key, settings.cache_fundamentals)
    cache_time = (time.time() - cache_start) * 1000

    if is_valid:
        company = await cache.get_company(session, symbol.split(".")[0])
        if company:
            total_time = (time.time() - start_time) * 1000
            log_timing(endpoint, True, cache_time, 0, total_time)
            return company

    # Fetch from EODHD
    eodhd_start = time.time()
    client = await get_eodhd_client()
    try:
        data = await client.get_fundamentals(symbol)
    except Exception as e:
        logger.error(f"EODHD error: {e}")
        raise HTTPException(status_code=502, detail=f"Error fetching from EODHD API: {e}")
    eodhd_time = (time.time() - eodhd_start) * 1000

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

    total_time = (time.time() - start_time) * 1000
    log_timing(endpoint, False, cache_time, eodhd_time, total_time)

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
    """Get news articles from cache only.

    News is populated by the background news worker every 15 minutes.
    This endpoint only returns cached data - it never fetches from EODHD directly.
    """
    start_time = time.time()
    ticker = s.split(".")[0] if s else None
    endpoint = f"GET /news?s={s}&limit={limit}"

    if not ticker:
        # General news not supported in cache-only mode
        return []

    # Return cached news only
    fetch_start = time.time()
    cached_data = await cache.get_news_for_ticker(session, ticker, limit, offset)
    fetch_time = (time.time() - fetch_start) * 1000
    total_time = (time.time() - start_time) * 1000

    logger.info(f"[CACHE] {endpoint} | fetch: {fetch_time:.1f}ms | total: {total_time:.1f}ms | {len(cached_data)} articles")
    return cached_data


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


# Batch API (for treemap optimization)
@router.post("/batch/daily-changes")
async def get_batch_daily_changes(
    request: dict,
    session: AsyncSession = Depends(get_session),
):
    """
    Get daily price changes for multiple symbols in a single call.

    Request body:
    {
        "symbols": ["AAPL.US", "GOOGL.US", ...],
        "start_date": "2026-01-03",
        "end_date": "2026-02-02"
    }

    Returns:
    {
        "AAPL.US": {"start_price": 150.0, "end_price": 155.0, "change": 0.0333},
        "GOOGL.US": {"start_price": 140.0, "end_price": 145.0, "change": 0.0357},
        ...
    }
    """
    start_time = time.time()
    symbols = request.get("symbols", [])
    start_date = request.get("start_date")
    end_date = request.get("end_date")

    if not symbols:
        return {}

    logger.info(f"Batch daily changes: {len(symbols)} symbols, {start_date} to {end_date}")

    # Parse dates
    from_date = datetime.fromisoformat(start_date) if start_date else None
    to_date = datetime.fromisoformat(end_date) if end_date else None

    results = {}
    client = await get_eodhd_client()
    symbols_to_fetch = []

    # First pass: check cache for all symbols
    for symbol in symbols:
        try:
            # Get all prices in the date range from cache
            prices = await cache.get_daily_prices(session, symbol, from_date, to_date)

            if prices and len(prices) >= 1:
                # Prices are ordered by date DESC, so last item is oldest (start), first is newest (end)
                end_price = prices[0].get("close")
                start_price = prices[-1].get("close") if len(prices) > 1 else end_price

                if start_price is not None and end_price is not None and start_price != 0:
                    change = (end_price - start_price) / start_price
                    results[symbol] = {
                        "start_price": float(start_price),
                        "end_price": float(end_price),
                        "change": float(change)
                    }
                elif end_price is not None:
                    results[symbol] = {
                        "start_price": None,
                        "end_price": float(end_price),
                        "change": 0
                    }
            else:
                symbols_to_fetch.append(symbol)
        except Exception as e:
            logger.debug(f"Cache lookup failed for {symbol}: {e}")
            symbols_to_fetch.append(symbol)

    cache_time = (time.time() - start_time) * 1000
    logger.info(f"Batch cache lookup: {len(results)} hits, {len(symbols_to_fetch)} misses in {cache_time:.1f}ms")

    # Second pass: fetch missing symbols from EODHD concurrently
    if symbols_to_fetch:
        async def fetch_symbol(symbol: str):
            try:
                data = await client.get_eod(symbol, start_date, end_date)
                if data and len(data) > 0:
                    await cache.store_daily_prices(session, symbol, data)
                    # Data is ordered by date ASC from EODHD
                    start_price = data[0].get("close")
                    end_price = data[-1].get("close")

                    if start_price is not None and end_price is not None and start_price != 0:
                        change = (end_price - start_price) / start_price
                        return symbol, {
                            "start_price": float(start_price),
                            "end_price": float(end_price),
                            "change": float(change)
                        }
                    elif end_price is not None:
                        return symbol, {
                            "start_price": None,
                            "end_price": float(end_price),
                            "change": 0
                        }
                return symbol, None
            except Exception as e:
                logger.debug(f"EODHD fetch failed for {symbol}: {e}")
                return symbol, None

        # Limit concurrent EODHD requests
        semaphore = asyncio.Semaphore(10)

        async def fetch_with_semaphore(symbol):
            async with semaphore:
                return await fetch_symbol(symbol)

        tasks = [fetch_with_semaphore(symbol) for symbol in symbols_to_fetch]
        fetch_results = await asyncio.gather(*tasks)

        for symbol, data in fetch_results:
            if data is not None:
                results[symbol] = data

        await session.commit()

    total_time = (time.time() - start_time) * 1000
    logger.info(f"Batch daily changes completed: {len(results)}/{len(symbols)} symbols in {total_time:.1f}ms")

    return results


@router.get("/server-status")
async def get_server_status():
    """Get data server status including EODHD API call statistics."""
    from data_server.workers.scheduler import get_scheduler_status

    eodhd_stats = get_eodhd_stats()
    scheduler_status = get_scheduler_status()

    return {
        "status": "connected",
        "eodhd_api_calls": eodhd_stats["api_calls"],
        "server_start_time": eodhd_stats["server_start_time"],
        "uptime_seconds": eodhd_stats["uptime_seconds"],
        "scheduler": scheduler_status,
    }
