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
    """Sync LivePrice table with daily_prices on startup. No external API calls.

    1. Update LivePrice rows where daily_prices has a newer/different close.
    2. Delete any LivePrice entries that are still stale (no daily data available).
       They will be repopulated by the price worker when markets open.
    """
    from datetime import datetime, date as date_type
    from decimal import Decimal
    from data_server.db.database import async_session_factory
    from data_server.db.models import LivePrice, DailyPrice
    from sqlalchemy import select, delete, func, and_

    async with async_session_factory() as session:
        result = await session.execute(select(LivePrice))
        prices = result.scalars().all()
        if not prices:
            return

        live_by_ticker = {p.ticker: p for p in prices}

        # Get the latest daily close for each tracked ticker in one query
        latest_dates_subq = (
            select(
                DailyPrice.ticker,
                func.max(DailyPrice.date).label("max_date"),
            )
            .where(DailyPrice.ticker.in_(list(live_by_ticker.keys())))
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
        updated_tickers = set()
        for dp in latest_daily.scalars().all():
            lp = live_by_ticker.get(dp.ticker)
            if not lp or dp.close is None:
                continue

            lp_date = lp.market_timestamp.date() if lp.market_timestamp else date_type.min
            dp_date = dp.date if isinstance(dp.date, date_type) else dp.date.date()
            prices_differ = (
                lp.price is not None
                and abs(float(dp.close) - float(lp.price)) > 0.01
            )

            if dp_date > lp_date or prices_differ:
                prev_result = await session.execute(
                    select(DailyPrice.close)
                    .where(DailyPrice.ticker == dp.ticker, DailyPrice.date < dp.date)
                    .order_by(DailyPrice.date.desc())
                    .limit(1)
                )
                prev_close = prev_result.scalar()

                lp.price = dp.close
                lp.open = dp.open
                lp.high = dp.high
                lp.low = dp.low
                if prev_close is not None:
                    lp.previous_close = prev_close
                    lp.change = dp.close - prev_close
                    if prev_close != 0:
                        lp.change_percent = Decimal(str(
                            float((dp.close - prev_close) / prev_close) * 100
                        ))
                lp.volume = dp.volume
                lp.market_timestamp = datetime.combine(dp_date, datetime.min.time())
                lp.updated_at = datetime.utcnow()
                lp.data_source = "daily_prices_db"
                updated_count += 1
                updated_tickers.add(dp.ticker)

        # Delete LivePrice entries that are still stale (no daily data to fix them)
        stale_tickers = []
        for p in prices:
            if p.ticker in updated_tickers:
                continue
            if p.market_timestamp:
                age_days = (date_type.today() - p.market_timestamp.date()).days
                if age_days > 2:
                    stale_tickers.append(p.ticker)

        if stale_tickers:
            await session.execute(
                delete(LivePrice).where(LivePrice.ticker.in_(stale_tickers))
            )
            logger.info(f"Startup: deleted {len(stale_tickers)} stale LivePrice entries with no daily data")

        await session.commit()
        if updated_count:
            logger.info(f"Startup: updated {updated_count} LivePrice entries from daily_prices (no API calls)")
        else:
            logger.info("Startup: all LivePrice entries already up to date")


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
