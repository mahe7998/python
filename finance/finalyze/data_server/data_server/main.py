"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_server.api.routes import router as api_router
from data_server.api.tracking import router as tracking_router
from data_server.db.database import init_db, close_db
from data_server.workers.scheduler import start_scheduler, stop_scheduler
from data_server.ws.manager import manager as ws_manager
from data_server.ws.handlers import router as ws_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _refresh_stale_live_prices():
    """Sync LivePrice table with daily_prices on startup.

    1. Check if LivePrice data is stale (>1 day old).
    2. If stale, fetch last 5 days of daily prices from EODHD (lightweight).
    3. Sync LivePrice from daily_prices (create missing, update stale).
    """
    from datetime import datetime, date as date_type, timedelta
    from decimal import Decimal
    from data_server.db.database import async_session_factory
    from data_server.db.models import LivePrice, DailyPrice
    from data_server.api.tracking import get_tracked_tickers
    from data_server.db import cache
    from sqlalchemy import select, func, and_
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    async with async_session_factory() as session:
        # Get all tracked tickers to ensure LivePrice coverage
        tracked = await get_tracked_tickers(session)

        result = await session.execute(select(LivePrice))
        prices = result.scalars().all()
        live_by_ticker = {p.ticker: p for p in prices}

        # Check if any LivePrice is stale (>1 day old)
        now = datetime.utcnow()
        stale_count = sum(
            1 for lp in prices
            if lp.market_timestamp and (now - lp.market_timestamp).days > 1
        )

        # If stale, fetch last 5 days of daily prices from EODHD (cheap: ~148 calls)
        if stale_count > 0:
            logger.info(f"Startup: {stale_count} stale LivePrice entries, fetching recent daily prices...")
            from_date = (now - timedelta(days=5)).strftime("%Y-%m-%d")
            try:
                from data_server.services.eodhd_client import get_eodhd_client
                client = await get_eodhd_client()
                fetched = 0
                for symbol in tracked:
                    try:
                        data = await client.get_eod(symbol, from_date=from_date)
                        if data:
                            await cache.store_daily_prices(session, symbol, data)
                            fetched += 1
                    except Exception as e:
                        logger.debug(f"Startup fetch failed for {symbol}: {e}")
                await session.commit()
                logger.info(f"Startup: fetched recent daily prices for {fetched}/{len(tracked)} stocks")
            except Exception as e:
                logger.error(f"Startup: daily price fetch failed: {e}")

        # Find tracked tickers missing from LivePrice
        missing_tickers = [t for t in tracked if t not in live_by_ticker]

        # Get latest daily close for ALL tracked tickers (existing + missing)
        all_tickers = list(set(list(live_by_ticker.keys()) + missing_tickers))
        latest_dates_subq = (
            select(
                DailyPrice.ticker,
                func.max(DailyPrice.date).label("max_date"),
            )
            .where(DailyPrice.ticker.in_(all_tickers))
            .group_by(DailyPrice.ticker)
            .subquery()
        )
        latest_daily = await session.execute(
            select(DailyPrice).join(
                latest_dates_subq,
                and_(
                    DailyPrice.ticker == latest_dates_subq.c.ticker,
                    DailyPrice.date == latest_dates_subq.c.max_date,
                ),
            )
        )

        updated_count = 0
        created_count = 0
        for dp in latest_daily.scalars().all():
            if dp.close is None:
                continue

            dp_date = dp.date if isinstance(dp.date, date_type) else dp.date.date()

            # Get previous close for change calculation
            prev_result = await session.execute(
                select(DailyPrice.close)
                .where(DailyPrice.ticker == dp.ticker, DailyPrice.date < dp.date)
                .order_by(DailyPrice.date.desc())
                .limit(1)
            )
            prev_close = prev_result.scalar()

            change = None
            change_pct = None
            if prev_close is not None and prev_close != 0:
                change = dp.close - prev_close
                change_pct = Decimal(str(float(change / prev_close) * 100))

            exchange = dp.ticker.split(".")[-1] if "." in dp.ticker else "US"

            lp = live_by_ticker.get(dp.ticker)
            if lp:
                # Only update when daily data is newer or same-day price correction
                lp_date = lp.market_timestamp.date() if lp.market_timestamp else date_type.min
                if dp_date >= lp_date:
                    lp.price = dp.close
                    lp.open = dp.open
                    lp.high = dp.high
                    lp.low = dp.low
                    if prev_close is not None:
                        lp.previous_close = prev_close
                        lp.change = change
                        lp.change_percent = change_pct
                    lp.volume = dp.volume
                    lp.market_timestamp = datetime.combine(dp_date, datetime.min.time())
                    lp.updated_at = datetime.utcnow()
                    lp.data_source = "daily_prices_db"
                    updated_count += 1
            else:
                # Create missing LivePrice entry from daily data
                stmt = pg_insert(LivePrice).values(
                    ticker=dp.ticker,
                    exchange=exchange,
                    price=dp.close,
                    open=dp.open,
                    high=dp.high,
                    low=dp.low,
                    previous_close=prev_close,
                    change=change,
                    change_percent=change_pct,
                    volume=dp.volume,
                    market_timestamp=datetime.combine(dp_date, datetime.min.time()),
                    updated_at=datetime.utcnow(),
                    data_source="daily_prices_db",
                ).on_conflict_do_nothing(index_elements=["ticker"])
                await session.execute(stmt)
                created_count += 1

        await session.commit()
        logger.info(f"Startup: LivePrice sync — updated {updated_count}, created {created_count} from daily_prices")


async def _invalidate_stale_eod_caches():
    """Invalidate EOD caches that are missing today's data after market close."""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from data_server.db.database import async_session_factory
    from data_server.db.models import CacheMetadata

    # Only invalidate if US market has closed today (after 4:30 PM ET = 21:30 UTC)
    now_utc = datetime.utcnow()
    # ET is UTC-5 (ignoring DST for simplicity)
    now_et = now_utc - timedelta(hours=5)
    market_close_today = now_et.replace(hour=16, minute=30, second=0, microsecond=0)

    if now_et < market_close_today:
        logger.info("US market hasn't closed yet today, skipping EOD cache invalidation")
        return

    async with async_session_factory() as session:
        # Delete EOD caches fetched before today's market close
        cutoff = market_close_today + timedelta(hours=5)  # Convert back to UTC
        result = await session.execute(
            delete(CacheMetadata).where(
                CacheMetadata.cache_key.startswith("eod:"),
                CacheMetadata.last_fetched < cutoff,
            )
        )
        deleted = result.rowcount
        await session.commit()

    if deleted:
        logger.info(f"Startup: invalidated {deleted} stale EOD cache entries (fetched before market close)")
    else:
        logger.info("EOD caches are up to date")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting data server...")
    await init_db()
    await _refresh_stale_live_prices()  # Fast: DB-only, no API calls
    await _invalidate_stale_eod_caches()
    await start_scheduler()
    logger.info("Data server started successfully")

    yield

    # Shutdown
    logger.info("Shutting down data server...")
    await stop_scheduler()
    await ws_manager.disconnect_all()
    await close_db()
    logger.info("Data server shutdown complete")


app = FastAPI(
    title="Data Server",
    description="EODHD caching proxy server with real-time updates",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router, prefix="/api")
app.include_router(tracking_router, prefix="/tracking")
app.include_router(ws_router)  # WebSocket router (no prefix, uses /ws)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Data Server",
        "version": "0.1.0",
        "description": "EODHD caching proxy server",
    }
